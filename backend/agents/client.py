import os
import time
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from groq import Groq
from loguru import logger
from agents.db import query
from agents.api_monitor import record_external_api_call
from agents.observability import check_agent_input_guardrails, record_llm_generation
from agents.metrics import (
    llm_prompt_tokens_total,
    llm_completion_tokens_total,
    llm_total_tokens_total,
    llm_duration_seconds
)

load_dotenv()

def log_token_usage_to_db(
    agent_name: str,
    ticker: Optional[str],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
    step_number: int = 1
):
    """Records token consumption into PostgreSQL and deducts exact tokens from the active user's wallet."""
    active_uid = None
    try:
        from agents.billing_router import current_billing_user_id, deduct_user_tokens

        active_uid = current_billing_user_id.get()
        if active_uid is not None and total_tokens > 0:
            deduct_user_tokens(active_uid, total_tokens, agent_name=agent_name, ticker=ticker or "GENERAL")
    except Exception as be:
        logger.debug(f"Token wallet deduction skipped: {be}")

    try:
        query(
            """INSERT INTO agent_token_logs 
               (agent_name, ticker, model, prompt_tokens, completion_tokens, total_tokens, duration_ms, step_number)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                agent_name,
                ticker or "GENERAL",
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                duration_ms,
                step_number
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to record token usage to DB: {e}")

class UnifiedChatCompletion:
    def __init__(self, groq_client: Optional[Groq] = None):
        self.groq_client = groq_client
        self.mistral_key = os.environ.get("MISTRAL_API_KEY")

    def complete(
        self,
        model: str = None,
        messages: list = None,
        tools: list = None,
        agent_name: str = "generic_agent",
        ticker: Optional[str] = None,
        step_number: int = 1,
        **kwargs
    ):
        """Unified chat completion with automated Prometheus, PostgreSQL & Langfuse I/O tracing."""
        start_time = time.time()
        response = None
        chosen_model = "unknown"
        clean_t = (ticker or "GENERAL").upper()

        # 0. Pre-LLM Input Guardrail Check (validates input messages & attached MCP tools)
        input_guardrail = check_agent_input_guardrails(
            messages=messages,
            tools=tools,
            agent_name=agent_name,
            ticker=clean_t,
        )
        if not input_guardrail["passed"]:
            logger.warning(f"[Input Guardrail | {agent_name}] Flagged input: {input_guardrail['warnings']}")

        # 1. Primary: Groq Cloud (Qwen-27B)
        if self.groq_client:
            chosen_model = "qwen/qwen3.8-27b"
            call_kwargs = {
                "model": chosen_model,
                "messages": messages,
                **kwargs
            }
            if tools:
                call_kwargs["tools"] = tools
            for attempt in range(4):
                t0 = time.time()
                try:
                    response = self.groq_client.chat.completions.create(**call_kwargs)
                    break
                except Exception as e:
                    err_msg = str(e)
                    err_ms = round((time.time() - t0) * 1000, 2)
                    is_429 = "429" in err_msg or "rate_limit" in err_msg
                    record_external_api_call(
                        provider="groq",
                        endpoint="https://api.groq.com/openai/v1/chat/completions",
                        operation=f"chat.completions ({agent_name})",
                        ticker=clean_t,
                        status_code=429 if is_429 else 500,
                        success=False,
                        duration_ms=err_ms,
                        error_message=err_msg,
                    )
                    if is_429:
                        wait_sec = 2.0 * (attempt + 1)
                        logger.warning(f"Groq 429 rate limit hit. Waiting {wait_sec}s (attempt {attempt+1}/4)...")
                        time.sleep(wait_sec)
                    else:
                        logger.warning(f"Groq API completion error: {e}. Attempting Mistral fallback.")
                        break

        # 2. Fallback: Mistral AI
        if response is None and self.mistral_key:
            from mistralai.client import Mistral
            m_client = Mistral(api_key=self.mistral_key)
            chosen_model = model or "mistral-small-latest"
            m_kwargs = {"model": chosen_model, "messages": messages, **kwargs}
            if tools:
                m_kwargs["tools"] = tools
            response = m_client.chat.complete(**m_kwargs)

        if response is None:
            raise RuntimeError("No working LLM provider found (checked Groq and Mistral).")

        # 3. Intercept and Record Token Usage
        duration_sec = time.time() - start_time
        duration_ms = round(duration_sec * 1000, 2)
        
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) if usage else 0

        # Update Prometheus Metrics
        clean_t = (ticker or "GENERAL").upper()
        try:
            llm_prompt_tokens_total.labels(agent_name=agent_name, model=chosen_model, ticker=clean_t).inc(prompt_tokens)
            llm_completion_tokens_total.labels(agent_name=agent_name, model=chosen_model, ticker=clean_t).inc(completion_tokens)
            llm_total_tokens_total.labels(agent_name=agent_name, model=chosen_model, ticker=clean_t).inc(total_tokens)
            llm_duration_seconds.labels(agent_name=agent_name, model=chosen_model).observe(duration_sec)
        except Exception as pe:
            logger.warning(f"Prometheus token metric update error: {pe}")

        # Update PostgreSQL Audit Table & Outbound External API Telemetry
        prov_key = "groq" if ("qwen" in chosen_model.lower() or "llama" in chosen_model.lower()) else "mistral"
        record_external_api_call(
            provider=prov_key,
            endpoint="https://api.groq.com/openai/v1/chat/completions" if prov_key == "groq" else "https://api.mistral.ai/v1/chat/completions",
            operation=f"chat.complete ({agent_name})",
            ticker=clean_t,
            status_code=200,
            success=True,
            duration_ms=duration_ms,
            tokens_used=total_tokens,
            metadata={"model": chosen_model, "step_number": step_number},
        )
        log_token_usage_to_db(
            agent_name=agent_name,
            ticker=clean_t,
            model=chosen_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            step_number=step_number
        )

        # Attach standardized token_usage metadata onto response object
        response.token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
            "model": chosen_model,
            "agent_name": agent_name,
            "step_number": step_number,
            "input_guardrail": input_guardrail,
        }

        # 4. Record Full Input / Output / Tool Call Trace to Langfuse & Local Trace Log
        try:
            msg_obj = response.choices[0].message if getattr(response, "choices", None) else None
            record_llm_generation(
                agent_name=agent_name,
                ticker=clean_t,
                step_number=step_number,
                model=chosen_model,
                messages=messages,
                tools=tools,
                response_message=msg_obj,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                input_guardrail=input_guardrail,
            )
        except Exception as lfe:
            logger.debug(f"Langfuse trace recording skipped: {lfe}")

        logger.info(
            f"[{agent_name} | {clean_t}] Model: {chosen_model} | "
            f"Prompt: {prompt_tokens} | Completion: {completion_tokens} | "
            f"Total: {total_tokens} tokens | Latency: {duration_ms}ms"
        )

        return response

class UnifiedChat:
    def __init__(self, groq_client: Optional[Groq]):
        self._handler = UnifiedChatCompletion(groq_client)

    def complete(self, *args, **kwargs):
        return self._handler.complete(*args, **kwargs)

class UnifiedClient:
    def __init__(self):
        groq_key = os.environ.get("GROQ_API_KEY")
        self.groq_client = Groq(api_key=groq_key) if groq_key else None
        self.chat = UnifiedChat(self.groq_client)

# Single centralized client instance for the entire system
client = UnifiedClient()