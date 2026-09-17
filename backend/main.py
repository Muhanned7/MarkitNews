from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List, Union
import asyncio
import json
from auth import hash_password, verify_password, create_token, get_current_user
from agents.db import query
import os

load_dotenv()


from agents.news_agent import news_agent
from agents.sentiment_agent import sentiment_agent
from agents.technical_agent import technical_agent
from agents.fundamentals_agent import fundamentals_agent
from agents.equity_reasearch_agent import equity_research_agent
from agents.risk_agent import risk_agent
from agents.client import client
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger
from agents.metrics import active_analyses, cache_hits
from datetime import datetime, timedelta
import sys
#client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])


app = FastAPI(title="MarketPulse Backend")

# Logging setup
logger.remove()
logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="INFO")

# Prometheus metrics
Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/register")
async def register(body: RegisterRequest):
    if len(body.password.encode('utf-8')) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 characters or less")
    
    hashed = hash_password(body.password)
    try:
        result = await asyncio.to_thread(
            query,
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
            [body.email, hashed]
        )
        user = result.rows[0]
        token = create_token(user["id"], user["email"])
        return {"token": token, "email": user["email"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Email already exists")

@app.post("/auth/login")
async def login(body: LoginRequest):
    result = await asyncio.to_thread(
        query,
        "SELECT * FROM users WHERE email = %s",
        [body.email]
    )
    if not result.rows:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = result.rows[0]
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], user["email"])
    return {"token": token, "email": user["email"]}

@app.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


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
        "INSERT INTO watchlist (ticker, user_id) VALUES (%s, %s)",
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
async def get_all_watchlist_tickers():
    result = await asyncio.to_thread(
        query,
        "SELECT DISTINCT ticker FROM watchlist"
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
async def create_ticker(body: TickerCreateRequest):
    await asyncio.to_thread(
        query,
        """INSERT INTO tickers (symbol, name, description, sector, industry)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (symbol) DO NOTHING""",
        [body.symbol.upper().strip(), body.name, body.description, body.sector, body.industry]
    )
    return {"message": f"Ticker {body.symbol} processed"}

@app.patch("/tickers/{symbol}/embedding")
async def update_ticker_embedding(symbol: str):
    await asyncio.to_thread(
        query,
        "UPDATE tickers SET embedding_stored = TRUE WHERE symbol = %s",
        [symbol.upper().strip()]
    )
    return {"message": f"Embedding status updated for {symbol}"}

@app.post("/articles")
async def save_articles(body: ArticlesBatchRequest):
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
async def log_search(body: SearchLogRequest):
    queries = body.query if isinstance(body.query, list) else [body.query]
    await asyncio.to_thread(
        query,
        "INSERT INTO searches (query, results_count) VALUES (%s, %s)",
        [queries, body.results_count]
    )
    return {"message": "Search logged"}



async def synthesizer(ticker: str, news: dict, sentiment: dict, fundamentals: dict, technical: dict, equity: dict, risk: dict) -> dict:
    
    logger.info(f"Synthesizing requested for {ticker}")
    
    try:
        if os.environ.get("MOCK_MODE", "true").lower() == "true":
            await asyncio.sleep(0.3)
            return {
                "recommendation": "buy",
                "conviction": 8,
                "price_target": 215.0,
                "risk_reward": "favorable",
                "investment_horizon": "medium_term",
                "bull_case": [
                    f"Strong competitive positioning and brand moat for {ticker}",
                    "Steady cash flow generation supporting ongoing innovation",
                    "Constructive technical momentum clearing key support levels"
                ],
                "bear_case": [
                    "Valuation multiples trade at a modest premium to sector medians",
                    "Potential exposure to broader tech sector volatility",
                    "Regulatory and supply chain considerations in global markets"
                ],
                "key_catalysts": ["Upcoming quarterly earnings release", "New product line adoption"],
                "key_risks": ["Macroeconomic interest rate shifts", "Input cost inflation"],
                "position_sizing": "medium",
                "summary": f"{ticker.upper()} presents an attractive risk-adjusted opportunity backed by strong operational discipline and durable market demand. With consistent analyst support and a constructive chart setup, the outlook remains solid for intermediate-term investors."
            }

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
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Synthesis failed for {ticker}: {e}")
        raise
    

analysis_cache = {}
@app.post("/analyse/{ticker}")
async def analyse(ticker: str, user: dict = Depends(get_current_user)):
    
    
    logger.info(f"Analysis requested for {ticker} by user {user.get('email', user.get('sub'))}")
    # return cache if analysed today
    if ticker in analysis_cache:
        cached_time, cached_data = analysis_cache[ticker]
        if datetime.now() - cached_time < timedelta(hours=24):
            logger.info(f"Cache hit for {ticker}")
            cache_hits.labels(ticker=ticker).inc()
            return {**cached_data, "cached": True}
    
    active_analyses.inc()
    try:
        logger.info(f"Running agents for {ticker}")
        news = await news_agent(ticker)
        sentiment, fundamentals, technical, equity, risk = await asyncio.gather(
            sentiment_agent(ticker, news),
            fundamentals_agent(ticker),
            technical_agent(ticker),
            equity_research_agent(ticker),
            risk_agent(ticker),
        )
        report = await synthesizer(ticker, news, sentiment, fundamentals, technical, equity, risk)
        
        result = {
            "ticker": ticker,
            "report": report,
            "agents": {
                "news": news,
                "sentiment": sentiment,
                "fundamentals": fundamentals,
                "technical": technical,
                "equity": equity,
                "risk": risk
            }
        }
        
        analysis_cache[ticker] = (datetime.now(), result)
        return result
    except Exception as e:
        logger.error(f"Analysis failed for {ticker}: {e}")
        raise
    finally:
        active_analyses.dec()



@app.get("/test/{ticker}")
async def test(ticker: str, user: dict = Depends(get_current_user)):
    return await analyse(ticker, user)