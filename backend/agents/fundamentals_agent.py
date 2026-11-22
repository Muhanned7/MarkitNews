import asyncio
import json
import os
import yfinance as yf
import random
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from agents.guardrails import guardrail_fundamentals_agent
from agents.evaluator import evaluate_agent_output
from loguru import logger
import time


MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def fundamentals_agent(ticker: str) -> dict:
    logger.info(f"fundamentals agent requested for {ticker}")
    agent_calls.labels(agent_name='fundamentals', ticker=ticker).inc()
    
    start = time.time()
    try:
        logger.info(f"Running fundamentals agents for {ticker}")
        if MOCK_MODE:
            await asyncio.sleep(0.3) 
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            pe = prof["pe_ratio"]
            roe = prof["return_on_equity"]

            mock_res = {
                "valuation": "overvalued" if pe > 30 else ("undervalued" if pe < 16 else "fairly_valued"),
                "valuation_reasoning": f"The current P/E ratio of {pe} reflects market expectations for {prof['sector']}. With an ROE of {round(roe*100, 1)}%, its valuation aligns with capital efficiency.",
                "financial_health": "strong",
                "health_reasoning": f"Maintains a robust balance sheet with an ROE of {round(roe*100, 1)}%. Debt levels are well-managed relative to equity ({prof['debt_to_equity']}%).",
                "growth_outlook": "moderate" if prof["revenue_growth"] < 0.15 else "strong",
                "growth_reasoning": f"Revenue growth is tracking at {round(prof['revenue_growth']*100, 1)}% annualized, driven by momentum in core {prof['industry']} operations.",
                "key_strengths": ["High return on equity", "Consistent free cash flow generation"],
                "key_weaknesses": ["Valuation multiple compression risks", "Macroeconomic rate sensitivity"],
                "metrics": {
                    "pe_ratio": pe,
                    "forward_pe": prof["forward_pe"],
                    "revenue_growth": prof["revenue_growth"],
                    "profit_margins": prof["profit_margins"],
                    "debt_to_equity": prof["debt_to_equity"],
                    "return_on_equity": roe,
                    "free_cashflow": prof["free_cashflow"]
                },
                "summary": f"{ticker.upper()} shows strong financial discipline. With an ROE of {round(roe*100, 1)}% and steady cash flow, its fundamentals in {prof['sector']} remain sound."
            }
            clean_res, stats = guardrail_fundamentals_agent(mock_res)
            clean_res["_evaluation"] = evaluate_agent_output("fundamentals", ticker, clean_res, stats)
            return clean_res
        def fetch_fundamentals():
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                "company_name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "profit_margins": info.get("profitMargins"),
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                "free_cashflow": info.get("freeCashflow"),
                "dividend_yield": info.get("dividendYield"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
            }

        raw_data = await asyncio.to_thread(fetch_fundamentals)

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a fundamental analyst. Given raw financial metrics, analyze and interpret them.
                    Return JSON with exactly these keys:
                    {
                        "valuation": "overvalued/fairly_valued/undervalued",
                        "valuation_reasoning": "2 sentence explanation",
                        "financial_health": "strong/moderate/weak",
                        "health_reasoning": "2 sentence explanation",
                        "growth_outlook": "high/moderate/low",
                        "growth_reasoning": "2 sentence explanation",
                        "key_strengths": ["strength1", "strength2"],
                        "key_weaknesses": ["weakness1", "weakness2"],
                        "metrics": {
                            "pe_ratio": 0,
                            "forward_pe": 0,
                            "revenue_growth": 0,
                            "profit_margins": 0,
                            "debt_to_equity": 0,
                            "return_on_equity": 0,
                            "free_cashflow": 0
                        },
                        "summary": "3 sentence summary"
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Analyze fundamentals for {ticker}: {json.dumps(raw_data)}"
                }
            ]
        )
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        clean_res, stats = guardrail_fundamentals_agent(parsed, raw_data)
        clean_res["_evaluation"] = evaluate_agent_output("fundamentals", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        mistral_errors.labels(agent_name='fundamentals').inc()
        logger.error(f"fundamentals agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='fundamentals').observe(time.time() - start)    