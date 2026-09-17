import asyncio
import json
import os
import yfinance as yf
import numpy as np
import random
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from loguru import logger
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def risk_agent(ticker: str) -> dict:
    logger.info(f"Risk Agent requested for {ticker}")
    agent_calls.labels(agent_name='Risk', ticker=ticker).inc()
    
    start = time.time()
    try:
        logger.info(f"Running Risk agent for {ticker}")
        if MOCK_MODE:
            await asyncio.sleep(0.5)
            return {
                "overall_risk": "medium",
                "volatility_assessment": "medium",
                "beta_assessment": "aggressive",
                "sharpe_assessment": "good",
                "short_squeeze_risk": "low",
                "key_risks": ["Market volatility exposure", "Regulatory risks", "Concentration in tech sector"],
                "risk_mitigants": ["Diversified revenue streams", "Strong cash position"],
                "max_drawdown_assessment": "mild",
                "var_interpretation": f"There is a 5% chance of losing more than 2% in a single day for {ticker}.",
                "metrics": {
                    "beta": 1.05,
                    "volatility": 0.22,
                    "sharpe_ratio": 1.4,
                    "max_drawdown": -0.14,
                    "var_95": -0.02
                },
                "summary": f"{ticker} exhibits moderate overall risk with a beta slightly above 1. The stock has a good Sharpe ratio suggesting efficient risk-adjusted returns. Low short squeeze risk and diversified revenue streams help balance the risk profile."
            }
        def fetch_risk_data():
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1y")

            if hist.empty:
                return None

            close = hist["Close"]
            daily_returns = close.pct_change().dropna()

            # Beta
            beta = info.get("beta")

            # Volatility (annualized)
            volatility = daily_returns.std() * np.sqrt(252)

            # Sharpe ratio (assuming risk free rate of 5%)
            risk_free_rate = 0.05
            avg_daily_return = daily_returns.mean()
            sharpe_ratio = (avg_daily_return * 252 - risk_free_rate) / (daily_returns.std() * np.sqrt(252))

            # Max drawdown
            rolling_max = close.cummax()
            drawdown = (close - rolling_max) / rolling_max
            max_drawdown = drawdown.min()

            # Value at Risk (95% confidence)
            var_95 = daily_returns.quantile(0.05)

            # Average True Range (ATR) for volatility
            high = hist["High"]
            low = hist["Low"]
            atr = (high - low).rolling(window=14).mean().iloc[-1]

            return {
                "beta": round(float(beta), 2) if beta else None,
                "annualized_volatility": round(float(volatility), 4),
                "sharpe_ratio": round(float(sharpe_ratio), 2),
                "max_drawdown": round(float(max_drawdown), 4),
                "var_95": round(float(var_95), 4),
                "atr_14": round(float(atr), 2),
                "short_ratio": info.get("shortRatio"),
                "shares_short": info.get("sharesShort"),
                "float_shares": info.get("floatShares"),
                "short_percent_of_float": info.get("shortPercentOfFloat"),
            }

        raw_data = await asyncio.to_thread(fetch_risk_data)

        if not raw_data:
            return {"error": "No data available"}

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a risk management analyst. Given risk metrics, produce a thorough risk analysis.
                    Return JSON with exactly these keys:
                    {
                        "overall_risk": "low/medium/high/very_high",
                        "volatility_assessment": "low/medium/high",
                        "beta_assessment": "defensive/market_neutral/aggressive",
                        "sharpe_assessment": "poor/acceptable/good/excellent",
                        "short_squeeze_risk": "low/medium/high",
                        "key_risks": ["risk1", "risk2", "risk3"],
                        "risk_mitigants": ["mitigant1", "mitigant2"],
                        "max_drawdown_assessment": "mild/moderate/severe",
                        "var_interpretation": "one sentence explaining the VaR",
                        "metrics": {
                            "beta": 0.0,
                            "volatility": 0.0,
                            "sharpe_ratio": 0.0,
                            "max_drawdown": 0.0,
                            "var_95": 0.0
                        },
                        "summary": "3 sentence risk summary"
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Analyze risk for {ticker}: {json.dumps(raw_data, default=str)}"
                }
            ]
        )
        logger.info(f"risk Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='risk').inc()
        logger.error(f"risk agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='risk').observe(time.time() - start)