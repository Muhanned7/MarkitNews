import asyncio
import json
import requests
from mistralai.client import Mistral
import os
from agents.client import client, parse_llm_json
from agents.metrics import agent_calls, agent_latency, mistral_errors
from agents.guardrails import guardrail_news_agent
from agents.evaluator import evaluate_agent_output
from agents.api_monitor import log_external_api_call
from ingestion.adapters.geo_feed_adapter import classify_article_temporal_regime, fetch_rss_feed
from loguru import logger
import time

def _is_mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "false").lower() == "true"

async def research_agent(ticker: str) -> dict:
    logger.info(f"Research requested for {ticker}")
    try:
        logger.info(f"Running Research agents for {ticker}")
        if _is_mock_mode():
            await asyncio.sleep(0.4)
            return {
                "company_name": f"{ticker.upper()} Corp",
                "sector": "Technology",
                "key_suppliers": ["TSMC", "ASML", "Samsung Electronics"],
                "raw_materials": ["Silicon", "Neon Gas", "Lithium"],
                "key_countries": ["Taiwan", "USA", "South Korea", "China"],
                "search_queries": [
                    f"{ticker} supply chain risks",
                    f"{ticker} semiconductor policy impact",
                    f"{ticker} raw material costs",
                    f"{ticker} expansion in Asia",
                    f"{ticker} government contracts"
                ]
            }

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            agent_name="research_agent",
            ticker=ticker,
            messages=[
                {
                    "role": "system",
                    "content": """You are a financial research analyst. Given a stock ticker, return a JSON object with these exact keys:
                    {
                        "company_name": "full company name",
                        "sector": "sector",
                        "key_suppliers": ["supplier1", "supplier2"],
                        "raw_materials": ["material1", "material2"],
                        "key_countries": ["country1", "country2"],
                        "search_queries": ["query1", "query2", "query3", "query4", "query5"]
                    }
                    search_queries should be specific NewsAPI-ready queries that would surface relevant news about the company, its supply chain, policy risks, and market conditions.
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Research this ticker: {ticker}"
                }
            ]
        )
        return parse_llm_json(
            response.choices[0].message.content,
            fallback={
                "company_name": f"{ticker.upper()} Corp",
                "sector": "Technology",
                "key_suppliers": ["TSMC", "Foxconn"],
                "raw_materials": ["Silicon"],
                "key_countries": ["USA", "Taiwan"],
                "search_queries": [f"{ticker} stock news", f"{ticker} earnings", f"{ticker} supply chain"],
            },
        )

    except Exception as e:
        logger.error(f"Reasearch Agent failed for {ticker}: {e}")
        raise


async def news_agent(ticker: str) -> dict:
    logger.info(f"News Agent requested for {ticker}")
    agent_calls.labels(agent_name='news', ticker=ticker).inc()

    start = time.time()
    try:
        logger.info(f"Running News agent for {ticker}")
        
        if _is_mock_mode():
            await asyncio.sleep(0.4)
            mock_res = {
                "overall_sentiment": "bullish",
                "summary": f"{ticker.upper()} is seeing strong positive momentum following reports of diversified supply chain logistics. Market analysts are focusing on the reduced dependency on single-region suppliers. Increased institutional interest is noted ahead of the upcoming product cycle.",
                "key_themes": ["Supply Chain Resilience", "Next-Gen AI Integration", "Market Share Expansion"],
                "supply_chain_risks": ["Potential export restrictions in Asia", "Rising costs of raw silicon"],
                "articles": [
                    {
                        "title": f"Why {ticker} leads the sector in 2026",
                        "source": "MarketWatch",
                        "url": "https://finance.yahoo.com",
                        "relevance": "Highlights the company's competitive advantage in supply chain management."
                    },
                    {
                        "title": f"New Policy Impacts for {ticker} Suppliers",
                        "source": "Reuters",
                        "url": "https://finance.yahoo.com",
                        "relevance": "Discusses potential cost increases for raw materials."
                    }
                ]
            }
            clean_res, stats = guardrail_news_agent(mock_res, mock_res["articles"])
            clean_res["_evaluation"] = evaluate_agent_output("news", ticker, clean_res, stats)
            return clean_res

        research = await research_agent(ticker)
        queries = research.get("search_queries", [ticker])

        async def fetch_news(query):
            api_key = os.environ.get("NEWSAPI_KEY", "").strip()
            if api_key:
                t0 = time.time()
                try:
                    resp = await asyncio.to_thread(
                        requests.get,
                        "https://newsapi.org/v2/everything",
                        params={
                            "q": query,
                            "pageSize": 5,
                            "sortBy": "publishedAt",
                            "apiKey": api_key
                        },
                        timeout=10
                    )
                    latency = (time.time() - t0) * 1000.0
                    data = resp.json() if resp.status_code == 200 else {}
                    arts = data.get("articles", []) or []
                    if resp.status_code != 429:
                        log_external_api_call(
                            provider="NewsAPI",
                            endpoint="GET /v2/everything",
                            method="GET",
                            status_code=resp.status_code,
                            latency_ms=latency,
                            caller="news_agent",
                            ticker=ticker,
                            query_summary=f"q={query} ({len(arts)} articles)",
                            success=(resp.status_code == 200),
                        )
                    if arts:
                        return arts
                except Exception as ex:
                    log_external_api_call(
                        provider="NewsAPI",
                        endpoint="GET /v2/everything",
                        method="GET",
                        status_code=500,
                        latency_ms=(time.time() - t0) * 1000.0,
                        caller="news_agent",
                        ticker=ticker,
                        query_summary=f"q={query}",
                        success=False,
                        error_message=str(ex)[:200],
                    )
            # Fallback to live Google News RSS via geo_feed_adapter if NewsAPI quota is reached or missing
            import httpx
            async with httpx.AsyncClient(follow_redirects=True) as rss_client:
                rss_items = await fetch_rss_feed(
                    client=rss_client,
                    query_str=query,
                    gl="US",
                    hl="en-US",
                    ceid="US:en",
                    max_items=5,
                    recency_window="90d",
                )
            return [
                {
                    "title": item.get("title", ""),
                    "description": item.get("title", ""),
                    "source": {"name": item.get("source", "Google News RSS")},
                    "url": item.get("url", ""),
                    "publishedAt": item.get("published_at", ""),
                }
                for item in rss_items
            ]

        all_articles_nested = await asyncio.gather(
            *[fetch_news(q) for q in queries[:3]]
        )

        seen = set()
        all_articles = []
        for articles in all_articles_nested:
            for article in articles:
                if article["url"] not in seen:
                    seen.add(article["url"])
                    pub_ts = article.get("publishedAt") or article.get("published_at") or ""
                    temporal_meta = classify_article_temporal_regime(pub_ts)
                    all_articles.append({
                        "title": article["title"],
                        "description": article["description"],
                        "source": article["source"]["name"] if isinstance(article.get("source"), dict) else article.get("source", "News Wire"),
                        "url": article["url"],
                        "published": pub_ts,
                        "age_days": temporal_meta["age_days"],
                        "temporal_regime": temporal_meta["temporal_regime"],
                        "is_live_contradiction_eligible": temporal_meta["is_live_contradiction_eligible"],
                        "temporal_guidance": temporal_meta["temporal_guidance"]
                    })

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            agent_name="news_agent",
            ticker=ticker,
            messages=[
                {
                    "role": "system",
                    "content": """You are a senior institutional financial & supply-chain news analyst. Given a list of news articles about a company and its supply chain (each annotated with `age_days`, `temporal_regime`, and `temporal_guidance`), return a JSON object with keys:
                    {
                        "overall_sentiment": "bullish/bearish/neutral",
                        "summary": "3 sentence summary of the news landscape",
                        "key_themes": ["theme1", "theme2", "theme3"],
                        "supply_chain_risks": ["risk1", "risk2"],
                        "temporal_supply_chain_effects": [
                            {
                                "event": "short description of the supply chain event",
                                "temporal_regime": "ACTIVE_SHOCK | RECOVERY_LAG | HISTORICAL_STRUCTURAL",
                                "age_days": 0,
                                "supply_chain_effect": "time-calibrated operational or structural impact"
                            }
                        ],
                        "articles": [
                            {
                                "title": "...",
                                "source": "...",
                                "url": "...",
                                "temporal_regime": "ACTIVE_SHOCK | RECOVERY_LAG | HISTORICAL_STRUCTURAL",
                                "relevance": "why this matters according to its temporal regime"
                            }
                        ]
                    }
                    CRITICAL TEMPORAL SUPPLY-CHAIN REASONING RULES:
                    1. ACTIVE_SHOCK (0-30 days old): Treat as an active operational flow event (immediate factory stoppage, spot shortage, or active shipment contradiction).
                    2. RECOVERY_LAG (31-180 days old): The physical shock is in recovery/rebuild; analyze the lagged financial/inventory effect (COGS inflation, expedited air-freight, buffer inventory drawdown, upcoming quarterly gross-margin compression).
                    3. HISTORICAL_STRUCTURAL (>180 days / 1-3+ years old, e.g., a supplier factory fire or walkout 3 years ago): NEVER claim an old historical event causes a current shipment halt or active production bottleneck today! Physical repairs and inventory flows normalized years ago. Instead, analyze its LONG-TERM STRUCTURAL EFFECT today:
                       - Did it expose a Single-Point-of-Failure (SPOF) concentration risk at that hub/supplier?
                       - Did it trigger geographic diversification or dual-sourcing (e.g., shifting capacity to a secondary country or qualifying a second wafer/component supplier)?
                       - How does that historical vulnerability shape baseline supply-chain resilience today?
                    Keep `articles` to at most the top 5 most relevant articles. Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Analyze these temporally-tagged articles for {ticker} ({research['company_name']}): {json.dumps(all_articles[:8])}"
                }
            ]
        )
        logger.info(f"News Agent complete for {ticker}")
        parsed = parse_llm_json(
            response.choices[0].message.content,
            fallback={
                "overall_sentiment": "neutral",
                "summary": f"Recent market coverage for {ticker.upper()} tracks quarterly execution, sector demand, and supply chain logistics across {len(all_articles)} news reports.",
                "key_themes": ["Earnings & Guidance", "Sector Demand", "Supply Chain Operations"],
                "supply_chain_risks": ["Regional supplier concentration", "Component lead-time variability"],
                "articles": [
                    {
                        "title": a.get("title", ""),
                        "source": a.get("source", "Financial Wire"),
                        "url": a.get("url", ""),
                        "temporal_regime": a.get("temporal_regime", "ACTIVE_SHOCK"),
                        "relevance": "Relevant market and operational coverage.",
                    }
                    for a in all_articles[:5]
                ],
            },
        )
        clean_res, stats = guardrail_news_agent(parsed, all_articles)
        clean_res["_evaluation"] = evaluate_agent_output("news", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        mistral_errors.labels(agent_name='news').inc()
        logger.error(f"News agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='news').observe(time.time() - start)    