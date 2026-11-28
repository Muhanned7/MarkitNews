import asyncio
import json
import os
import yfinance as yf
import pandas as pd
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from agents.guardrails import guardrail_technical_agent
from agents.evaluator import evaluate_agent_output
from agents.api_monitor import log_external_api_call
from loguru import logger
import time


async def technical_agent(ticker: str) -> dict:
    logger.info(f"Technical Agent requested for {ticker}")
    agent_calls.labels(agent_name='Technical', ticker=ticker).inc()

    start = time.time()
    try:
        if os.environ.get("MOCK_MODE", "false").lower() == "true":
            await asyncio.sleep(0.3)  # Simulate network latency
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            mock_res = {
                "trend": "bullish" if prof["current_price"] >= prof["ma50"] else "bearish",
                "trend_strength": "moderate",
                "rsi_signal": "overbought" if prof["rsi"] > 70 else ("oversold" if prof["rsi"] < 30 else "neutral"),
                "macd_signal": "bullish" if prof["macd"] >= 0 else "bearish",
                "support_level": prof["support_level"],
                "resistance_level": prof["resistance_level"],
                "short_term_outlook": "bullish" if prof["day_change"] >= 0 else "bearish",
                "key_levels": [f"${prof['support_level']} (Support)", f"${prof['resistance_level']} (Resistance)"],
                "signals": [
                    f"Price trading above 50-day SMA (${prof['ma50']:.2f})" if prof["current_price"] >= prof["ma50"] else f"Price trading below 50-day SMA (${prof['ma50']:.2f})",
                    f"RSI(14) at {prof['rsi']}"
                ],
                "summary": f"{ticker.upper()} is currently trading at ${prof['current_price']:.2f} ({'+' if prof['day_change'] >= 0 else ''}{prof['day_change_pct']:.2f}%). Key support lies at ${prof['support_level']:.2f} and resistance at ${prof['resistance_level']:.2f}.",
                "raw": {
                    "current_price": prof["current_price"],
                    "rsi": prof["rsi"],
                    "rsi_14": prof["rsi"],
                    "macd": prof["macd"],
                    "ma50": prof["ma50"],
                    "ma200": prof["ma200"],
                    "price_vs_ma50": "Above 50-day SMA" if prof["current_price"] >= prof["ma50"] else "Below 50-day SMA",
                    "price_vs_ma200": "Above 200-day SMA" if prof["current_price"] >= prof["ma200"] else "Below 200-day SMA",
                    "volume_vs_average": "Above 20-day avg volume"
                }
            }
            clean_res, stats = guardrail_technical_agent(mock_res)
            clean_res["_evaluation"] = evaluate_agent_output("technical", ticker, clean_res, stats)
            return clean_res

        def fetch_technicals():
            t0 = time.time()
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2y")
            log_external_api_call(
                provider="yfinance",
                endpoint="Ticker.history(2y Technicals)",
                method="GET",
                status_code=200 if not hist.empty else 404,
                latency_ms=(time.time() - t0) * 1000.0,
                caller="technical_agent",
                ticker=ticker,
                query_summary=f"{ticker} 2y OHLCV ({len(hist)} bars)",
                success=(not hist.empty),
            )
            
            if hist.empty:
                return None

            close = hist["Close"]
            volume = hist["Volume"]

            # Moving averages
            ma50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else close.mean()
            ma200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
            current_price = close.iloc[-1]

            # 20-day swing pivots for realistic support & resistance
            swing_low_20d = close.iloc[-20:].min()
            swing_high_20d = close.iloc[-20:].max()

            # RSI (Wilder's exponential smoothing)
            delta = close.diff()
            gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50.0

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            macd_value = macd.iloc[-1]
            signal_value = signal.iloc[-1]

            # Volume
            avg_volume = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else volume.mean()
            current_volume = volume.iloc[-1]

            # 52-week high and low from last 252 bars
            last_252 = close.iloc[-252:] if len(close) >= 252 else close
            high_52w = last_252.max()
            low_52w = last_252.min()

            def safe_num(v, decimals=2):
                if v is None or pd.isna(v):
                    return None
                return round(float(v), decimals)

            return {
                "current_price": safe_num(current_price),
                "ma50": safe_num(ma50),
                "ma200": safe_num(ma200),
                "price_vs_ma50": "Above 50-day SMA" if (ma50 is not None and current_price > ma50) else "Below 50-day SMA",
                "price_vs_ma200": "Above 200-day SMA" if (ma200 is not None and current_price > ma200) else "Below 200-day SMA",
                "swing_support_20d": safe_num(swing_low_20d),
                "swing_resistance_20d": safe_num(swing_high_20d),
                "rsi": safe_num(rsi),
                "rsi_14": safe_num(rsi),
                "macd": safe_num(macd_value, 4),
                "macd_signal": safe_num(signal_value, 4),
                "macd_crossover": "bullish" if (macd_value is not None and signal_value is not None and macd_value > signal_value) else "bearish",
                "avg_volume_20d": round(float(avg_volume)) if not pd.isna(avg_volume) else None,
                "current_volume": round(float(current_volume)) if not pd.isna(current_volume) else None,
                "volume_vs_average": "Above 20-day avg volume" if (current_volume and avg_volume and current_volume > avg_volume) else "Below 20-day avg volume",
                "52_week_high": safe_num(high_52w),
                "52_week_low": safe_num(low_52w),
            }

        raw_data = await asyncio.to_thread(fetch_technicals)

        if not raw_data:
            return {"error": "No price data available"}

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a technical analyst. Given price and indicator data, analyze the stock's technical picture.
                    Return JSON with exactly these keys:
                    {
                        "trend": "bullish/bearish/neutral",
                        "trend_strength": "strong/moderate/weak",
                        "rsi_signal": "overbought/oversold/neutral",
                        "macd_signal": "bullish/bearish",
                        "support_level": 0.0,
                        "resistance_level": 0.0,
                        "short_term_outlook": "bullish/bearish/neutral",
                        "key_levels": ["level1", "level2"],
                        "signals": ["signal1", "signal2"],
                        "summary": "3 sentence technical summary",
                        "raw": {}
                    }
                    Put the raw input data in the raw field.
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"Analyze technicals for {ticker}: {json.dumps(raw_data)}"
                }
            ]
        )
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        clean_res, stats = guardrail_technical_agent(parsed, raw_data)
        clean_res["_evaluation"] = evaluate_agent_output("technical", ticker, clean_res, stats)
        return clean_res
    except Exception as e:
        mistral_errors.labels(agent_name='Technical').inc()
        logger.error(f"Technical agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='technical').observe(time.time() - start)
