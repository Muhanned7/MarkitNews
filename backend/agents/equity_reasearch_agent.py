import asyncio
import json
import os
import yfinance as yf
import random
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from loguru import logger
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def equity_research_agent(ticker: str) -> dict:

    logger.info(f"fundamentals agent requested for {ticker}")
    agent_calls.labels(agent_name='fundamentals', ticker=ticker).inc()
    
    start = time.time()
    try:
        if MOCK_MODE:
            await asyncio.sleep(0.5)  # Simulate network latency
            
            # Consistent seeding based on ticker
            seed = sum(ord(c) for c in ticker)
            random.seed(seed)
            
            # Logic to make the mock feel dynamic
            target_price = 225.50
            current_price = 192.25
            upside = round(((target_price / current_price) - 1) * 100, 2)

            return {
                "analyst_consensus": "strong_buy",
                "price_target": target_price,
                "upside_downside": f"{upside}% upside from current price",
                "competitive_position": "leader",
                "moat": "wide",
                "moat_sources": ["High switching costs", "Brand ecosystem", "Proprietary technology"],
                "growth_catalysts": ["Expansion into AI services", "Increased enterprise adoption"],
                "key_risks": ["Regulatory scrutiny on app store", "Supply chain concentration in Asia"],
                "sector_outlook": "positive",
                "investment_thesis": f"{ticker.upper()} maintains a dominant position in its core markets with industry-leading margins. The shift toward high-margin services provides a significant runway for earnings growth. We believe the current valuation does not fully account for its AI integration potential.",
                "summary": f"Analysts are overwhelmingly positive on {ticker}, citing a wide economic moat and strong cash flow generation. The consensus price target suggests double-digit upside. Overall, the stock remains a top pick for long-term growth-oriented portfolios."
            }

        def fetch_equity_data():
            stock = yf.Ticker(ticker)
            info = stock.info

            # Analyst recommendations
            recommendations = stock.recommendations
            rec_summary = stock.recommendations_summary

            # Price targets
            analyst_price_targets = stock.analyst_price_targets

            # Earnings estimates
            earnings_estimate = stock.earnings_estimate
            revenue_estimate = stock.revenue_estimate

            return {
                "company_name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "business_summary": info.get("longBusinessSummary", "")[:500],
                "employees": info.get("fullTimeEmployees"),
                "country": info.get("country"),
                "website": info.get("website"),
                "current_price": info.get("currentPrice"),
                "analyst_price_targets": analyst_price_targets if analyst_price_targets is not None else {},
                "recommendations_summary": rec_summary if rec_summary is not None else {},
                "recent_recommendations": recommendations.tail(10) if recommendations is not None else {},
                "earnings_estimate": earnings_estimate if earnings_estimate is not None else {},
                "revenue_estimate": revenue_estimate if revenue_estimate is not None else {},
            }

        raw_data = await asyncio.to_thread(fetch_equity_data)

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a senior equity research analyst. Given company data, analyst ratings and estimates,
                    produce a thorough equity research analysis. Return JSON with exactly these keys:
                    {
                        "analyst_consensus": "strong_buy/buy/hold/sell/strong_sell",
                        "price_target": 0.0,
                        "upside_downside": "X% upside/downside from current price",
                        "competitive_position": "leader/challenger/follower/niche",
                        "moat": "wide/narrow/none",
                        "moat_sources": ["source1", "source2"],
                        "growth_catalysts": ["catalyst1", "catalyst2"],
                        "key_risks": ["risk1", "risk2"],
                        "sector_outlook": "positive/neutral/negative",
                        "investment_thesis": "3 sentence thesis",
                        "summary": "3 sentence summary"
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Produce equity research for {ticker}: {json.dumps(raw_data, default=str)}"
                }
            ]
        )
        logger.info(f"fundamentals Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='equity_research').inc()
        logger.error(f"equity research agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='equity_research').observe(time.time() - start)    