import asyncio
import json
import os
import yfinance as yf
import numpy as np
import random
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from agents.guardrails import guardrail_risk_agent
from agents.evaluator import evaluate_agent_output
from agents.api_monitor import log_external_api_call
from loguru import logger
import time

def _is_mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "false").lower() == "true"

async def risk_agent(ticker: str) -> dict:
    logger.info(f"Risk Agent requested for {ticker}")
    agent_calls.labels(agent_name='Risk', ticker=ticker).inc()
    
    start = time.time()
    try:
        logger.info(f"Running Risk agent for {ticker}")
        if _is_mock_mode():
            await asyncio.sleep(0.3)
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            var_pct = abs(round(prof["var_95_1d"] * 100, 2))
            vol_pct = round(prof["annualized_volatility"] * 100, 1)
            beta_val = round(prof["beta"], 2)
            mock_res = {
                "overall_risk": "high" if prof["annualized_volatility"] > 0.35 else ("low" if prof["annualized_volatility"] < 0.20 else "medium"),
                "volatility_assessment": "high" if prof["annualized_volatility"] > 0.35 else ("low" if prof["annualized_volatility"] < 0.20 else "medium"),
                "beta_assessment": "Aggressive (moves more than market)" if prof["beta"] > 1.2 else ("Defensive (moves less than market)" if prof["beta"] < 0.8 else "≈ Market"),
                "sharpe_assessment": "strong" if prof["sharpe_ratio"] > 1.2 else ("weak" if prof["sharpe_ratio"] < 0.5 else "good"),
                "short_squeeze_risk": "low",
                "key_risks": [
                    f"Market volatility exposure (annualized vol: {vol_pct:.1f}%)",
                    f"Systematic market risk (beta: {beta_val:.2f} vs benchmark)",
                    f"Max 1-year drawdown: {prof['max_drawdown'] * 100:.1f}%"
                ],
                "risk_mitigants": ["Diversified operating revenue", "Adequate liquidity buffers"],
                "max_drawdown_assessment": "severe" if prof["max_drawdown"] < -0.25 else ("moderate" if prof["max_drawdown"] < -0.15 else "mild"),
                "var_interpretation": f"There is a 5% historical probability of a 1-day decline exceeding {var_pct:.2f}% for {ticker.upper()}.",
                "metrics": {
                    "beta": prof["beta"],
                    "volatility": prof["annualized_volatility"],
                    "annualized_volatility": prof["annualized_volatility"],
                    "ewma_volatility": prof["ewma_volatility"],
                    "sharpe_ratio": prof["sharpe_ratio"],
                    "sortino_ratio": prof["sortino_ratio"],
                    "max_drawdown": prof["max_drawdown"],
                    "max_drawdown_peak_date": prof.get("max_drawdown_peak_date", "2024-01-18"),
                    "max_drawdown_trough_date": prof.get("max_drawdown_trough_date", "2024-04-19"),
                    "days_to_recover": prof.get("days_to_recover", "not recovered"),
                    "var_95": prof["var_95_1d"],
                    "var_95_parametric": prof.get("var_95_parametric", round(prof["var_95_1d"] * 0.95, 4)),
                    "var_99": prof["var_99_1d"],
                    "cvar_975": prof["cvar_975_1d"],
                    "r_squared": prof["r_squared"],
                    "adv_20d_dollars": prof["adv_20d_dollars"],
                    "bid_ask_spread_bps": prof["bid_ask_spread_bps"]
                },
                "summary": f"{ticker.upper()} exhibits an annualized volatility of {vol_pct:.1f}% and a beta of {beta_val:.2f} vs SPY. Daily 95% historical VaR stands at {var_pct:.2f}%, with a Sharpe ratio of {prof['sharpe_ratio']}."
            }
            clean_res, stats = guardrail_risk_agent(mock_res, ticker=ticker)
            clean_res["_evaluation"] = evaluate_agent_output("risk", ticker, clean_res, stats)
            return clean_res
        def fetch_risk_data():
            t0 = time.time()
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            hist = stock.history(period="1y")
            log_external_api_call(
                provider="yfinance",
                endpoint="Ticker.history(1y) + info",
                method="GET",
                status_code=200 if not hist.empty else 404,
                latency_ms=(time.time() - t0) * 1000.0,
                caller="risk_agent",
                ticker=ticker,
                query_summary=f"{ticker} 1y OHLCV ({len(hist)} bars)",
                success=(not hist.empty),
            )

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
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        clean_res, stats = guardrail_risk_agent(parsed, raw_data, ticker=ticker)
        clean_res["_evaluation"] = evaluate_agent_output("risk", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        mistral_errors.labels(agent_name='risk').inc()
        logger.error(f"risk agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='risk').observe(time.time() - start)