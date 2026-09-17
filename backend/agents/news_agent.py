import asyncio
import json
import requests
from mistralai.client import Mistral
import os
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from loguru import logger
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def research_agent(ticker: str) -> dict:
    logger.info(f"Research requested for {ticker}")
    try:
        logger.info(f"Running Research agents for {ticker}")
        if MOCK_MODE:
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
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except Exception as e:
        logger.error(f"Reasearch Agent failed for {ticker}: {e}")
        raise


async def news_agent(ticker: str) -> dict:
    logger.info(f"News Agent requested for {ticker}")
    agent_calls.labels(agent_name='news', ticker=ticker).inc()

    start = time.time()
    try:
        logger.info(f"Running News agent for {ticker}")
        
        if MOCK_MODE:
            await asyncio.sleep(0.8) # News takes longer as it "searches"
            return {
                "overall_sentiment": "bullish",
                "summary": f"{ticker.upper()} is seeing strong positive momentum following reports of diversified supply chain logistics. Market analysts are focusing on the reduced dependency on single-region suppliers. Increased institutional interest is noted ahead of the upcoming product cycle.",
                "key_themes": ["Supply Chain Resilience", "Next-Gen AI Integration", "Market Share Expansion"],
                "supply_chain_risks": ["Potential export restrictions in Asia", "Rising costs of raw silicon"],
                "articles": [
                    {
                        "title": f"Why {ticker} is leads the sector in 2026",
                        "source": "MarketWatch",
                        "url": "https://example.com/article1",
                        "relevance": "Highlights the company's competitive advantage in supply chain management."
                    },
                    {
                        "title": f"New Policy Impacts for {ticker} Suppliers",
                        "source": "Reuters",
                        "url": "https://example.com/article2",
                        "relevance": "Discusses potential cost increases for raw materials."
                    }
                ]
            }

        research = await research_agent(ticker)
        queries = research.get("search_queries", [ticker])

        def fetch_news(query):
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "pageSize": 5,
                    "sortBy": "publishedAt",
                    "apiKey": os.environ["NEWSAPI_KEY"]
                }
            )
            return resp.json().get("articles", [])

        all_articles_nested = await asyncio.gather(
            *[asyncio.to_thread(fetch_news, q) for q in queries]
        )

        seen = set()
        all_articles = []
        for articles in all_articles_nested:
            for article in articles:
                if article["url"] not in seen:
                    seen.add(article["url"])
                    all_articles.append({
                        "title": article["title"],
                        "description": article["description"],
                        "source": article["source"]["name"],
                        "url": article["url"],
                        "published": article["publishedAt"]
                    })

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a financial news analyst. Given a list of news articles about a company and its supply chain, 
                    return a JSON object with keys:
                    {
                        "overall_sentiment": "bullish/bearish/neutral",
                        "summary": "3 sentence summary of the news landscape",
                        "key_themes": ["theme1", "theme2", "theme3"],
                        "supply_chain_risks": ["risk1", "risk2"],
                        "articles": [{"title": "...", "source": "...", "url": "...", "relevance": "why this matters"}]
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Analyze these articles for {ticker} ({research['company_name']}): {json.dumps(all_articles)}"
                }
            ]
        )
        logger.info(f"News Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='news').inc()
        logger.error(f"News agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='news').observe(time.time() - start)    