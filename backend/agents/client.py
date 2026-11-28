import json
import os
import re
import threading
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

# Global concurrency & cooldown gate to prevent parallel 6-agent bursts from triggering Groq 429s
_GROQ_CONCURRENCY_SEMAPHORE = threading.BoundedSemaphore(2)
_GROQ_COOLDOWN_LOCK = threading.Lock()
_GROQ_COOLDOWN_UNTIL = 0.0
_MISTRAL_BILLING_DISABLED = False

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

        # 1. Primary: Groq Cloud (Qwen-27B) with concurrency pacing & multi-model fallback
        global _GROQ_COOLDOWN_UNTIL, _MISTRAL_BILLING_DISABLED
        if self.groq_client:
            # Try Qwen-27B first, then Groq's fast Llama-3.3-70B / Llama-3.1-8B pools (separate TPM buckets!)
            groq_models = ["qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            with _GROQ_CONCURRENCY_SEMAPHORE:
                for g_model in groq_models:
                    chosen_model = g_model
                    groq_kwargs = dict(kwargs)
                    if not tools:
                        groq_kwargs.setdefault("max_tokens", 3072)
                    call_kwargs = {
                        "model": chosen_model,
                        "messages": messages,
                        **groq_kwargs
                    }
                    if tools:
                        call_kwargs["tools"] = tools

                    t0 = time.time()
                    try:
                        response = self.groq_client.chat.completions.create(**call_kwargs)
                        break
                    except Exception as e:
                        err_msg = str(e)
                        err_ms = round((time.time() - t0) * 1000, 2)
                        is_429 = "429" in err_msg or "rate_limit" in err_msg.lower()
                        if is_429:
                            logger.warning(
                                f"[Groq TPM Limit | {agent_name}] Model {g_model} hit 429; rotating to next Groq model pool..."
                            )
                            time.sleep(0.8)
                            continue
                        else:
                            logger.warning(f"Groq model {g_model} error ({e}); rotating to next model pool...")
                            continue

        # 2. Fallback: Mistral AI (only if Mistral account has active billing budget)
        if response is None and self.mistral_key and not _MISTRAL_BILLING_DISABLED:
            try:
                from mistralai.client import Mistral
                m_client = Mistral(api_key=self.mistral_key)
                chosen_model = model if (model and "qwen" not in model.lower()) else "mistral-small-latest"
                m_kwargs = {"model": chosen_model, "messages": messages, **kwargs}
                if tools:
                    m_kwargs["tools"] = tools
                response = m_client.chat.complete(**m_kwargs)
            except Exception as m_err:
                m_str = str(m_err)
                if "402" in m_str or "billing_no_api_budget_configured" in m_str:
                    _MISTRAL_BILLING_DISABLED = True
                    logger.warning("[Mistral] API key has no billing budget (402). Disabling Mistral failover and retrying Groq after 3s...")
                else:
                    logger.warning(f"[Mistral] Failover error: {m_err}")

        # 3. Last-resort Groq retry after brief pause if all pools were busy
        if response is None and self.groq_client:
            time.sleep(3.0)
            for fallback_m in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "qwen/qwen3.8-27b"):
                try:
                    chosen_model = fallback_m
                    retry_kwargs = {"model": chosen_model, "messages": messages, **kwargs}
                    if tools:
                        retry_kwargs["tools"] = tools
                    response = self.groq_client.chat.completions.create(**retry_kwargs)
                    break
                except Exception:
                    time.sleep(1.5)
                    continue

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


def parse_llm_json(raw_content: Optional[str], fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely extracts and parses a JSON object from an LLM response that may contain:
      - `<think>...</think>` reasoning blocks (including unclosed `<think>` blocks if truncated)
      - Markdown ```json ... ``` code fences
      - Leading or trailing commentary around the JSON object
      - Slightly truncated trailing strings/arrays when completion hit max_tokens
    """
    if not raw_content:
        if fallback is not None:
            return fallback
        raise ValueError("Empty LLM response content")

    txt = str(raw_content).strip()
    # 1. Strip complete <think>...</think> blocks
    txt = re.sub(r"<think>[\s\S]*?</think>", "", txt, flags=re.IGNORECASE).strip()
    # 2. If an unclosed <think> tag remains, strip up to the first '{' after it
    if "<think>" in txt.lower():
        idx_t = txt.lower().find("<think>")
        brace_after = txt.find("{", idx_t)
        if brace_after != -1:
            txt = txt[brace_after:]

    # 3. Strip markdown code fences
    txt = txt.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

    # 4. Isolate outermost JSON object { ... }
    first_brace = txt.find("{")
    last_brace = txt.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = txt[first_brace : last_brace + 1]
    elif first_brace != -1:
        candidate = txt[first_brace:]
    else:
        candidate = txt

    # Direct parse attempt
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 5. Repair common trailing commas or truncated tail if max_tokens cut off the end
    repaired = re.sub(r",\s*([\]}])", r"\1", candidate)
    try:
        parsed = json.loads(repaired)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Progressive truncation repair: trim back to last valid comma/value and close open brackets/braces
    for cut_char in (",", "}", "]"):
        pos = repaired.rfind(cut_char)
        while pos > 0:
            prefix = repaired[: pos if cut_char == "," else pos + 1].rstrip()
            # Count unclosed quotes, brackets, braces
            in_str = False
            esc = False
            open_braces = 0
            open_brackets = 0
            for ch in prefix:
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == "{":
                        open_braces += 1
                    elif ch == "}":
                        open_braces = max(0, open_braces - 1)
                    elif ch == "[":
                        open_brackets += 1
                    elif ch == "]":
                        open_brackets = max(0, open_brackets - 1)
            closer = ('"' if in_str else "") + ("]" * open_brackets) + ("}" * open_braces)
            try:
                parsed = json.loads(prefix + closer)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            pos = repaired.rfind(cut_char, 0, pos)

    if fallback is not None:
        return fallback
    raise ValueError(f"Could not parse JSON from LLM output (len={len(raw_content)})")