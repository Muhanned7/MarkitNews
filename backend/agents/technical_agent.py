import asyncio
import json
import os
import yfinance as yf
import pandas as pd
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from loguru import logger
import time


MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def technical_agent(ticker: str) -> dict:
    logger.info(f"Technical Agent requested for {ticker}")
    agent_calls.labels(agent_name='Technical', ticker=ticker).inc()

    start = time.time()
    try:
        if MOCK_MODE:
            await asyncio.sleep(0.5)  # Simulate network latency
            return {
                "trend": "bullish",
                "trend_strength": "moderate",
                "rsi_signal": "neutral",
                "macd_signal": "bullish",
                "support_level": 185.50,
                "resistance_level": 198.20,
                "short_term_outlook": "bullish",
                "key_levels": ["$185.50 (50-day MA)", "$200.00 (Psychological)"],
                "signals": ["MACD Bullish Crossover", "Price holding above 200-day MA"],
                "summary": f"{ticker} is currently showing a constructive technical setup. The price is consolidating above key support levels with increasing volume. Indicators suggest a potential breakout if it clears current resistance.",
                "raw": {
                    "current_price": 192.25,
                    "rsi": 54.2,
                    "macd": 0.45,
                    "volume_vs_average": "above"
                }
            }

        def fetch_technicals():
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            
            if hist.empty:
                return None

            close = hist["Close"]
            volume = hist["Volume"]

            # Moving averages
            ma50 = close.rolling(window=50).mean().iloc[-1]
            ma200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
            current_price = close.iloc[-1]

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            macd_value = macd.iloc[-1]
            signal_value = signal.iloc[-1]

            # Volume
            avg_volume = volume.rolling(window=20).mean().iloc[-1]
            current_volume = volume.iloc[-1]

            return {
                "current_price": round(float(current_price), 2),
                "ma50": round(float(ma50), 2),
                "ma200": round(float(ma200), 2) if ma200 else None,
                "price_vs_ma50": "above" if current_price > ma50 else "below",
                "price_vs_ma200": "above" if ma200 and current_price > ma200 else "below",
                "rsi": round(float(rsi), 2),
                "macd": round(float(macd_value), 4),
                "macd_signal": round(float(signal_value), 4),
                "macd_crossover": "bullish" if macd_value > signal_value else "bearish",
                "avg_volume_20d": round(float(avg_volume)),
                "current_volume": round(float(current_volume)),
                "volume_vs_average": "above" if current_volume > avg_volume else "below",
                "52_week_high": round(float(close.rolling(window=252).max().iloc[-1]), 2),
                "52_week_low": round(float(close.rolling(window=252).min().iloc[-1]), 2),
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
        logger.info(f"Technical Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='Sentiment').inc()
        logger.error(f"Technical agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='technical').observe(time.time() - start)
