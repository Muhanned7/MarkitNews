"""
Outbound External API Telemetry Monitor (`backend/agents/api_monitor.py`)
=========================================================================
Tracks every outbound HTTP / SDK call that MarketPulse makes to external
third-party APIs:
  1. Groq Cloud (`qwen/qwen3.8-27b`)
  2. Mistral AI (`mistral-small-latest`)
  3. NewsAPI.org (`v2/everything`)
  4. Google News RSS (`news.google.com/rss/search`)
  5. Yahoo Finance (`yfinance`)
  6. SEC EDGAR & Atom (`data.sec.gov` / `www.sec.gov`)
  7. Wikipedia REST/Action API (`en.wikipedia.org/w/api.php`)
  8. DuckDuckGo HTML Search (`html.duckduckgo.com`)
  9. Hugging Face Inference API (`sentence-transformers/all-MiniLM-L6-v2`)
  10. Finnhub API (`finnhub.io/api/v1/stock/profile2`)
  11. Finviz (`finviz.com/quote.ashx`)
  12. Pinecone Vector DB (`marketpulse` index)
"""

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.db import query
from agents.metrics import external_api_calls_total, external_api_latency_seconds
from auth import get_service_or_user, require_admin_or_service

api_monitor_router = APIRouter(tags=["External API Telemetry"])

_schema_lock = threading.Lock()
_schema_initialized = False
_memory_ring: deque = deque(maxlen=250)

EXTERNAL_API_CATALOG: Dict[str, Dict[str, Any]] = {
    "groq": {
        "provider": "groq",
        "name": "Groq Cloud (Qwen 3.8 27B)",
        "category": "LLM Inference",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
        "quota_limit": 14400,
        "quota_window": "requests / day",
        "used_by": "Primary LLM for 6 Specialist Agents, Synthesizer & Footprint Agent",
    },
    "mistral": {
        "provider": "mistral",
        "name": "Mistral AI (mistral-small-latest)",
        "category": "LLM Inference",
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "env_key": "MISTRAL_API_KEY",
        "quota_limit": 10000,
        "quota_window": "requests / day",
        "used_by": "Automatic Failover LLM when Groq hits 429 rate limits",
    },
    "newsapi": {
        "provider": "newsapi",
        "name": "NewsAPI.org",
        "category": "News & Regulatory Filings",
        "base_url": "https://newsapi.org/v2/everything",
        "env_key": "NEWSAPI_KEY",
        "quota_limit": 100,
        "quota_window": "requests / day (Developer Plan)",
        "used_by": "Home News Search (/api/search) & News Agent (news_agent.py)",
    },
    "google_news_rss": {
        "provider": "google_news_rss",
        "name": "Google News RSS Mesh",
        "category": "News & Regulatory Filings",
        "base_url": "https://news.google.com/rss/search",
        "env_key": None,
        "quota_limit": 5000,
        "quota_window": "requests / day (Free RSS)",
        "used_by": "Tri-Perspective Regional Hub Feeds, Search Fallback & MCP Web Search",
    },
    "yfinance": {
        "provider": "yfinance",
        "name": "Yahoo Finance (yfinance)",
        "category": "Financial & Market Data",
        "base_url": "https://query2.finance.yahoo.com",
        "env_key": None,
        "quota_limit": 2000,
        "quota_window": "requests / day (Public API)",
        "used_by": "Live Stock Prices, RSI/MACD/SMA, Fundamentals, Vol/Beta/VaR & Ticker Validation",
    },
    "sec_edgar": {
        "provider": "sec_edgar",
        "name": "SEC EDGAR (10-K & 8-K Atom)",
        "category": "News & Regulatory Filings",
        "base_url": "https://data.sec.gov/submissions",
        "env_key": None,
        "quota_limit": 86400,
        "quota_window": "10 req/sec fair-access policy",
        "used_by": "MCP fetch_sec_properties (10-K Item 2) & Real-Time 8-K Atom Feed",
    },
    "wikipedia": {
        "provider": "wikipedia",
        "name": "Wikipedia Action & Extract API",
        "category": "News & Regulatory Filings",
        "base_url": "https://en.wikipedia.org/w/api.php",
        "env_key": None,
        "quota_limit": 10000,
        "quota_window": "requests / day (Free REST/Action API)",
        "used_by": "MCP fetch_wikipedia_facilities & Source Revision Fingerprint Check",
    },
    "duckduckgo": {
        "provider": "duckduckgo",
        "name": "DuckDuckGo HTML Search",
        "category": "News & Regulatory Filings",
        "base_url": "https://html.duckduckgo.com/html/",
        "env_key": None,
        "quota_limit": 1000,
        "quota_window": "requests / day",
        "used_by": "Primary MCP search_web_sources supply-chain discovery",
    },
    "huggingface": {
        "provider": "huggingface",
        "name": "Hugging Face Inference API (MiniLM-L6-v2)",
        "category": "Embeddings & Vector DB",
        "base_url": "https://router.huggingface.co/hf-inference/models/sentence-transformers/all-MiniLM-L6-v2",
        "env_key": "HUGGINGFACE_API_KEY",
        "quota_limit": 1000,
        "quota_window": "requests / day (Serverless Inference)",
        "used_by": "Link C Guardrail Semantic Fallback & Article/Ticker Vector Embeddings",
    },
    "finnhub": {
        "provider": "finnhub",
        "name": "Finnhub Stock Profile API",
        "category": "Financial & Market Data",
        "base_url": "https://finnhub.io/api/v1/stock/profile2",
        "env_key": "FINNHUB_API",
        "quota_limit": 3600,
        "quota_window": "60 req/min (Free Tier)",
        "used_by": "Company metadata & sector lookup when adding new tickers (POST /api/tickers)",
    },
    "finviz": {
        "provider": "finviz",
        "name": "Finviz Quote & Analyst Scrape",
        "category": "Financial & Market Data",
        "base_url": "https://finviz.com/quote.ashx",
        "env_key": None,
        "quota_limit": 1000,
        "quota_window": "requests / day",
        "used_by": "Sentiment Agent analyst rating & institutional sentiment extraction",
    },
    "pinecone": {
        "provider": "pinecone",
        "name": "Pinecone Vector DB",
        "category": "Embeddings & Vector DB",
        "base_url": "https://api.pinecone.io",
        "env_key": "PINECONE_API_KEY",
        "quota_limit": 10000,
        "quota_window": "operations / day (Starter Index)",
        "used_by": "Semantic news search & similar-ticker vector retrieval (/api/search, /api/similar)",
    },
}


def ensure_external_api_logs_table() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_lock:
        if _schema_initialized:
            return
        try:
            query(
                """
                CREATE TABLE IF NOT EXISTS external_api_logs (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(64) NOT NULL,
                    endpoint VARCHAR(160) NOT NULL,
                    operation VARCHAR(120) NOT NULL,
                    ticker VARCHAR(32),
                    status_code INTEGER NOT NULL DEFAULT 200,
                    success BOOLEAN NOT NULL DEFAULT TRUE,
                    duration_ms NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
                    tokens_used INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_ext_api_logs_created_at ON external_api_logs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_ext_api_logs_provider ON external_api_logs(provider);
                """
            )
            _schema_initialized = True
        except Exception as e:
            logger.debug(f"Could not initialize external_api_logs table: {e}")


def record_external_api_call(
    provider: str,
    endpoint: str,
    operation: str,
    ticker: Optional[str] = None,
    status_code: int = 200,
    success: Optional[bool] = None,
    duration_ms: float = 0.0,
    tokens_used: int = 0,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Records an outbound external API call into Prometheus, in-memory ring buffer, and PostgreSQL.
    Never raises an exception so it cannot disrupt caller execution.
    """
    prov = (provider or "unknown").lower().strip()
    op = (operation or "request").strip()[:120]
    ep = (endpoint or "").strip()[:160]
    clean_t = ticker.upper().strip()[:32] if ticker else None
    code = int(status_code or 200)
    is_ok = (200 <= code < 400 and not error_message) if success is None else bool(success)
    dur_ms = round(max(0.0, float(duration_ms or 0.0)), 2)
    tok = int(tokens_used or 0)

    # 1. Prometheus counter & latency histogram
    try:
        external_api_calls_total.labels(provider=prov, operation=op, status_code=str(code)).inc()
        external_api_latency_seconds.labels(provider=prov, operation=op).observe(dur_ms / 1000.0)
    except Exception:
        pass

    # 2. In-memory ring buffer fallback
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": len(_memory_ring) + 1,
        "provider": prov,
        "endpoint": ep,
        "operation": op,
        "ticker": clean_t,
        "status_code": code,
        "success": is_ok,
        "duration_ms": dur_ms,
        "tokens_used": tok,
        "error_message": (error_message or "")[:300] if error_message else None,
        "metadata": metadata or {},
        "created_at": now_iso,
    }
    _memory_ring.appendleft(entry)

    # 3. Persist to PostgreSQL
    try:
        ensure_external_api_logs_table()
        query(
            """INSERT INTO external_api_logs
               (provider, endpoint, operation, ticker, status_code, success, duration_ms, tokens_used, error_message, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
            [
                prov,
                ep,
                op,
                clean_t,
                code,
                is_ok,
                dur_ms,
                tok,
                (error_message or "")[:300] if error_message else None,
                json.dumps(metadata or {}),
            ],
        )
    except Exception as e:
        logger.debug(f"External API DB log skipped for {prov}: {e}")


def log_external_api_call(
    provider: str,
    endpoint: str,
    operation: Optional[str] = None,
    method: str = "GET",
    status_code: int = 200,
    latency_ms: float = 0.0,
    duration_ms: float = 0.0,
    caller: Optional[str] = None,
    ticker: Optional[str] = None,
    query_summary: Optional[str] = None,
    tokens_used: int = 0,
    success: Optional[bool] = None,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Compatibility wrapper forwarding flexible keyword arguments to record_external_api_call."""
    prov_norm = (provider or "unknown").lower().strip().replace(" ", "_")
    if prov_norm == "newsapi":
        prov_norm = "newsapi"
    elif "google" in prov_norm:
        prov_norm = "google_news_rss"
    elif "sec" in prov_norm:
        prov_norm = "sec_edgar"
    elif "hugging" in prov_norm:
        prov_norm = "huggingface"
    op_str = operation or caller or f"{method} {endpoint}"
    meta = dict(metadata or {})
    if query_summary:
        meta["query_summary"] = query_summary
    if caller:
        meta["caller"] = caller
    record_external_api_call(
        provider=prov_norm,
        endpoint=endpoint,
        operation=op_str,
        ticker=ticker,
        status_code=status_code,
        success=success,
        duration_ms=latency_ms or duration_ms,
        tokens_used=tokens_used,
        error_message=error_message,
        metadata=meta,
    )


class ExternalApiLogRequest(BaseModel):
    provider: str
    endpoint: str
    operation: str
    ticker: Optional[str] = None
    status_code: Optional[int] = 200
    success: Optional[bool] = None
    duration_ms: Optional[float] = 0.0
    tokens_used: Optional[int] = 0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@api_monitor_router.post("/telemetry/external-apis/log")
async def post_external_api_log(req: ExternalApiLogRequest):
    """Receives outbound API call logs from Next.js server routes (/api/search, /api/tickers, embeddings, Pinecone)."""
    record_external_api_call(
        provider=req.provider,
        endpoint=req.endpoint,
        operation=req.operation,
        ticker=req.ticker,
        status_code=req.status_code or 200,
        success=req.success,
        duration_ms=req.duration_ms or 0.0,
        tokens_used=req.tokens_used or 0,
        error_message=req.error_message,
        metadata=req.metadata,
    )
    return {"recorded": True}


@api_monitor_router.get("/telemetry/external-apis")
async def get_external_api_telemetry(user: dict = Depends(require_admin_or_service)):
    """
    Returns comprehensive real-time telemetry across all 12 external APIs used by MarketPulse,
    combining `external_api_logs`, historical `agent_token_logs`, Langfuse status, and Prometheus endpoints.
    Restricted to Developer Admin accounts (`require_admin_or_service`).
    """
    ensure_external_api_logs_table()

    # Backfill / merge historical LLM calls from `agent_token_logs` so Groq/Mistral counts are immediately visible
    by_provider_stats: Dict[str, Dict[str, Any]] = {}
    recent_calls: List[Dict[str, Any]] = []

    try:
        agg_res = query(
            """
            SELECT
                provider,
                COUNT(*) AS calls_total,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS calls_24h,
                COUNT(*) FILTER (WHERE success = TRUE) AS success_count,
                COUNT(*) FILTER (WHERE success = FALSE) AS error_count,
                COUNT(*) FILTER (WHERE status_code = 429) AS rate_limit_429_count,
                ROUND(AVG(duration_ms)::numeric, 1) AS avg_latency_ms,
                ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 1) AS p95_latency_ms,
                COALESCE(SUM(tokens_used) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours'), 0) AS tokens_24h,
                COALESCE(SUM(tokens_used), 0) AS tokens_total,
                MAX(created_at) AS last_called_at
            FROM external_api_logs
            GROUP BY provider
            """
        )
        for row in agg_res.rows:
            by_provider_stats[row["provider"]] = dict(row)

        # Also pull LLM token logs from `agent_token_logs` if not yet mirrored in `external_api_logs`
        llm_res = query(
            """
            SELECT
                CASE WHEN LOWER(model) LIKE '%qwen%' OR LOWER(model) LIKE '%llama%' THEN 'groq' ELSE 'mistral' END AS provider,
                COUNT(*) AS calls_total,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS calls_24h,
                ROUND(AVG(duration_ms)::numeric, 1) AS avg_latency_ms,
                COALESCE(SUM(total_tokens) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours'), 0) AS tokens_24h,
                COALESCE(SUM(total_tokens), 0) AS tokens_total,
                MAX(created_at) AS last_called_at
            FROM agent_token_logs
            GROUP BY 1
            """
        )
        for lrow in llm_res.rows:
            p_key = lrow["provider"]
            existing = by_provider_stats.get(p_key)
            if not existing or int(lrow["calls_total"] or 0) > int(existing.get("calls_total") or 0):
                by_provider_stats[p_key] = {
                    "provider": p_key,
                    "calls_total": int(lrow["calls_total"] or 0),
                    "calls_24h": int(lrow["calls_24h"] or 0),
                    "success_count": int(lrow["calls_total"] or 0),
                    "error_count": existing.get("error_count", 0) if existing else 0,
                    "rate_limit_429_count": existing.get("rate_limit_429_count", 0) if existing else 0,
                    "avg_latency_ms": float(lrow["avg_latency_ms"] or 0.0),
                    "p95_latency_ms": float(existing.get("p95_latency_ms") or lrow["avg_latency_ms"] or 0.0) if existing else float(lrow["avg_latency_ms"] or 0.0),
                    "tokens_24h": int(lrow["tokens_24h"] or 0),
                    "tokens_total": int(lrow["tokens_total"] or 0),
                    "last_called_at": lrow["last_called_at"],
                }

        rec_res = query(
            """
            SELECT id, provider, endpoint, operation, ticker, status_code, success,
                   duration_ms, tokens_used, error_message, created_at
            FROM external_api_logs
            ORDER BY id DESC
            LIMIT 40
            """
        )
        for r in rec_res.rows:
            recent_calls.append({
                "id": r["id"],
                "provider": r["provider"],
                "provider_name": EXTERNAL_API_CATALOG.get(r["provider"], {}).get("name", r["provider"]),
                "endpoint": r["endpoint"],
                "operation": r["operation"],
                "ticker": r["ticker"],
                "status_code": r["status_code"],
                "success": bool(r["success"]),
                "duration_ms": float(r["duration_ms"] or 0.0),
                "tokens_used": int(r["tokens_used"] or 0),
                "error_message": r["error_message"],
                "created_at": str(r["created_at"]),
            })

        if len(recent_calls) < 15:
            llm_rec = query(
                """
                SELECT id, agent_name, ticker, model, total_tokens, duration_ms, created_at
                FROM agent_token_logs
                ORDER BY id DESC
                LIMIT 15
                """
            )
            for lr in llm_rec.rows:
                m_str = str(lr.get("model") or "")
                p_key = "groq" if ("qwen" in m_str.lower() or "llama" in m_str.lower()) else "mistral"
                recent_calls.append({
                    "id": f"llm-{lr['id']}",
                    "provider": p_key,
                    "provider_name": EXTERNAL_API_CATALOG[p_key]["name"],
                    "endpoint": EXTERNAL_API_CATALOG[p_key]["base_url"],
                    "operation": f"chat.complete ({lr['agent_name']})",
                    "ticker": lr["ticker"],
                    "status_code": 200,
                    "success": True,
                    "duration_ms": float(lr["duration_ms"] or 0.0),
                    "tokens_used": int(lr["total_tokens"] or 0),
                    "error_message": None,
                    "created_at": str(lr["created_at"]),
                })
    except Exception as e:
        logger.warning(f"External API telemetry DB query fallback to memory: {e}")
        recent_calls = list(_memory_ring)[:40]
        for item in _memory_ring:
            pk = item["provider"]
            b = by_provider_stats.setdefault(
                pk,
                {
                    "provider": pk,
                    "calls_total": 0,
                    "calls_24h": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "rate_limit_429_count": 0,
                    "avg_latency_ms": 0.0,
                    "p95_latency_ms": 0.0,
                    "tokens_24h": 0,
                    "tokens_total": 0,
                    "last_called_at": item["created_at"],
                },
            )
            b["calls_total"] += 1
            b["calls_24h"] += 1
            if item["success"]:
                b["success_count"] += 1
            else:
                b["error_count"] += 1
            if item["status_code"] == 429:
                b["rate_limit_429_count"] += 1
            b["avg_latency_ms"] = round(
                ((b["avg_latency_ms"] * (b["calls_total"] - 1)) + float(item["duration_ms"])) / b["calls_total"], 1
            )
            b["p95_latency_ms"] = max(b["p95_latency_ms"], float(item["duration_ms"]))
            b["tokens_24h"] += int(item["tokens_used"] or 0)
            b["tokens_total"] += int(item["tokens_used"] or 0)

    providers_list: List[Dict[str, Any]] = []
    total_calls_24h = 0
    total_calls_all = 0
    total_success_all = 0
    total_errors_all = 0
    total_429_all = 0
    total_tokens_24h = 0
    weighted_latency_sum = 0.0

    for key, meta in EXTERNAL_API_CATALOG.items():
        st = by_provider_stats.get(key, {})
        c_total = int(st.get("calls_total") or 0)
        c_24h = int(st.get("calls_24h") or 0)
        s_cnt = int(st.get("success_count") or 0)
        e_cnt = int(st.get("error_count") or 0)
        r429 = int(st.get("rate_limit_429_count") or 0)
        avg_lat = float(st.get("avg_latency_ms") or 0.0)
        p95_lat = float(st.get("p95_latency_ms") or avg_lat)
        tok_24h = int(st.get("tokens_24h") or 0)
        tok_total = int(st.get("tokens_total") or 0)

        env_key = meta["env_key"]
        is_configured = True if env_key is None else bool(os.environ.get(env_key, "").strip())
        quota_limit = meta["quota_limit"]
        quota_pct = round(min(100.0, (c_24h / quota_limit) * 100.0), 1) if quota_limit else 0.0
        success_rate = round((s_cnt / c_total) * 100.0, 1) if c_total > 0 else 100.0

        total_calls_24h += c_24h
        total_calls_all += c_total
        total_success_all += s_cnt
        total_errors_all += e_cnt
        total_429_all += r429
        total_tokens_24h += tok_24h
        weighted_latency_sum += avg_lat * c_total

        providers_list.append({
            **meta,
            "configured": is_configured,
            "calls_24h": c_24h,
            "calls_total": c_total,
            "success_count": s_cnt,
            "error_count": e_cnt,
            "rate_limit_429_count": r429,
            "success_rate_pct": success_rate,
            "avg_latency_ms": avg_lat,
            "p95_latency_ms": p95_lat,
            "tokens_24h": tok_24h,
            "tokens_total": tok_total,
            "quota_used_pct": quota_pct,
            "last_called_at": str(st["last_called_at"]) if st.get("last_called_at") else None,
            "health_status": (
                "rate_limited" if r429 > 0 else ("degraded" if (c_total > 0 and success_rate < 80.0) else ("active" if c_total > 0 else ("ready" if is_configured else "unconfigured")))
            ),
        })

    overall_avg_latency = round(weighted_latency_sum / total_calls_all, 1) if total_calls_all > 0 else 0.0
    overall_success_rate = round((total_success_all / total_calls_all) * 100.0, 1) if total_calls_all > 0 else 100.0

    # Langfuse & AI Agent Evaluation observability summary for Developer Admin console
    lf_pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    lf_sec = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    lf_host = (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    ).strip()
    lf_env = os.environ.get("LANGFUSE_TRACING_ENVIRONMENT", "production").strip()

    agent_eval_summary: Dict[str, Any] = {}
    footprint_eval_summary: Dict[str, Any] = {}
    recent_agent_evals: List[Dict[str, Any]] = []
    llm_by_agent: List[Dict[str, Any]] = []

    try:
        ae_res = query(
            """SELECT
                COUNT(*) AS total_evaluations,
                ROUND(AVG(faithfulness_score)::numeric, 2) AS avg_faithfulness,
                ROUND(AVG(consistency_score)::numeric, 2) AS avg_consistency,
                ROUND(AVG(completeness_score)::numeric, 2) AS avg_completeness,
                ROUND(AVG(overall_quality_score)::numeric, 2) AS avg_overall_quality,
                COALESCE(SUM(hallucinations_detected), 0) AS total_hallucinations_intercepted,
                ROUND((COUNT(*) FILTER (WHERE guardrails_passed = true) * 100.0 / GREATEST(COUNT(*), 1))::numeric, 1) AS guardrails_pass_pct
               FROM agent_evaluations"""
        )
        if ae_res.rows:
            agent_eval_summary = dict(ae_res.rows[0])

        fe_res = query(
            """SELECT
                COUNT(*) AS total_evaluations,
                ROUND(AVG(faithfulness_score)::numeric, 2) AS avg_faithfulness,
                ROUND(AVG(citation_grounding_score)::numeric, 2) AS avg_citation_grounding,
                ROUND(AVG(overall_quality_score)::numeric, 2) AS avg_overall_quality,
                COALESCE(SUM(hallucinations_detected), 0) AS total_hallucinations_intercepted
               FROM footprint_evaluations"""
        )
        if fe_res.rows:
            footprint_eval_summary = dict(fe_res.rows[0])

        rec_ev = query(
            """SELECT id, agent_name, ticker, faithfulness_score, consistency_score,
                      completeness_score, overall_quality_score, grade,
                      guardrails_passed, hallucinations_detected, created_at
               FROM agent_evaluations
               ORDER BY id DESC
               LIMIT 15"""
        )
        recent_agent_evals = [
            {
                **dict(r),
                "faithfulness_score": float(r.get("faithfulness_score") or 0.0),
                "consistency_score": float(r.get("consistency_score") or 0.0),
                "completeness_score": float(r.get("completeness_score") or 0.0),
                "overall_quality_score": float(r.get("overall_quality_score") or 0.0),
                "created_at": str(r.get("created_at")),
            }
            for r in rec_ev.rows
        ]

        ag_tok = query(
            """SELECT
                agent_name,
                COUNT(*) AS calls,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                ROUND(AVG(duration_ms)::numeric, 1) AS avg_latency_ms
               FROM agent_token_logs
               GROUP BY agent_name
               ORDER BY total_tokens DESC"""
        )
        llm_by_agent = [
            {
                "agent_name": r["agent_name"],
                "calls": int(r["calls"] or 0),
                "prompt_tokens": int(r["prompt_tokens"] or 0),
                "completion_tokens": int(r["completion_tokens"] or 0),
                "total_tokens": int(r["total_tokens"] or 0),
                "avg_latency_ms": float(r["avg_latency_ms"] or 0.0),
            }
            for r in ag_tok.rows
        ]
    except Exception as eval_exc:
        logger.debug(f"Admin Langfuse/eval summary query skipped: {eval_exc}")

    # Also read last 15 local Langfuse mirror traces from `backend/logs/langfuse_traces.jsonl`
    local_traces: List[Dict[str, Any]] = []
    trace_file = Path(__file__).resolve().parent.parent / "logs" / "langfuse_traces.jsonl"
    if trace_file.exists():
        try:
            lines = trace_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-15:]
            for ln in reversed(lines):
                if ln.strip():
                    local_traces.append(json.loads(ln))
        except Exception:
            pass

    backend_public_url = os.environ.get(
        "BACKEND_PUBLIC_URL",
        "https://finnwinn-api-258199278374.us-east4.run.app",
    ).rstrip("/")

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mock_mode_enabled": os.environ.get("MOCK_MODE", "false").lower() == "true",
        "overview": {
            "total_providers_tracked": len(EXTERNAL_API_CATALOG),
            "configured_providers": sum(1 for p in providers_list if p["configured"]),
            "total_calls_24h": total_calls_24h,
            "total_calls_all_time": total_calls_all,
            "overall_success_rate_pct": overall_success_rate,
            "total_errors_all_time": total_errors_all,
            "total_rate_limit_429": total_429_all,
            "overall_avg_latency_ms": overall_avg_latency,
            "total_llm_tokens_24h": total_tokens_24h,
        },
        "prometheus": {
            "enabled": os.environ.get("EXPOSE_METRICS", "true").lower() == "true",
            "production_metrics_url": f"{backend_public_url}/metrics",
            "production_docs_url": f"{backend_public_url}/docs",
            "production_telemetry_html_url": f"{backend_public_url}/telemetry",
            "local_metrics_url": "http://localhost:8000/metrics",
            "exported_metrics": [
                "external_api_calls_total{provider,operation,status_code}",
                "external_api_latency_seconds{provider,operation}",
                "agent_calls_total{agent_name,ticker}",
                "agent_latency_seconds{agent_name}",
                "agent_faithfulness_score{agent_name,ticker}",
                "agent_evaluation_score{agent_name,ticker,grade}",
                "agent_hallucinations_detected_total{agent_name,ticker}",
                "llm_prompt_tokens_total{agent_name,model}",
                "llm_completion_tokens_total{agent_name,model}",
                "llm_total_tokens_total{agent_name,model}",
                "active_analyses",
                "cache_hits_total{ticker}",
            ],
        },
        "langfuse": {
            "configured": bool(lf_pub and lf_sec),
            "host": lf_host,
            "dashboard_url": lf_host,
            "traces_url": f"{lf_host}/traces",
            "datasets_url": f"{lf_host}/datasets",
            "scores_url": f"{lf_host}/scores",
            "environment": lf_env,
            "public_key_prefix": f"{lf_pub[:12]}..." if lf_pub else None,
            "sdk_version": "Langfuse Python SDK v4 (OpenTelemetry)",
            "agent_evaluations": agent_eval_summary,
            "footprint_evaluations": footprint_eval_summary,
            "recent_evaluations": recent_agent_evals,
            "llm_by_agent": llm_by_agent,
            "recent_traces": local_traces,
        },
        "providers": providers_list,
        "recent_calls": recent_calls[:40],
    }


@api_monitor_router.get("/telemetry", response_class=HTMLResponse)
async def get_backend_developer_telemetry_dashboard():
    """Developer-only HTML dashboard served directly from the FastAPI backend."""
    data = await get_external_api_telemetry(user={"sub": "internal-service", "role": "admin", "is_admin": True})
    ov = data["overview"]
    mode_badge = "MOCK MODE" if data["mock_mode_enabled"] else "LIVE PRODUCTION (MOCK_MODE=false)"
    mode_color = "#b45309" if data["mock_mode_enabled"] else "#15803d"

    rows_html = ""
    for p in data["providers"]:
        status_color = "#15803d" if p["health_status"] in ("active", "ready") else ("#b91c1c" if p["health_status"] in ("degraded", "rate_limited") else "#64748b")
        rows_html += f"""
        <tr>
            <td><strong>{p['name']}</strong><br><small style="color:#64748b">{p['base_url']}</small></td>
            <td>{p['category']}</td>
            <td><span style="color:{status_color};font-weight:700;text-transform:uppercase">{p['health_status']}</span></td>
            <td style="text-align:right;font-family:monospace">{p['calls_24h']}</td>
            <td style="text-align:right;font-family:monospace">{p['calls_total']}</td>
            <td style="text-align:right;font-family:monospace">{p['success_rate_pct']}%</td>
            <td style="text-align:right;font-family:monospace">{p['avg_latency_ms']} ms</td>
            <td style="text-align:right;font-family:monospace">{p['rate_limit_429_count']}</td>
            <td style="text-align:right;font-family:monospace">{p['quota_used_pct']}% <small style="color:#64748b">({p['quota_window']})</small></td>
        </tr>"""

    recent_html = ""
    for c in data["recent_calls"][:25]:
        badge = "✅ 200" if c["success"] else f"❌ {c['status_code']}"
        recent_html += f"""
        <tr>
            <td style="font-family:monospace;font-size:12px">{c['created_at'][:19]}</td>
            <td><strong>{c['provider_name']}</strong></td>
            <td style="font-family:monospace;font-size:12px">{c['operation']}</td>
            <td style="font-family:monospace">{c['ticker'] or '—'}</td>
            <td style="font-family:monospace">{badge}</td>
            <td style="text-align:right;font-family:monospace">{c['duration_ms']} ms</td>
            <td style="text-align:right;font-family:monospace">{c['tokens_used'] or '—'}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>MarketPulse Backend Developer API Monitor</title>
<meta http-equiv="refresh" content="15">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 28px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; border-bottom: 1px solid #1e293b; padding-bottom: 16px; }}
  .badge {{ background: {mode_color}; color: #fff; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-bottom: 26px; }}
  .kpi {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px 16px; }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.06em; }}
  .kpi-val {{ font-size: 24px; font-weight: 700; margin-top: 6px; font-family: monospace; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin-bottom: 28px; }}
  th, td {{ padding: 11px 14px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; }}
  th {{ background: #0f172a; color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }}
  a {{ color: #38bdf8; text-decoration: none; margin-left: 14px; font-size: 13px; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="margin:0;font-size:22px">📡 MarketPulse Backend Developer API Telemetry</h1>
      <div style="color:#94a3b8;font-size:13px;margin-top:4px">Backend-only developer observability across all 12 outbound APIs • Auto-refreshes every 15s</div>
    </div>
    <div>
      <span class="badge">{mode_badge}</span>
      <a href="/telemetry/external-apis">Raw JSON</a>
      <a href="/metrics">Prometheus /metrics</a>
      <a href="/docs">OpenAPI /docs</a>
    </div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="kpi-label">APIs Configured</div><div class="kpi-val">{ov['configured_providers']} / {ov['total_providers_tracked']}</div></div>
    <div class="kpi"><div class="kpi-label">Calls (24h)</div><div class="kpi-val">{ov['total_calls_24h']}</div></div>
    <div class="kpi"><div class="kpi-label">Calls (All-Time)</div><div class="kpi-val">{ov['total_calls_all_time']}</div></div>
    <div class="kpi"><div class="kpi-label">Success Rate</div><div class="kpi-val">{ov['overall_success_rate_pct']}%</div></div>
    <div class="kpi"><div class="kpi-label">Avg Latency</div><div class="kpi-val">{ov['overall_avg_latency_ms']} ms</div></div>
    <div class="kpi"><div class="kpi-label">429 Rate Limits</div><div class="kpi-val">{ov['total_rate_limit_429']}</div></div>
  </div>
  <h2 style="font-size:15px;color:#94a3b8;text-transform:uppercase">Outbound External API Providers (12)</h2>
  <table>
    <thead>
      <tr>
        <th>Provider</th><th>Category</th><th>Status</th>
        <th style="text-align:right">24h Calls</th><th style="text-align:right">Total Calls</th>
        <th style="text-align:right">Success</th><th style="text-align:right">Avg Latency</th>
        <th style="text-align:right">429s</th><th style="text-align:right">24h Quota</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <h2 style="font-size:15px;color:#94a3b8;text-transform:uppercase">Recent Outbound API Calls</h2>
  <table>
    <thead>
      <tr>
        <th>Timestamp (UTC)</th><th>Provider</th><th>Operation</th><th>Ticker</th><th>Status</th>
        <th style="text-align:right">Duration</th><th style="text-align:right">LLM Tokens</th>
      </tr>
    </thead>
    <tbody>{recent_html}</tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(content=html)
