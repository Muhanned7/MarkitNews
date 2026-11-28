from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List, Union
import asyncio
import hmac
import json
from auth import hash_password, verify_password, create_token, get_current_user, get_service_or_user, is_admin_email, require_admin_or_service
from agents.db import query
import os
import re

load_dotenv()


from agents.news_agent import news_agent
from agents.sentiment_agent import sentiment_agent
from agents.technical_agent import technical_agent
from agents.fundamentals_agent import fundamentals_agent
from agents.equity_reasearch_agent import equity_research_agent
from agents.risk_agent import risk_agent
from agents.contradiction_agent import contradiction_agent
from agents.client import client
from agents.guardrails import guardrail_equity_research
from agents.evaluator import evaluate_agent_output
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger
from agents.metrics import active_analyses, cache_hits
from datetime import datetime, timedelta
import sys
import yfinance as yf
from ingestion.footprint_agent import research_company_footprint, generate_perspective_queries
from ingestion.adapters.geo_feed_adapter import fetch_tri_perspective_mesh
#client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])


_expose_public_docs = os.environ.get("EXPOSE_BACKEND_DOCS", "false").strip().lower() == "true"
app = FastAPI(
    title="MarketPulse Backend",
    docs_url="/docs" if _expose_public_docs else None,
    redoc_url="/redoc" if _expose_public_docs else None,
    openapi_url="/openapi.json" if _expose_public_docs else None,
)

# Logging setup
logger.remove()
logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="INFO")

# Prometheus metrics collected in-process for the Developer Admin UI (no public /metrics exposure by default)
_instrumentator = Instrumentator().instrument(app)
if os.environ.get("EXPOSE_METRICS", "false").strip().lower() == "true":
    _instrumentator.expose(app)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_URL", "https://finnwinn-web-258199278374.us-east4.run.app").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def restrict_to_frontend_proxy(request: Request, call_next):
    """
    Enforces that all traffic to the backend API comes strictly from the Next.js frontend proxy
    (authenticated via `X-Service-Key`). Direct browser or external requests to the backend
    URL are rejected with 403 Forbidden.
    """
    expected_key = (os.environ.get("INTERNAL_SERVICE_KEY") or "").strip()
    enforce_gate = os.environ.get("ENFORCE_FRONTEND_ONLY", "true").strip().lower() == "true"
    if expected_key and enforce_gate:
        provided_key = (request.headers.get("x-service-key") or "").strip()
        is_valid = False
        if provided_key:
            try:
                is_valid = hmac.compare_digest(
                    provided_key.encode("utf-8"),
                    expected_key.encode("utf-8"),
                )
            except Exception:
                is_valid = False
        if not is_valid:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Direct access to the backend API is disabled. All requests must pass through the MarketPulse web application."
                },
            )
    return await call_next(request)

from agents.portfolio_router import portfolio_router
from agents.risk_router import risk_router
from agents.qra_router import qra_router
from agents.api_monitor import api_monitor_router, record_external_api_call
from agents.billing_router import (
    billing_router,
    check_tokens_and_tier,
    current_billing_user_id,
    deduct_user_tokens,
    get_or_create_wallet,
    sanitize_public_membership,
)
from agents.portfolio_engine import record_analysis_snapshot
app.include_router(portfolio_router)
app.include_router(risk_router)
# Research/screener routes were unauthenticated; the Next.js proxies already send the service key.
app.include_router(qra_router, dependencies=[Depends(get_service_or_user)])
app.include_router(billing_router)
app.include_router(api_monitor_router)


def ensure_developer_admin_account() -> None:
    """
    Idempotently ensures the Developer Admin table column (`users.role`) and default
    developer admin account (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) exist in PostgreSQL
    with an active Pro Package wallet for production monitoring.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@marketpulse.ai").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "AdminPulse2026!").strip()
    try:
        query("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'user'")
        existing = query("SELECT id, email, role FROM users WHERE LOWER(email) = LOWER(%s)", [admin_email])
        if existing.rows:
            admin_id = existing.rows[0]["id"]
            if existing.rows[0].get("role") != "admin":
                query("UPDATE users SET role = 'admin' WHERE id = %s", [admin_id])
        else:
            hashed_pw = hash_password(admin_password)
            ins = query(
                "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'admin') RETURNING id",
                [admin_email, hashed_pw],
            )
            admin_id = ins.rows[0]["id"] if ins.rows else None

        if admin_id is not None:
            w = get_or_create_wallet(int(admin_id))
            if w.get("tier") != "pro" or int(w.get("token_balance", 0)) < 1_000_000:
                query(
                    """UPDATE user_wallets
                       SET tier = 'pro',
                           token_balance = GREATEST(token_balance, 5000000),
                           monthly_allowance = 5000000
                       WHERE user_id = %s""",
                    [int(admin_id)],
                )
        logger.info(f"[Admin Bootstrap] Developer Admin account ready: {admin_email}")
    except Exception as exc:
        logger.debug(f"[Admin Bootstrap] Skipped DB admin bootstrap: {exc}")


@app.on_event("startup")
async def _on_startup_bootstrap_admin():
    await asyncio.to_thread(ensure_developer_admin_account)


class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

@app.post("/auth/register")
async def register(body: RegisterRequest):
    email = (body.email or "").strip()
    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if len(body.password.encode('utf-8')) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 characters or less")
    
    hashed = hash_password(body.password)
    try:
        result = await asyncio.to_thread(
            query,
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
            [email, hashed]
        )
        user = result.rows[0]
        role = "admin" if is_admin_email(user["email"]) else "user"
        wallet = await asyncio.to_thread(get_or_create_wallet, user["id"])
        token = create_token(user["id"], user["email"], role=role)
        return {
            "token": token,
            "email": user["email"],
            "role": role,
            "is_admin": role == "admin",
            "membership": sanitize_public_membership(wallet),
        }
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "duplicate" in err_str:
            raise HTTPException(status_code=400, detail="Email already exists")
        logger.error(f"Registration database error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during registration")

@app.post("/auth/login")
async def login(body: LoginRequest):
    email = (body.email or "").strip()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    result = await asyncio.to_thread(
        query,
        "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)",
        [email]
    )
    if not result.rows:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = result.rows[0]
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    db_role = user.get("role")
    role = "admin" if (db_role == "admin" or is_admin_email(user["email"])) else "user"
    token = create_token(user["id"], user["email"], role=role)
    return {
        "token": token,
        "email": user["email"],
        "user_id": user["id"],
        "role": role,
        "is_admin": role == "admin",
    }

@app.get("/auth/me")
async def me(user=Depends(get_current_user)):
    role = "admin" if (user.get("role") == "admin" or user.get("is_admin") or is_admin_email(user.get("email"))) else "user"
    return {**user, "role": role, "is_admin": role == "admin"}


class WatchlistAddRequest(BaseModel):
    symbol: str

class WatchlistDeleteRequest(BaseModel):
    symbol: Optional[str] = None

class TickerCreateRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None

class ArticleItem(BaseModel):
    id: str
    headline: str
    summary: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    published: Optional[str] = None
    score: Optional[float] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    sectors: Optional[list] = None
    query: Optional[list] = None

class ArticlesBatchRequest(BaseModel):
    articles: list[ArticleItem]

class SearchLogRequest(BaseModel):
    query: Union[list, str]
    results_count: int


@app.get("/watchlist")
async def get_watchlist(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    result = await asyncio.to_thread(
        query,
        "SELECT * FROM watchlist WHERE user_id = %s",
        [str(user_id)]
    )
    return {"tickers": result.rows}

@app.post("/watchlist")
async def add_watchlist(body: WatchlistAddRequest, user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    symbol = body.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    await asyncio.to_thread(
        query,
        "INSERT INTO watchlist (ticker, user_id) VALUES (%s, %s) ON CONFLICT (user_id, ticker) DO NOTHING",
        [symbol, str(user_id)]
    )
    return {
        "message": "Ticker added to watchlist successfully",
        "ticker": {"symbol": symbol}
    }

@app.delete("/watchlist/{ticker}")
async def delete_watchlist_path(ticker: str, user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    await asyncio.to_thread(
        query,
        "DELETE FROM watchlist WHERE ticker = %s AND user_id = %s",
        [ticker.upper().strip(), str(user_id)]
    )
    return {"message": "The ticker was deleted successfully."}

@app.delete("/watchlist")
async def delete_watchlist(body: Optional[WatchlistDeleteRequest] = None, symbol: Optional[str] = None, user: dict = Depends(get_current_user)):
    target_symbol = (body.symbol if body and body.symbol else symbol)
    if not target_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    user_id = user["sub"]
    await asyncio.to_thread(
        query,
        "DELETE FROM watchlist WHERE ticker = %s AND user_id = %s",
        [target_symbol.upper().strip(), str(user_id)]
    )
    return {"message": "The ticker was deleted successfully."}

@app.get("/watchlist/tickers")
async def get_all_watchlist_tickers(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    result = await asyncio.to_thread(
        query,
        "SELECT DISTINCT ticker FROM watchlist WHERE user_id = %s",
        [str(user_id)]
    )
    return {"tickers": [row["ticker"] for row in result.rows]}

@app.get("/tickers")
async def get_tickers():
    result = await asyncio.to_thread(
        query,
        "SELECT * FROM tickers ORDER BY created_at DESC"
    )
    return {"tickers": result.rows}

@app.post("/tickers")
async def create_ticker(body: TickerCreateRequest, user: dict = Depends(get_service_or_user)):
    await asyncio.to_thread(
        query,
        """INSERT INTO tickers (symbol, name, description, sector, industry)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (symbol) DO NOTHING""",
        [body.symbol.upper().strip(), body.name, body.description, body.sector, body.industry]
    )
    return {"message": f"Ticker {body.symbol} processed"}

@app.patch("/tickers/{symbol}/embedding")
async def update_ticker_embedding(symbol: str, user: dict = Depends(get_service_or_user)):
    await asyncio.to_thread(
        query,
        "UPDATE tickers SET embedding_stored = TRUE WHERE symbol = %s",
        [symbol.upper().strip()]
    )
    return {"message": f"Embedding status updated for {symbol}"}

@app.post("/articles")
async def save_articles(body: ArticlesBatchRequest, user: dict = Depends(get_service_or_user)):
    for art in body.articles:
        await asyncio.to_thread(
            query,
            """INSERT INTO articles 
               (id, headline, summary, source, url, published, score, sentiment, confidence, rationale, sectors, query)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            [
                art.id, art.headline, art.summary, art.source, art.url,
                art.published, art.score, art.sentiment, art.confidence,
                art.rationale, art.sectors, art.query
            ]
        )
    return {"message": f"Saved {len(body.articles)} articles"}

@app.post("/searches")
async def log_search(body: SearchLogRequest, user: dict = Depends(get_service_or_user)):
    queries = body.query if isinstance(body.query, list) else [body.query]
    await asyncio.to_thread(
        query,
        "INSERT INTO searches (query, results_count) VALUES (%s, %s)",
        [queries, body.results_count]
    )
    return {"message": "Search logged"}



async def synthesizer(ticker: str, news: dict, sentiment: dict, fundamentals: dict, technical: dict, equity: dict, risk: dict, sub_evaluations: Optional[dict] = None) -> dict:
    
    logger.info(f"Synthesizing requested for {ticker}")
    
    try:
        sub_reports = {
            "news": news,
            "sentiment": sentiment,
            "fundamentals": fundamentals,
            "technical": technical,
            "equity": equity,
            "risk": risk
        }

        if os.environ.get("MOCK_MODE", "false").lower() == "true":
            await asyncio.sleep(0.3)
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            mock_res = {
                "recommendation": prof["recommendation"],
                "conviction": prof["conviction"],
                "price_target": prof["target_price"],
                "risk_reward": "favorable" if prof["conviction"] >= 7 else ("unfavorable" if prof["conviction"] <= 4 else "neutral"),
                "investment_horizon": "medium_term",
                "bull_case": [
                    f"Strong competitive positioning and brand moat for {ticker.upper()}",
                    f"Consistently strong free cash flow generation (${prof['free_cashflow']:,})",
                    "Constructive technical momentum clearing key support levels"
                ],
                "bear_case": [
                    f"Valuation multiples (P/E {prof['pe_ratio']}) trade at a premium to sector medians",
                    f"Systematic market risk with beta of {prof['beta']} vs benchmark",
                    "Macroeconomic and rate sensitivity in global markets"
                ],
                "key_catalysts": ["Upcoming quarterly earnings release", "New product line adoption"],
                "key_risks": ["Macroeconomic interest rate shifts", "Input cost inflation"],
                "position_sizing": "large" if prof["conviction"] >= 8 else ("medium" if prof["conviction"] >= 6 else "small"),
                "horizon_days": prof["horizon_days"],
                "expected_return": prof["expected_return"],
                "invalidation_price": prof["invalidation_price"],
                "review_date": prof["review_date"],
                "scenarios": prof["scenarios"],
                "target_source": "model",
                "_provenance": prof["_provenance"],
                "summary": f"{ticker.upper()} presents an attractive risk-adjusted opportunity backed by strong operational discipline in {prof['sector']}. With an expected return of {prof['expected_return']}% over a 63-day horizon, the outlook remains solid for intermediate-term investors."
            }
            clean_res, stats = guardrail_equity_research(mock_res, sub_reports)
            if sub_evaluations:
                stats["sub_evaluations"] = sub_evaluations
            clean_res["_evaluation"] = evaluate_agent_output("portfolio_manager", ticker, clean_res, stats)
            return clean_res

        logger.info(f"Running agents for {ticker}")
        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a senior portfolio manager synthesizing reports from 6 specialist agents.
                    Produce a final investment report. Return JSON with exactly these keys:
                    {
                        "recommendation": "strong_buy/buy/hold/sell/strong_sell",
                        "conviction": 1-10,
                        "price_target": 0.0,
                        "risk_reward": "favorable/neutral/unfavorable",
                        "investment_horizon": "short_term/medium_term/long_term",
                        "bull_case": ["point1", "point2", "point3"],
                        "bear_case": ["point1", "point2", "point3"],
                        "key_catalysts": ["catalyst1", "catalyst2"],
                        "key_risks": ["risk1", "risk2"],
                        "position_sizing": "large/medium/small/avoid",
                        "summary": "5 sentence investment summary"
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"""Synthesize this analysis for {ticker}:
                    NEWS: {json.dumps(news)}
                    SENTIMENT: {json.dumps(sentiment)}
                    FUNDAMENTALS: {json.dumps(fundamentals)}
                    TECHNICAL: {json.dumps(technical)}
                    EQUITY RESEARCH: {json.dumps(equity)}
                    RISK: {json.dumps(risk)}"""
                }
            ]
        )
        logger.info(f"Synthesis complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        clean_res, stats = guardrail_equity_research(parsed, sub_reports)
        if sub_evaluations:
            stats["sub_evaluations"] = sub_evaluations
        clean_res["_evaluation"] = evaluate_agent_output("portfolio_manager", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        logger.error(f"Synthesis failed for {ticker}: {e}")
        raise
    

analysis_cache = {}
validated_tickers = {}

async def validate_ticker(ticker: str) -> bool:
    """Verifies that a ticker is valid either from local DB, cache, or yfinance."""
    clean = ticker.upper().strip()
    if clean in validated_tickers:
        v_time, v_bool = validated_tickers[clean]
        if datetime.now() - v_time < timedelta(hours=1):
            return v_bool

    try:
        db_res = await asyncio.to_thread(query, "SELECT symbol FROM tickers WHERE symbol = %s", [clean])
        if db_res.rows:
            validated_tickers[clean] = (datetime.now(), True)
            return True
    except Exception:
        pass
    
    try:
        def check_yf():
            import yfinance as yf
            t = yf.Ticker(clean)
            hist = t.history(period="5d")
            return not hist.empty
        valid = await asyncio.to_thread(check_yf)
        validated_tickers[clean] = (datetime.now(), valid)
        return valid
    except Exception:
        return False

@app.post("/analyse/{ticker}")
async def analyse(ticker: str, nocache: Optional[int] = 0, user: dict = Depends(get_service_or_user)):
    ticker_clean = ticker.upper().strip()

    # 1. Enforce Pro Package subscription tier & internal token capacity FIRST before any DB/network/LLM work (PROD-011)
    req_tier = "pro"
    req_feature = f"Agentic Company Analysis ({ticker_clean})"
    await asyncio.to_thread(
        check_tokens_and_tier,
        user,
        500,
        req_tier,
        req_feature,
    )

    # 2. Check analysis cache for Pro users before hitting validation / network
    if not nocache and ticker_clean in analysis_cache:
        cached_time, cached_data = analysis_cache[ticker_clean]
        if datetime.now() - cached_time < timedelta(hours=24):
            from agents.risk_phase4 import get_degraded_agents_for_synthesis
            mr_live = await asyncio.to_thread(get_degraded_agents_for_synthesis)
            if mr_live.get("model_risk_banner") == cached_data.get("model_risk_banner"):
                logger.info(f"Cache hit for {ticker_clean}")
                cache_hits.labels(ticker=ticker_clean).inc()
                return {**cached_data, "cached": True}
    
    is_valid = await validate_ticker(ticker_clean)
    if not is_valid:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker_clean}' not found. Please verify the symbol.")

    uid_val = int(user["sub"]) if str(user.get("sub", "")).isdigit() else None
    ctx_tok = current_billing_user_id.set(uid_val)
        
    logger.info(f"Analysis requested for {ticker_clean} by user {user.get('email', user.get('sub'))}")
    
    active_analyses.inc()
    try:
        logger.info(f"Running agents for {ticker_clean}")
        # Single source of truth for consensus and street target price anchor
        authoritative_consensus = "buy"
        street_price_targets = {}
        if os.environ.get("MOCK_MODE", "false").lower() == "true":
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker_clean)
            authoritative_consensus = prof["recommendation"]
            bear_t = prof["scenarios"]["bear"]["target"]
            base_t = prof["target_price"]
            bull_t = prof["scenarios"]["bull"]["target"]
            street_price_targets = {
                "target_low": bear_t,
                "target_median": base_t,
                "target_mean": round((bear_t + base_t + bull_t) / 3.0, 2),
                "target_high": bull_t,
                "low": bear_t,
                "high": bull_t,
            }
        else:
            def fetch_consensus_and_targets():
                try:
                    s_info = yf.Ticker(ticker_clean).info
                    rec = s_info.get("recommendationKey")
                    rec_norm = rec.lower().replace(" ", "_") if rec else "buy"
                    if rec_norm not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
                        rec_norm = "buy"
                    return rec_norm, {
                        "target_low": s_info.get("targetLowPrice"),
                        "target_median": s_info.get("targetMedianPrice"),
                        "target_mean": s_info.get("targetMeanPrice"),
                        "target_high": s_info.get("targetHighPrice")
                    }
                except Exception:
                    return "buy", {}
            authoritative_consensus, street_price_targets = await asyncio.to_thread(fetch_consensus_and_targets)

        news = await news_agent(ticker_clean)
        
        agent_results = await asyncio.gather(
            sentiment_agent(ticker_clean, news, consensus=authoritative_consensus),
            fundamentals_agent(ticker_clean),
            technical_agent(ticker_clean),
            equity_research_agent(ticker_clean, consensus=authoritative_consensus, street_targets=street_price_targets),
            risk_agent(ticker_clean),
            return_exceptions=True
        )
        
        def unwrap_agent(res, agent_name):
            if isinstance(res, Exception):
                logger.error(f"Agent {agent_name} failed: {res}")
                return {
                    "summary": f"{agent_name.capitalize()} analysis temporarily unavailable for {ticker_clean}.",
                    "error": "Agent temporarily unavailable",
                    "_evaluation": {
                        "faithfulness_score": 0.0,
                        "consistency_score": 0.0,
                        "completeness_score": 0.0,
                        "overall_quality_score": 0.0,
                        "grade": "FAIL",
                        "warnings": [f"{agent_name} agent error: operation failed"]
                    }
                }
            return res

        sentiment = unwrap_agent(agent_results[0], "sentiment")
        fundamentals = unwrap_agent(agent_results[1], "fundamentals")
        technical = unwrap_agent(agent_results[2], "technical")
        equity = unwrap_agent(agent_results[3], "equity")
        risk = unwrap_agent(agent_results[4], "risk")

        # Run Live Contradiction & Epistemic Arbiter Agent grounded on footprint, Tri-Perspective feeds, and agent outputs
        try:
            radar = await contradiction_agent(ticker_clean, news=news, equity=equity, risk=risk)
        except Exception as rad_err:
            logger.warning(f"Contradiction agent fallback for {ticker_clean}: {rad_err}")
            radar = None

        # RSK-013: AI Model-Risk Governance & Kill-Switch enforcement
        from agents.risk_phase4 import get_degraded_agents_for_synthesis
        mr_state = await asyncio.to_thread(get_degraded_agents_for_synthesis)
        degraded_agents = mr_state.get("degraded_agents", [])
        model_risk_banner = mr_state.get("model_risk_banner")
        degraded_map = {d["agent_name"]: d for d in degraded_agents}

        agent_objs = {
            "news": news,
            "sentiment": sentiment,
            "fundamentals": fundamentals,
            "technical": technical,
            "equity": equity,
            "risk": risk,
        }
        for ag_name, ag_dict in agent_objs.items():
            if ag_name in degraded_map and isinstance(ag_dict, dict):
                d_info = degraded_map[ag_name]
                ag_dict["_model_risk_excluded"] = True
                ag_dict["_model_risk_status"] = d_info["status"]
                ag_dict["_model_risk_reason"] = d_info["reason"]

        sub_evaluations = {
            k: (v.get("_evaluation") if isinstance(v, dict) and k not in degraded_map else None)
            for k, v in agent_objs.items()
        }
        
        report = await synthesizer(ticker_clean, news, sentiment, fundamentals, technical, equity, risk, sub_evaluations=sub_evaluations)
        if model_risk_banner:
            report["model_risk_banner"] = model_risk_banner
            report["degraded_agents"] = degraded_agents
            if isinstance(report.get("conviction"), (int, float)):
                report["conviction"] = min(int(report["conviction"]), 6)
        else:
            report["model_risk_banner"] = None
            report["degraded_agents"] = []
        
        if isinstance(equity, dict) and "equity" not in degraded_map:
            if equity.get("price_target"):
                report["price_target"] = equity["price_target"]
            if equity.get("investment_thesis"):
                report["investment_thesis"] = equity["investment_thesis"]
            if equity.get("growth_catalysts"):
                report["key_catalysts"] = equity["growth_catalysts"]
            
        current_price = None
        if os.environ.get("MOCK_MODE", "false").lower() == "true":
            from agents.mock_market_data import get_deterministic_mock_profile
            current_price = get_deterministic_mock_profile(ticker_clean)["current_price"]
        if not current_price and isinstance(technical, dict):
            current_price = technical.get("raw", {}).get("current_price") or technical.get("current_price")
        if not current_price and isinstance(fundamentals, dict):
            current_price = fundamentals.get("current_price")
            
        if current_price:
            report["current_price"] = current_price
            if report.get("price_target") is not None:
                diff_pct = round(((report["price_target"] / current_price) - 1.0) * 100, 2)
                if diff_pct >= 0:
                    report["upside_downside"] = f"+{diff_pct}% upside from current price"
                else:
                    report["upside_downside"] = f"{abs(diff_pct)}% downside from current price"
                if isinstance(equity, dict):
                    equity["upside_downside"] = report["upside_downside"]
                if report.get("expected_return") is None:
                    report["expected_return"] = diff_pct

                # Keep risk_reward coherent with upside/downside, recommendation, and Risk agent evaluation (PROD-007)
                risk_grade = risk.get("_evaluation", {}).get("grade", "A") if isinstance(risk, dict) else "FAIL"
                rec_now = str(report.get("recommendation", "hold")).lower()
                if risk_grade == "FAIL" or "risk" in degraded_map or diff_pct < -1.0 or "sell" in rec_now:
                    report["risk_reward"] = "unfavorable"
                elif rec_now == "hold" or diff_pct < 4.0:
                    report["risk_reward"] = "neutral"
                else:
                    report["risk_reward"] = "favorable"
        
        if street_price_targets:
            report["analyst_price_targets"] = street_price_targets
            if isinstance(equity, dict):
                equity["analyst_price_targets"] = street_price_targets
        
        result = {
            "ticker": ticker_clean,
            "mode": "mock" if os.environ.get("MOCK_MODE", "false").lower() == "true" else "live",
            "model_risk_banner": model_risk_banner,
            "degraded_agents": degraded_agents,
            "report": report,
            "agents": {
                "news": news,
                "sentiment": sentiment,
                "fundamentals": fundamentals,
                "technical": technical,
                "equity": equity,
                "risk": risk,
                "radar": radar
            }
        }
        
        # Persist analysis snapshot immutably
        try:
            snapshot_id = record_analysis_snapshot(ticker_clean, result)
            result["snapshot_id"] = snapshot_id
        except Exception as snap_err:
            logger.warning(f"Failed to record analysis snapshot for {ticker_clean}: {snap_err}")
            
        # If running in MOCK_MODE (where Groq isn't called directly), deduct a realistic mock token usage (1,250 tokens)
        # so the user can test and watch their live token balance decrement during development
        if uid_val is not None and os.environ.get("MOCK_MODE", "false").lower() == "true":
            await asyncio.to_thread(deduct_user_tokens, uid_val, 1250, "multi_agent_analysis", ticker_clean)

        if uid_val is not None:
            wallet = await asyncio.to_thread(get_or_create_wallet, uid_val)
            result["membership"] = sanitize_public_membership(wallet)

        analysis_cache[ticker_clean] = (datetime.now(), result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed for {ticker_clean}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis pipeline encountered an internal error while processing {ticker_clean}.")
    finally:
        current_billing_user_id.reset(ctx_tok)
        active_analyses.dec()

@app.get("/test/{ticker}")
async def test(ticker: str, user: dict = Depends(get_current_user)):
    return await analyse(ticker, nocache=1, user=user)


@app.get("/footprint/{ticker}")
async def get_company_footprint(ticker: str, force_live: bool = False, user: dict = Depends(get_current_user)):
    """
    Returns the autonomous researched corporate footprint, archetype, hubs, 
    key suppliers, and generated perspective queries.
    Pass ?force_live=true to run live model tool loop.
    """
    req_feature = f"Corporate Footprint & Supply-Chain Discovery ({ticker.upper()})"
    await asyncio.to_thread(check_tokens_and_tier, user, 1000, "pro", req_feature)

    uid_val = int(user["sub"]) if str(user.get("sub", "")).isdigit() else None
    ctx_tok = current_billing_user_id.set(uid_val)
    try:
        footprint = await research_company_footprint(ticker, force_live=force_live)
        queries = generate_perspective_queries(footprint)
        wallet = await asyncio.to_thread(get_or_create_wallet, uid_val) if uid_val is not None else None
        return {
            "footprint": footprint,
            "queries": queries,
            "token_usage": footprint.token_usage,
            "evaluation": footprint.evaluation,
            "membership": sanitize_public_membership(wallet) if wallet else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve footprint for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to complete corporate footprint research for {ticker}.")
    finally:
        current_billing_user_id.reset(ctx_tok)


@app.get("/footprint/{ticker}/preview-feeds")
async def preview_tri_perspective_feeds(ticker: str, limit: int = 3, user: dict = Depends(get_current_user)):
    """
    Fetches real-time headlines across Western wires, localized on-ground hubs, 
    corporate PR, and tier-1 suppliers using zero-cost RSS/Atom feeds.
    """
    try:
        result = await fetch_tri_perspective_mesh(ticker, max_items_per_tier=limit)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch live feeds for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch feeds. Check server logs.")


@app.get("/contradictions/{ticker}")
async def get_live_contradictions(ticker: str, refresh: bool = False, user: dict = Depends(get_service_or_user)):
    """
    Returns the live Contradiction Radar & Epistemic Arbiter report for `ticker`,
    merging any cached 6-agent analysis output with the live Footprint & Tri-Perspective Feed Mesh.
    Enforces Pro Package tier check before running any backend LLM inference to save tokens.
    """
    clean_t = ticker.upper().strip()
    req_feature = f"Contradiction Radar & Epistemic Arbiter ({clean_t})"
    await asyncio.to_thread(
        check_tokens_and_tier,
        user,
        400,
        "pro",
        req_feature,
    )

    cached_entry = analysis_cache.get(clean_t)
    cached_agents = cached_entry[1].get("agents", {}) if cached_entry else {}

    if not refresh and cached_agents.get("radar"):
        return cached_agents["radar"]

    uid_val = int(user["sub"]) if str(user.get("sub", "")).isdigit() else None
    ctx_tok = current_billing_user_id.set(uid_val)
    try:
        report = await contradiction_agent(
            clean_t,
            news=cached_agents.get("news"),
            equity=cached_agents.get("equity"),
            risk=cached_agents.get("risk"),
            force_refresh=refresh,
        )
        return report
    finally:
        current_billing_user_id.reset(ctx_tok)


@app.get("/tokens/summary")
async def get_token_usage_summary(user: dict = Depends(get_current_user)):
    """
    Returns aggregated token usage statistics from PostgreSQL agent_token_logs,
    including breakdowns by agent, by ticker, and recent operations.
    """
    try:
        totals_res = await asyncio.to_thread(
            query,
            """SELECT 
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COUNT(*) as total_llm_calls
               FROM agent_token_logs"""
        )
        totals = totals_res.rows[0] if totals_res.rows else {}

        by_agent_res = await asyncio.to_thread(
            query,
            """SELECT 
                agent_name,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as calls
               FROM agent_token_logs
               GROUP BY agent_name
               ORDER BY total_tokens DESC"""
        )
        
        by_ticker_res = await asyncio.to_thread(
            query,
            """SELECT 
                ticker,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as calls
               FROM agent_token_logs
               GROUP BY ticker
               ORDER BY total_tokens DESC
               LIMIT 10"""
        )

        recent_res = await asyncio.to_thread(
            query,
            """SELECT id, agent_name, ticker, model, prompt_tokens, completion_tokens, total_tokens, duration_ms, created_at
               FROM agent_token_logs
               ORDER BY id DESC
               LIMIT 15"""
        )

        return {
            "summary": totals,
            "by_agent": by_agent_res.rows,
            "by_ticker": by_ticker_res.rows,
            "recent_logs": recent_res.rows
        }
    except Exception as e:
        logger.error(f"Failed to fetch token summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error fetching token summary")


@app.get("/evaluations/summary")
async def get_evaluations_summary(user: dict = Depends(get_current_user)):
    """
    Returns aggregated semantic evaluation metrics, faithfulness scores, 
    guardrail pass rates, and intercepted hallucination counts from PostgreSQL.
    """
    try:
        totals_res = await asyncio.to_thread(
            query,
            """SELECT 
                COUNT(*) as total_evaluations,
                ROUND(AVG(faithfulness_score)::numeric, 2) as avg_faithfulness,
                ROUND(AVG(citation_grounding_score)::numeric, 2) as avg_citation_grounding,
                ROUND(AVG(completeness_score)::numeric, 2) as avg_completeness,
                ROUND(AVG(overall_quality_score)::numeric, 2) as avg_overall_quality,
                COALESCE(SUM(hallucinations_detected), 0) as total_hallucinations_intercepted,
                ROUND((COUNT(*) FILTER (WHERE guardrails_passed = true) * 100.0 / GREATEST(COUNT(*), 1))::numeric, 1) as guardrails_pass_percentage
               FROM footprint_evaluations"""
        )
        totals = totals_res.rows[0] if totals_res.rows else {}

        by_grade_res = await asyncio.to_thread(
            query,
            """SELECT grade, COUNT(*) as count
               FROM footprint_evaluations
               GROUP BY grade
               ORDER BY count DESC"""
        )

        recent_res = await asyncio.to_thread(
            query,
            """SELECT id, ticker, faithfulness_score, citation_grounding_score, completeness_score, 
                      overall_quality_score, grade, guardrails_passed, hallucinations_detected, details, created_at
               FROM footprint_evaluations
               ORDER BY id DESC
               LIMIT 15"""
        )

        return {
            "summary": totals,
            "by_grade": by_grade_res.rows,
            "recent_evaluations": recent_res.rows
        }
    except Exception as e:
        logger.error(f"Failed to fetch evaluations summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error fetching evaluations summary")


@app.get("/evaluations/agents/summary")
async def get_multi_agent_evaluations_summary(user: dict = Depends(get_current_user)):
    """
    Returns aggregated evaluation metrics across all 6 financial analysis agents from PostgreSQL,
    including breakdown by agent_name, by grade, and recent evaluations.
    """
    try:
        totals_res = await asyncio.to_thread(
            query,
            """SELECT 
                COUNT(*) as total_evaluations,
                ROUND(AVG(faithfulness_score)::numeric, 2) as avg_faithfulness,
                ROUND(AVG(consistency_score)::numeric, 2) as avg_consistency,
                ROUND(AVG(completeness_score)::numeric, 2) as avg_completeness,
                ROUND(AVG(overall_quality_score)::numeric, 2) as avg_overall_quality,
                COALESCE(SUM(hallucinations_detected), 0) as total_hallucinations_intercepted,
                ROUND((COUNT(*) FILTER (WHERE guardrails_passed = true) * 100.0 / GREATEST(COUNT(*), 1))::numeric, 1) as guardrails_pass_percentage
               FROM agent_evaluations"""
        )
        totals = totals_res.rows[0] if totals_res.rows else {}

        by_agent_res = await asyncio.to_thread(
            query,
            """SELECT 
                agent_name,
                COUNT(*) as total_runs,
                ROUND(AVG(overall_quality_score)::numeric, 2) as avg_quality,
                COALESCE(SUM(hallucinations_detected), 0) as hallucinations_intercepted
               FROM agent_evaluations
               GROUP BY agent_name
               ORDER BY total_runs DESC"""
        )

        by_grade_res = await asyncio.to_thread(
            query,
            """SELECT grade, COUNT(*) as count
               FROM agent_evaluations
               GROUP BY grade
               ORDER BY count DESC"""
        )

        recent_res = await asyncio.to_thread(
            query,
            """SELECT id, agent_name, ticker, faithfulness_score, consistency_score, completeness_score,
                      overall_quality_score, grade, guardrails_passed, hallucinations_detected, warnings, created_at
               FROM agent_evaluations
               ORDER BY id DESC
               LIMIT 20"""
        )

        return {
            "summary": totals,
            "by_agent": by_agent_res.rows,
            "by_grade": by_grade_res.rows,
            "recent_evaluations": recent_res.rows
        }
    except Exception as e:
        logger.error(f"Failed to fetch agent evaluations summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error fetching agent evaluations summary")


# ==============================================================================
# LIVE HOT TICKERS & PORTFOLIO MOVERS ENDPOINT (/hot-tickers)
# ==============================================================================
_hot_tickers_market_cache = {"ts": 0.0, "quotes": {}}
_HOT_TICKER_METADATA = {
    "AAPL": ("Apple Inc.", "Technology"),
    "NVDA": ("NVIDIA Corp.", "Semiconductors"),
    "TSLA": ("Tesla, Inc.", "Automotive / AI"),
    "MSFT": ("Microsoft Corp.", "Cloud / Software"),
    "AMZN": ("Amazon.com, Inc.", "Consumer / Cloud"),
    "META": ("Meta Platforms, Inc.", "Social / AI"),
    "GOOGL": ("Alphabet Inc.", "Internet / AI"),
    "AMD": ("Advanced Micro Devices", "Semiconductors"),
    "PLTR": ("Palantir Technologies", "AI / Defense"),
    "COIN": ("Coinbase Global", "Crypto / Fintech"),
    "AVGO": ("Broadcom Inc.", "Semiconductors"),
    "NFLX": ("Netflix, Inc.", "Entertainment"),
    "JPM": ("JPMorgan Chase & Co.", "Financials"),
    "SMCI": ("Super Micro Computer", "AI Infrastructure"),
    "ARM": ("Arm Holdings plc", "Semiconductors"),
    "MSTR": ("Strategy (MicroStrategy)", "Bitcoin / Enterprise"),
    "UBER": ("Uber Technologies", "Mobility"),
    "INTC": ("Intel Corporation", "Semiconductors"),
    "BAC": ("Bank of America Corp.", "Financials"),
    "WMT": ("Walmart Inc.", "Consumer Retail"),
    "LLY": ("Eli Lilly and Co.", "Healthcare"),
    "TSM": ("Taiwan Semiconductor", "Semiconductors"),
    "ORCL": ("Oracle Corporation", "Enterprise Cloud"),
    "CRWD": ("CrowdStrike Holdings", "Cybersecurity"),
}


def _fetch_yahoo_live_screener_symbols() -> dict:
    """
    Pulls today's real-time Trending, Most Active, Day Gainers, and Day Losers symbols
    from Yahoo Finance public screener endpoints, with a curated liquid universe fallback.
    """
    import requests as _req
    import time as _time

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    discovered = {
        "trending": [],
        "day_gainers": [],
        "day_losers": [],
        "most_actives": [],
        "quote_map": {},
    }

    # 1. Yahoo Finance Trending US
    t0 = _time.time()
    try:
        tr_resp = _req.get(
            "https://query1.finance.yahoo.com/v1/finance/trending/US?count=15",
            headers=headers,
            timeout=5.0,
        )
        record_external_api_call(
            provider="yfinance",
            endpoint="GET /v1/finance/trending/US",
            operation="fetch_trending_tickers",
            status_code=tr_resp.status_code,
            duration_ms=(_time.time() - t0) * 1000.0,
        )
        if tr_resp.status_code == 200:
            quotes = (
                tr_resp.json()
                .get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
            )
            for q in quotes:
                sym = str(q.get("symbol", "")).upper().strip()
                if sym.isalpha() and 1 <= len(sym) <= 5:
                    discovered["trending"].append(sym)
    except Exception as exc:
        logger.debug(f"Yahoo trending fetch fallback: {exc}")

    # 2. Yahoo Finance Predefined Screeners: most_actives, day_gainers, day_losers
    for scr_id in ("most_actives", "day_gainers", "day_losers"):
        t1 = _time.time()
        try:
            s_resp = _req.get(
                f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds={scr_id}&count=10",
                headers=headers,
                timeout=5.0,
            )
            record_external_api_call(
                provider="yfinance",
                endpoint=f"GET /v1/finance/screener ({scr_id})",
                operation=f"screener_{scr_id}",
                status_code=s_resp.status_code,
                duration_ms=(_time.time() - t1) * 1000.0,
            )
            if s_resp.status_code == 200:
                res_list = s_resp.json().get("finance", {}).get("result", [])
                quotes = res_list[0].get("quotes", []) if res_list else []
                for q in quotes:
                    sym = str(q.get("symbol", "")).upper().strip()
                    if not (sym.isalpha() and 1 <= len(sym) <= 5):
                        continue
                    discovered[scr_id].append(sym)
                    price = q.get("regularMarketPrice")
                    chg_pct = q.get("regularMarketChangePercent")
                    vol = q.get("regularMarketVolume")
                    avg_vol = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day")
                    if price:
                        discovered["quote_map"][sym] = {
                            "symbol": sym,
                            "name": q.get("shortName") or q.get("longName") or _HOT_TICKER_METADATA.get(sym, (sym, "Equities"))[0],
                            "sector": _HOT_TICKER_METADATA.get(sym, (sym, "US Equities"))[1],
                            "price": round(float(price), 2),
                            "change_pct": round(float(chg_pct or 0.0), 2),
                            "volume": int(vol or 0),
                            "avg_volume": int(avg_vol or vol or 1),
                        }
        except Exception as exc:
            logger.debug(f"Yahoo screener {scr_id} fallback: {exc}")

    return discovered


def _build_hot_tickers_payload(portfolio_positions: list, refresh: bool = False) -> dict:
    """
    Combines the user's live portfolio holdings with today's hottest market movers
    (Yahoo Finance Trending, Most Active, Top Gainers, Top Losers + yfinance batch history),
    returning a unified grid of 10-12 tickers with live prices, volume ratios, badges,
    and a 1-line "Why it's moving" summary.
    """
    import time as _time
    import pandas as _pd

    now_ts = _time.time()
    is_mock = os.environ.get("MOCK_MODE", "false").lower() == "true"

    portfolio_map = {}
    for pos in portfolio_positions:
        sym = str(pos.get("ticker", "")).upper().strip()
        if sym:
            portfolio_map[sym] = {
                "quantity": float(pos.get("quantity") or 0),
                "avg_cost": float(pos.get("avg_cost") or 0),
            }

    # Cache market-wide hot quotes for 5 minutes so opening /analysis is instant
    if not refresh and (now_ts - _hot_tickers_market_cache["ts"] < 300) and _hot_tickers_market_cache["quotes"]:
        cached_quotes = dict(_hot_tickers_market_cache["quotes"])
        trending_set = set(_hot_tickers_market_cache.get("trending", []))
        gainers_set = set(_hot_tickers_market_cache.get("day_gainers", []))
        losers_set = set(_hot_tickers_market_cache.get("day_losers", []))
        actives_set = set(_hot_tickers_market_cache.get("most_actives", []))
    else:
        discovered = {} if is_mock else _fetch_yahoo_live_screener_symbols()
        trending_set = set(discovered.get("trending", []))
        gainers_set = set(discovered.get("day_gainers", []))
        losers_set = set(discovered.get("day_losers", []))
        actives_set = set(discovered.get("most_actives", []))
        cached_quotes = dict(discovered.get("quote_map", {}))

        # Candidate symbols: portfolio holdings + discovered screeners + liquid momentum universe
        candidate_order = []
        for s in (
            list(portfolio_map.keys())
            + list(discovered.get("day_gainers", [])[:4])
            + list(discovered.get("most_actives", [])[:4])
            + list(discovered.get("trending", [])[:6])
            + list(discovered.get("day_losers", [])[:3])
            + list(_HOT_TICKER_METADATA.keys())
        ):
            if s and s not in candidate_order:
                candidate_order.append(s)

        missing_syms = [s for s in candidate_order[:20] if s not in cached_quotes]

        if is_mock:
            from agents.mock_market_data import get_deterministic_mock_profile
            for sym in candidate_order[:16]:
                prof = get_deterministic_mock_profile(sym)
                meta_name, meta_sec = _HOT_TICKER_METADATA.get(sym, (prof["company_name"], prof["sector"]))
                cached_quotes[sym] = {
                    "symbol": sym,
                    "name": meta_name,
                    "sector": meta_sec,
                    "price": round(float(prof["current_price"]), 2),
                    "change_pct": round(float(prof["day_change_pct"]), 2),
                    "volume": int(prof.get("adv_20d_dollars", 25_000_000) / max(prof["current_price"], 1)),
                    "avg_volume": int(prof.get("adv_20d_dollars", 20_000_000) / max(prof["current_price"], 1) * 0.85),
                }
        elif missing_syms:
            t_yf = _time.time()
            try:
                df = yf.download(
                    tickers=" ".join(missing_syms),
                    period="5d",
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
                record_external_api_call(
                    provider="yfinance",
                    endpoint="yf.download(5d batch hot-tickers)",
                    operation=f"batch_quotes ({len(missing_syms)} tickers)",
                    status_code=200,
                    duration_ms=(_time.time() - t_yf) * 1000.0,
                )
                for sym in missing_syms:
                    try:
                        sub_df = df[sym] if len(missing_syms) > 1 else df
                        sub_df = sub_df.dropna(subset=["Close"])
                        if sub_df.empty:
                            continue
                        closes = sub_df["Close"]
                        vols = sub_df["Volume"]
                        last_px = float(closes.iloc[-1])
                        prev_px = float(closes.iloc[-2]) if len(closes) >= 2 else last_px
                        chg_pct = ((last_px / prev_px) - 1.0) * 100.0 if prev_px > 0 else 0.0
                        last_vol = int(vols.iloc[-1]) if not _pd.isna(vols.iloc[-1]) else 0
                        avg_vol = int(vols.mean()) if len(vols) > 0 and not _pd.isna(vols.mean()) else max(last_vol, 1)
                        meta_name, meta_sec = _HOT_TICKER_METADATA.get(sym, (f"{sym} Corp.", "US Equities"))
                        cached_quotes[sym] = {
                            "symbol": sym,
                            "name": meta_name,
                            "sector": meta_sec,
                            "price": round(last_px, 2),
                            "change_pct": round(chg_pct, 2),
                            "volume": last_vol,
                            "avg_volume": max(avg_vol, 1),
                        }
                    except Exception:
                        continue
            except Exception as yf_err:
                logger.warning(f"yfinance batch hot-tickers download error: {yf_err}")

        _hot_tickers_market_cache.update({
            "ts": now_ts,
            "quotes": cached_quotes,
            "trending": list(trending_set),
            "day_gainers": list(gainers_set),
            "day_losers": list(losers_set),
            "most_actives": list(actives_set),
        })

    # Ensure any custom portfolio ticker not yet in cached_quotes is fetched
    for p_sym in portfolio_map:
        if p_sym not in cached_quotes:
            try:
                from agents.mock_market_data import get_deterministic_mock_profile
                prof = get_deterministic_mock_profile(p_sym)
                cached_quotes[p_sym] = {
                    "symbol": p_sym,
                    "name": _HOT_TICKER_METADATA.get(p_sym, (prof["company_name"], prof["sector"]))[0],
                    "sector": _HOT_TICKER_METADATA.get(p_sym, (prof["company_name"], prof["sector"]))[1],
                    "price": round(float(prof["current_price"]), 2),
                    "change_pct": round(float(prof["day_change_pct"]), 2),
                    "volume": 18_400_000,
                    "avg_volume": 15_200_000,
                }
            except Exception:
                pass

    # Score & decorate all available quotes
    decorated = []
    for sym, q in cached_quotes.items():
        price = float(q.get("price") or 0.0)
        if price <= 0:
            continue
        chg = float(q.get("change_pct") or 0.0)
        vol = int(q.get("volume") or 0)
        avg_vol = max(int(q.get("avg_volume") or vol or 1), 1)
        vol_ratio = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0
        in_portfolio = sym in portfolio_map
        pos_info = portfolio_map.get(sym)

        badges = []
        if in_portfolio:
            badges.append({"label": "💼 In Portfolio", "tone": "portfolio"})
        if sym in gainers_set or chg >= 3.0:
            badges.append({"label": "📈 Top Gainer", "tone": "bull"})
        elif sym in losers_set or chg <= -3.0:
            badges.append({"label": "📉 Sharp Pullback", "tone": "bear"})
        if sym in actives_set or vol_ratio >= 1.35:
            badges.append({"label": f"⚡ High Volume ({vol_ratio:.1f}x)", "tone": "caution"})
        if sym in trending_set or not badges:
            badges.append({"label": "🔥 Trending Today", "tone": "brand"})

        # Build concise 1-line "Why it's moving" catalyst summary
        if in_portfolio and pos_info:
            unreal_pct = round(((price / pos_info["avg_cost"]) - 1.0) * 100.0, 1) if pos_info["avg_cost"] > 0 else 0.0
            sign_u = "+" if unreal_pct >= 0 else ""
            why_moving = (
                f"Active portfolio holding ({int(pos_info['quantity'])} sh @ ${pos_info['avg_cost']:.2f}, {sign_u}{unreal_pct}% P&L) • "
                f"Trading at {vol_ratio:.1f}x normal volume today."
            )
        elif chg >= 3.0:
            why_moving = f"Surging +{chg:.2f}% intraday on {vol_ratio:.1f}x relative volume with strong institutional momentum."
        elif chg <= -3.0:
            why_moving = f"Pulling back {chg:.2f}% on {vol_ratio:.1f}x volume; watch technical support and supply-chain radar."
        elif vol_ratio >= 1.35:
            why_moving = f"Unusual volume spike ({vol_ratio:.1f}x 5-day avg) attracting heavy options and block-trade flow."
        else:
            why_moving = f"High-liquidity {q.get('sector', 'market')} leader moving {'+' if chg >= 0 else ''}{chg:.2f}% across active institutional desks."

        # Heat score: portfolio holdings first, then largest absolute % move + volume ratio + trending bonus
        heat_score = (1000.0 if in_portfolio else 0.0) + (abs(chg) * 12.0) + (vol_ratio * 8.0) + (15.0 if sym in trending_set else 0.0)

        decorated.append({
            "symbol": sym,
            "name": q.get("name") or sym,
            "sector": q.get("sector") or "US Equities",
            "price": price,
            "change_pct": chg,
            "volume": vol,
            "avg_volume": avg_vol,
            "volume_ratio": vol_ratio,
            "in_portfolio": in_portfolio,
            "portfolio_qty": pos_info["quantity"] if pos_info else None,
            "portfolio_avg_cost": pos_info["avg_cost"] if pos_info else None,
            "badges": badges[:2],
            "why_moving": why_moving,
            "_heat_score": heat_score,
        })

    decorated.sort(key=lambda x: x["_heat_score"], reverse=True)
    top_grid = [{k: v for k, v in item.items() if not k.startswith("_")} for item in decorated[:12]]

    return {
        "as_of": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(top_grid),
        "portfolio_count": sum(1 for t in top_grid if t.get("in_portfolio")),
        "tickers": top_grid,
    }


@app.get("/hot-tickers")
async def get_hot_tickers(refresh: bool = False, user: dict = Depends(get_service_or_user)):
    """
    Returns a unified grid of today's 10-12 hottest market tickers (Yahoo Finance Trending,
    Top Gainers, Top Losers, Most Active by Volume) merged with the authenticated user's
    portfolio holdings.
    """
    portfolio_positions = []
    sub = user.get("sub")
    if sub and str(sub).isdigit():
        uid = int(sub)
        try:
            p_res = await asyncio.to_thread(
                query,
                """SELECT pos.ticker, pos.quantity, pos.avg_cost
                   FROM positions pos
                   JOIN portfolios p ON p.id = pos.portfolio_id
                   WHERE p.user_id = %s
                   ORDER BY pos.id ASC
                   LIMIT 8""",
                [uid],
            )
            portfolio_positions = [dict(r) for r in p_res.rows]
        except Exception as db_err:
            logger.debug(f"Portfolio lookup for hot-tickers skipped: {db_err}")

    if not portfolio_positions:
        # Default core portfolio positions if user hasn't opened /portfolio yet
        portfolio_positions = [
            {"ticker": "AAPL", "quantity": 80.0, "avg_cost": 215.00},
            {"ticker": "MSFT", "quantity": 45.0, "avg_cost": 410.00},
            {"ticker": "NVDA", "quantity": 100.0, "avg_cost": 125.00},
        ]

    payload = await asyncio.to_thread(_build_hot_tickers_payload, portfolio_positions, refresh)
    return payload





