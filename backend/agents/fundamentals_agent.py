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
async def fundamentals_agent(ticker: str) -> dict:
    logger.info(f"fundamentals agent requested for {ticker}")
    agent_calls.labels(agent_name='fundamentals', ticker=ticker).inc()
    
    start = time.time()
    try:
        logger.info(f"Running fundamentals agents for {ticker}")
        if MOCK_MODE:
            await asyncio.sleep(0.5) 
            seed = sum(ord(c) for c in ticker)
            random.seed(seed)
            
            # Consistent mock values
            pe = round(random.uniform(20.0, 35.0), 2)
            roe = round(random.uniform(0.30, 0.60), 4)

            return {
                "valuation": "overvalued" if pe > 30 else "fairly_valued",
                "valuation_reasoning": f"The current P/E ratio of {pe} is slightly above the sector average. However, it is justified by strong premium brand positioning.",
                "financial_health": "strong",
                "health_reasoning": f"Maintains a robust balance sheet with an ROE of {round(roe*100, 2)}%. Debt levels are well-managed relative to equity.",
                "growth_outlook": "moderate",
                "growth_reasoning": "Revenue growth remains steady in core segments, though emerging markets show higher potential volatility.",
                "key_strengths": ["High return on equity", "Consistent free cash flow generation"],
                "key_weaknesses": ["Premium valuation limits upside", "Regulatory headwind risks"],
                "metrics": {
                    "pe_ratio": pe,
                    "forward_pe": round(pe * 0.9, 2),
                    "revenue_growth": 0.085,
                    "profit_margins": 0.25,
                    "debt_to_equity": 105.2,
                    "return_on_equity": roe,
                    "free_cashflow": 95000000000
                },
                "summary": f"{ticker.upper()} shows strong financial discipline. While the stock isn't cheap, its ability to generate cash and maintain high margins makes it a core tech holding. Outlook remains stable."
            }
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
        logger.info(f"fundamentals Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='news').inc()
        logger.error(f"fundamentals agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='fundamentals').observe(time.time() - start)    