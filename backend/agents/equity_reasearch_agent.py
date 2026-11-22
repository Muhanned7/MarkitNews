import asyncio
import json
import os
import yfinance as yf
import random
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from agents.guardrails import guardrail_equity_agent
from agents.evaluator import evaluate_agent_output
from loguru import logger
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def equity_research_agent(ticker: str, consensus: str = None, street_targets: dict = None) -> dict:

    logger.info(f"equity research agent requested for {ticker}")
    agent_calls.labels(agent_name='equity_research', ticker=ticker).inc()
    
    start = time.time()
    try:
        if MOCK_MODE:
            await asyncio.sleep(0.3)  # Simulate network latency
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            
            target_price = prof["target_price"]
            current_price = prof["current_price"]
            upside = round(((target_price / current_price) - 1) * 100, 2)

            mock_res = {
                "recommendation": prof["recommendation"],
                "conviction": prof["conviction"],
                "analyst_consensus": consensus or prof["recommendation"],
                "price_target": target_price,
                "upside_downside": f"{'+' if upside >= 0 else ''}{upside}% {'upside' if upside >= 0 else 'downside'} from current price",
                "competitive_position": "leader" if prof["conviction"] >= 7 else "challenger",
                "moat": "wide" if prof["conviction"] >= 8 else ("narrow" if prof["conviction"] >= 6 else "none"),
                "moat_sources": ["High switching costs", "Brand ecosystem", "Proprietary technology"],
                "growth_catalysts": ["Expansion into AI services", "Increased enterprise adoption"],
                "key_risks": ["Valuation multiple compression", "Macro headwinds"],
                "sector_outlook": "positive",
                "investment_thesis": f"{ticker.upper()} maintains a strong position in {prof['sector']} with an expected return of {prof['expected_return']}%. Target price is ${target_price:.2f} based on 63-day horizon scenarios.",
                "summary": f"Our analysis yields a {prof['recommendation'].upper()} rating for {ticker.upper()} (conviction {prof['conviction']}/10) with an expected 63-day target of ${target_price:.2f}."
            }
            clean_res, stats = guardrail_equity_agent(mock_res, {})
            if consensus:
                clean_res["analyst_consensus"] = consensus
            if street_targets:
                clean_res["analyst_price_targets"] = street_targets
            clean_res["_evaluation"] = evaluate_agent_output("equity_research", ticker, clean_res, stats)
            return clean_res

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
                        "recommendation": "strong_buy/buy/hold/sell/strong_sell",
                        "conviction": 1-10,
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
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        clean_res, stats = guardrail_equity_agent(parsed, raw_data)
        if consensus:
            clean_res["analyst_consensus"] = consensus
        if street_targets:
            clean_res["analyst_price_targets"] = street_targets
        clean_res["_evaluation"] = evaluate_agent_output("equity_research", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        mistral_errors.labels(agent_name='equity_research').inc()
        logger.error(f"equity research agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='equity_research').observe(time.time() - start)    