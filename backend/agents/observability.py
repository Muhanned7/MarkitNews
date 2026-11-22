"""
MarketPulse Langfuse v4 Observability & Guardrail Tracing (`backend/agents/observability.py`)

Built according to the official Langfuse Agent Skill (`github.com/langfuse/skills`):
  - Uses Langfuse Python SDK v4 (`start_as_current_observation`, `start_observation`, `propagate_attributes`).
  - Enforces proper nested observation hierarchy (`agent` -> `retriever` / `tool` / `guardrail` / `generation` / `evaluator`).
  - Uses stable, low-cardinality, verb-first observation names (e.g. `research-company-footprint`,
    `retrieve-sec-properties`, `check-input-guardrails`, `generate-agent-response`,
    `apply-footprint-guardrails`, `evaluate-footprint-quality`) with run-specific values (`ticker`, `archetype`)
    stored in `metadata`, `tags`, and `session_id`.
  - Captures reasoning (`<think>` blocks), token `usage_details`, model name, and custom trace scores.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterator, List, Optional
from dotenv import load_dotenv
from loguru import logger

_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env", override=True)

_LOG_DIR = _BACKEND_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_TRACE_FILE = _LOG_DIR / "langfuse_traces.jsonl"

_langfuse_client = None
_langfuse_checked = False


def get_langfuse():
    """
    Lazy-initializes the Langfuse v4 SDK client AFTER loading `backend/.env`.
    Automatically un-swaps public/secret keys if they were pasted in reverse order.
    """
    global _langfuse_client, _langfuse_checked
    if _langfuse_checked:
        return _langfuse_client

    _langfuse_checked = True
    pub_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip().strip('"').strip("'")
    sec_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip().strip('"').strip("'")

    # Auto-heal if pk-lf and sk-lf were accidentally swapped in .env
    if pub_key.startswith("sk-lf-") and sec_key.startswith("pk-lf-"):
        pub_key, sec_key = sec_key, pub_key
        os.environ["LANGFUSE_PUBLIC_KEY"] = pub_key
        os.environ["LANGFUSE_SECRET_KEY"] = sec_key

    host = (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    ).strip().strip('"').strip("'")
    os.environ["LANGFUSE_HOST"] = host
    os.environ["LANGFUSE_BASE_URL"] = host

    if not pub_key or not sec_key:
        logger.info(
            "[Langfuse] LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in .env. "
            f"Mirroring all agent I/O & guardrail traces locally to {LOCAL_TRACE_FILE}"
        )
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=pub_key,
            secret_key=sec_key,
            host=host,
        )
        logger.info(f"[Langfuse v4] Initialized client for host: {host}")
    except Exception as exc:
        logger.warning(f"[Langfuse] Could not initialize client ({exc}). Using local trace mirror.")
        _langfuse_client = None

    return _langfuse_client


def flush_langfuse() -> None:
    """Flushes queued OpenTelemetry spans to Langfuse (essential before short scripts/debugger exit)."""
    lf = get_langfuse()
    if lf is not None and hasattr(lf, "flush"):
        try:
            lf.flush()
        except Exception as exc:
            logger.debug(f"[Langfuse] Flush warning: {exc}")


def _append_local_trace(record: Dict[str, Any]) -> None:
    """Writes a structured JSONL trace entry to `backend/logs/langfuse_traces.jsonl`."""
    try:
        with open(LOCAL_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.debug(f"Could not write local trace log: {exc}")


# =====================================================================
# 1. Context Manager for Nested Agent / Tool / Retriever Spans
# =====================================================================

@contextmanager
def trace_agent_run(
    trace_name: str,
    ticker: str,
    input_payload: Dict[str, Any],
    tags: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    """
    Wraps an entire agent execution (or debug harness run) in a root `agent` observation
    with `propagate_attributes` (`trace_name`, `session_id`, `user_id`, `tags`, `metadata`)
    so all child MCP tool retrievals, LLM generations, guardrails, and evaluators nest
    inside one cohesive trace tree and render in the Langfuse Agent Graph.
    """
    lf = get_langfuse()
    clean_t = (ticker or "GENERAL").upper().strip()
    active_tags = list(dict.fromkeys((tags or []) + [f"ticker:{clean_t}", "app:marketpulse"]))
    active_session = session_id or f"footprint-session-{clean_t.lower()}"
    active_meta = {"ticker": clean_t, **(metadata or {})}

    if lf is None:
        yield None
        return

    try:
        from langfuse import propagate_attributes

        with lf.start_as_current_observation(
            name=trace_name,
            as_type="agent",
            input=input_payload,
            metadata=active_meta,
        ) as agent_obs:
            with propagate_attributes(
                trace_name=trace_name,
                session_id=active_session,
                user_id=user_id,
                tags=active_tags,
                metadata={k: str(v) for k, v in active_meta.items() if v is not None},
            ):
                yield agent_obs
    finally:
        flush_langfuse()


def trace_mcp_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
    duration_ms: Optional[float] = None,
) -> None:
    """
    Records an MCP tool invocation under the current active agent trace.
    Uses specific observation type:
      - `retriever` for read-only knowledge/document lookups (`fetch_sec_properties`,
        `fetch_wikipedia_facilities`, `search_web_sources`, `fetch_source_fingerprint`)
      - `tool` for state-changing or action tools
    """
    # Map tool names to low-cardinality, verb-first observation names per Langfuse best practices
    verb_name_map = {
        "fetch_sec_properties": "retrieve-sec-properties",
        "fetch_wikipedia_facilities": "retrieve-wikipedia-facilities",
        "search_web_sources": "search-web-sources",
        "fetch_source_fingerprint": "check-source-fingerprint",
    }
    obs_name = verb_name_map.get(tool_name, f"call-{tool_name.replace('_', '-')}")
    obs_type = "retriever" if tool_name in verb_name_map else "tool"

    # Build concise, readable summary output so huge 4,000-char strings don't clutter the preview
    if isinstance(result, dict):
        if "results" in result and isinstance(result["results"], list):
            summary_output = {
                "article_count": len(result["results"]),
                "urls": [r.get("source_url") for r in result["results"] if isinstance(r, dict)],
                "snippets_preview": [str(r.get("snippet", ""))[:180] for r in result["results"][:3] if isinstance(r, dict)],
            }
        elif "text" in result:
            summary_output = {
                "found": result.get("found", False),
                "source_type": result.get("source_type"),
                "source_url": result.get("source_url"),
                "text_char_length": len(str(result.get("text", ""))),
                "text_preview": str(result.get("text", ""))[:350],
            }
        else:
            summary_output = result
    else:
        summary_output = {"result": str(result)[:350]}

    _append_local_trace(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": obs_type,
            "name": obs_name,
            "tool_name": tool_name,
            "input": arguments,
            "output": summary_output,
            "duration_ms": duration_ms,
        }
    )

    lf = get_langfuse()
    if lf is not None:
        try:
            obs = lf.start_observation(
                name=obs_name,
                as_type=obs_type,
                input=arguments,
                output=summary_output,
                metadata={"mcp_tool": tool_name, "duration_ms": duration_ms},
            )
            obs.end()
        except Exception as exc:
            logger.debug(f"[Langfuse] Tool observation error: {exc}")


# =====================================================================
# 2. Pre-Execution Input Guardrail (`as_type="guardrail"`)
# =====================================================================

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
]


def check_agent_input_guardrails(
    messages: Optional[List[Dict[str, Any]]],
    tools: Optional[List[Dict[str, Any]]],
    agent_name: str,
    ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inspects the input payload (`messages` and `tools`) BEFORE it is sent to the LLM
    and logs a `guardrail` observation (`check-input-guardrails`) in Langfuse.
    """
    warnings: List[str] = []
    passed = True

    if not messages:
        return {"passed": False, "warnings": ["Empty messages list passed to LLM"], "message_count": 0}

    combined_user_text = ""
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "")
            content = str(m.get("content", "") or "")
            if role == "user":
                combined_user_text += " " + content
            for pat in _INJECTION_PATTERNS:
                if pat.search(content):
                    passed = False
                    warnings.append(f"Prompt-injection pattern detected in '{role}' message: '{pat.pattern}'")

    if not combined_user_text.strip():
        warnings.append("No user prompt content found in messages")

    if agent_name == "footprint_agent":
        if "No properties found in Item 2." in combined_user_text and "No Wikipedia facility text." in combined_user_text:
            warnings.append("Both SEC Item 2 and Wikipedia pre-fetch corpora are empty on input")

    tools_attached = [t.get("function", {}).get("name") for t in (tools or []) if isinstance(t, dict)]
    verdict = {
        "passed": passed,
        "warnings": warnings,
        "message_count": len(messages),
        "tools_attached": tools_attached,
        "input_char_length": len(combined_user_text),
    }

    lf = get_langfuse()
    if lf is not None:
        try:
            g_obs = lf.start_observation(
                name="check-input-guardrails",
                as_type="guardrail",
                input={
                    "agent_name": agent_name,
                    "ticker": ticker or "GENERAL",
                    "message_count": len(messages),
                    "tools_attached": tools_attached,
                    "input_char_length": len(combined_user_text),
                },
                output=verdict,
                level="DEFAULT" if passed and not warnings else "WARNING",
                metadata={"agent_name": agent_name, "ticker": ticker or "GENERAL"},
            )
            g_obs.end()
        except Exception as exc:
            logger.debug(f"[Langfuse] Input guardrail span error: {exc}")

    return verdict


# =====================================================================
# 3. LLM Generation Tracer (`as_type="generation"`)
# =====================================================================

def record_llm_generation(
    agent_name: str,
    ticker: str,
    step_number: int,
    model: str,
    messages: Optional[List[Any]],
    tools: Optional[List[Dict[str, Any]]],
    response_message: Any,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: float,
    input_guardrail: Dict[str, Any],
) -> None:
    """
    Logs a single LLM turn (`as_type="generation"`) with:
      - Stable verb-first name (`generate-agent-response`)
      - Role-labeled `messages` input and on-demand MCP `tools`
      - Extracted `<think>` reasoning block (`thinking`) + final output + `tool_calls`
      - Model name & `usage_details` (`input`, `output`, `total`)
    """
    raw_content = getattr(response_message, "content", None) or ""
    # Extract <think>...</think> reasoning from Qwen / reasoning models per Langfuse best practices
    think_matches = re.findall(r"<think>([\s\S]*?)</think>", raw_content)
    thinking_text = "\n".join(t.strip() for t in think_matches if t.strip())
    clean_content = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()

    raw_tool_calls = getattr(response_message, "tool_calls", None) or []
    serialized_tool_calls = [
        {
            "id": getattr(tc, "id", ""),
            "name": getattr(getattr(tc, "function", None), "name", ""),
            "arguments": getattr(getattr(tc, "function", None), "arguments", ""),
        }
        for tc in raw_tool_calls
    ]

    serializable_messages = []
    for m in (messages or []):
        if isinstance(m, dict):
            serializable_messages.append(m)
        else:
            serializable_messages.append(
                {
                    "role": getattr(m, "role", "assistant"),
                    "content": getattr(m, "content", ""),
                }
            )

    output_payload: Dict[str, Any] = {
        "role": "assistant",
        "content": clean_content or raw_content,
    }
    if thinking_text:
        output_payload["thinking"] = thinking_text
    if serialized_tool_calls:
        output_payload["tool_calls"] = serialized_tool_calls

    trace_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "generation",
        "name": "generate-agent-response",
        "agent_name": agent_name,
        "ticker": ticker,
        "step_number": step_number,
        "model": model,
        "input_guardrail": input_guardrail,
        "input": {
            "messages": serializable_messages,
            "tools": [t.get("function", {}).get("name") for t in (tools or []) if isinstance(t, dict)],
        },
        "output": output_payload,
        "usage": {
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": total_tokens,
            "duration_ms": duration_ms,
        },
    }
    _append_local_trace(trace_payload)

    lf = get_langfuse()
    if lf is not None:
        try:
            gen = lf.start_observation(
                name="generate-agent-response",
                as_type="generation",
                model=model,
                input=serializable_messages,
                output=output_payload,
                usage_details={
                    "input": int(prompt_tokens),
                    "output": int(completion_tokens),
                    "total": int(total_tokens),
                },
                metadata={
                    "agent_name": agent_name,
                    "ticker": ticker,
                    "step_number": step_number,
                    "duration_ms": duration_ms,
                    "tools_enabled": trace_payload["input"]["tools"],
                    "has_thinking": bool(thinking_text),
                },
            )
            gen.end()
        except Exception as exc:
            logger.debug(f"[Langfuse] Generation observation error: {exc}")


# =====================================================================
# 4. Output Guardrail (`as_type="guardrail"`) & Evaluator (`as_type="evaluator"`)
# =====================================================================

def record_guardrail_and_eval(
    ticker: str,
    agent_name: str,
    guardrail_stats: Dict[str, Any],
    evaluation_obj: Any = None,
    raw_counts: Optional[Dict[str, int]] = None,
    sanitized_counts: Optional[Dict[str, int]] = None,
) -> None:
    """
    Records:
      1. `apply-footprint-guardrails` (`as_type="guardrail"`) with Link A, Link B, Link C,
         URL Whitelist, and Third-Party Co-Mention results.
      2. If `evaluation_obj` is provided, `evaluate-footprint-quality` (`as_type="evaluator"`)
         and scores the trace with metric names named after what is measured:
         `faithfulness`, `citation_grounding`, `completeness`, `overall_quality`, `hallucinations_detected`.
    """
    eval_dict = {}
    if evaluation_obj is not None:
        eval_dict = (
            evaluation_obj.model_dump()
            if hasattr(evaluation_obj, "model_dump")
            else (evaluation_obj.dict() if hasattr(evaluation_obj, "dict") else {})
        )

    trace_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "guardrail_and_evaluation",
        "agent_name": agent_name,
        "ticker": ticker,
        "guardrail_stats": guardrail_stats,
        "evaluation": eval_dict,
        "raw_counts": raw_counts or {},
        "sanitized_counts": sanitized_counts or {},
    }
    _append_local_trace(trace_payload)

    lf = get_langfuse()
    if lf is None:
        return

    try:
        hallucinations = int(guardrail_stats.get("hallucinations_detected", 0))
        avg_grounding = float(guardrail_stats.get("avg_grounding_score", 0.0))
        warnings = guardrail_stats.get("warnings", [])

        # 1. Output Guardrail Observation (`as_type="guardrail"`) with nested Link A, Link B, Link C spans
        if not eval_dict:
            items_breakdown = guardrail_stats.get("items_breakdown", [])
            with lf.start_as_current_observation(
                name="apply-footprint-guardrails",
                as_type="guardrail",
                input={
                    "ticker": ticker,
                    "raw_counts": raw_counts or {},
                    "items_evaluated": [
                        {"type": it.get("item_type"), "name": it.get("item_name"), "source_type": it.get("source_type")}
                        for it in items_breakdown
                    ],
                },
                level="WARNING" if hallucinations > 0 else "DEFAULT",
                metadata={
                    "ticker": ticker,
                    "agent_name": agent_name,
                    "checks": [
                        "Link A: Payload-to-Quote Entity Binding",
                        "Link B: 2-Sentence Sliding Window Locality",
                        "Link C: Token Weighting & 0.35 Proper-Noun Gate",
                        "URL Whitelist & Third-Party Co-Mention",
                    ],
                },
            ) as g_obs:
                # Emit nested child observations for Link A, Link B, and Link C per item
                for item in items_breakdown:
                    item_label = f"{item.get('item_type')}:{item.get('item_name')}"
                    item_meta = {
                        "item_type": item.get("item_type"),
                        "item_name": item.get("item_name"),
                        "source_type": item.get("source_type"),
                        "source_url": item.get("source_url"),
                        "url_repaired": item.get("url_repaired"),
                        "third_party_comention_passed": item.get("third_party_comention_passed"),
                    }

                    # Link A Child Span
                    la = item.get("link_a", {})
                    obs_a = lf.start_observation(
                        name="verify-link-a-entity-binding",
                        as_type="guardrail",
                        input={"item": item_label, **(la.get("input") or {})},
                        output=la.get("output") or {},
                        level="DEFAULT" if (la.get("output") or {}).get("is_bound", True) else "WARNING",
                        metadata=item_meta,
                    )
                    obs_a.end()

                    # Link B Child Span
                    lb = item.get("link_b", {})
                    obs_b = lf.start_observation(
                        name="evaluate-link-b-window-locality",
                        as_type="guardrail",
                        input={"item": item_label, **(lb.get("input") or {})},
                        output=lb.get("output") or {},
                        metadata=item_meta,
                    )
                    obs_b.end()

                    # Link C Child Span
                    lc = item.get("link_c", {})
                    lc_out = lc.get("output") or {}
                    obs_c = lf.start_observation(
                        name="compute-link-c-weighted-grounding",
                        as_type="guardrail",
                        input={"item": item_label, **(lc.get("input") or {})},
                        output={
                            **lc_out,
                            "final_item_score_after_all_gates": item.get("final_item_score"),
                        },
                        level="WARNING" if float(item.get("final_item_score", 1.0)) < 0.50 else "DEFAULT",
                        metadata=item_meta,
                    )
                    obs_c.end()

                g_obs.update(
                    output={
                        "sanitized_counts": sanitized_counts or {},
                        "avg_grounding_score": avg_grounding,
                        "hallucinations_detected": hallucinations,
                        "warnings": warnings,
                    }
                )
                g_obs.score_trace(
                    name="grounding_score",
                    value=avg_grounding,
                    comment="; ".join(warnings[:3]) or "All claims grounded in primary sources",
                )
                g_obs.score_trace(
                    name="hallucinations_detected",
                    value=float(hallucinations),
                )

        # 2. Quality Evaluator Observation (`as_type="evaluator"`)
        if eval_dict:
            e_obs = lf.start_observation(
                name="evaluate-footprint-quality",
                as_type="evaluator",
                input={
                    "ticker": ticker,
                    "avg_grounding_score": avg_grounding,
                    "hallucinations_detected": hallucinations,
                    "sanitized_counts": sanitized_counts or {},
                },
                output=eval_dict,
                level="WARNING" if eval_dict.get("grade") in ("C", "FAIL") else "DEFAULT",
                metadata={"ticker": ticker, "grade": eval_dict.get("grade")},
            )
            e_obs.score_trace(
                name="faithfulness",
                value=float(eval_dict.get("faithfulness_score", 0.0)),
                comment=f"Grounding check: {eval_dict.get('details', {}).get('grounding_check', '')}",
            )
            e_obs.score_trace(
                name="citation_grounding",
                value=float(eval_dict.get("citation_grounding_score", 0.0)),
                comment=f"Tiered citation check: {eval_dict.get('details', {}).get('citation_check', '')}",
            )
            e_obs.score_trace(
                name="completeness",
                value=float(eval_dict.get("completeness_score", 0.0)),
            )
            e_obs.score_trace(
                name="overall_quality",
                value=float(eval_dict.get("overall_quality_score", 0.0)),
                comment=f"Grade: {eval_dict.get('grade', 'N/A')}",
            )
            e_obs.end()
    except Exception as exc:
        logger.debug(f"[Langfuse] Guardrail/Evaluator observation error: {exc}")
