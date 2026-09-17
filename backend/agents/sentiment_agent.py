import asyncio
import json
import requests
import random
from mistralai.client import Mistral
import os
from agents.client import client
from agents.metrics import agent_calls, agent_latency, mistral_errors
from loguru import logger
import time

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def sentiment_agent(ticker: str, news_data: dict) -> dict:
    logger.info(f"Sentiment Agent requested for {ticker}")
    agent_calls.labels(agent_name='Sentiment', ticker=ticker).inc()

    start = time.time()
    try:
        logger.info(f"Running sentiment agent for {ticker}")
        if MOCK_MODE:
            await asyncio.sleep(0.5)  # Simulate network latency
            
            # Seed based on ticker and current news sentiment to stay "consistent"
            seed_val = sum(ord(c) for c in ticker)
            random.seed(seed_val)
            
            # Logic to make the mock feel reactive to the news_data passed in
            news_sent = news_data.get('overall_sentiment', 'neutral')
            
            return {
                "overall_sentiment": news_sent,
                "retail_sentiment": "bullish" if news_sent == "bullish" else "neutral",
                "institutional_sentiment": "bullish",
                "sentiment_score": random.randint(6, 9) if news_sent == "bullish" else 5,
                "analyst_consensus": "buy",
                "key_sentiment_drivers": [
                    f"Positive news coverage regarding {ticker}'s latest earnings",
                    "Strong institutional accumulation over the last 30 days",
                    "High social media engagement on StockTwits and Reddit"
                ],
                "summary": f"Market sentiment for {ticker} is currently {news_sent}, driven by strong institutional backing. Retail interest remains high with a focus on long-term growth catalysts."
            }
        def fetch_finviz():
            resp = requests.get(
                f"https://finviz.com/quote.ashx?t={ticker}",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            return resp.text

        finviz_html = await asyncio.to_thread(fetch_finviz)

        response = await asyncio.to_thread(
            client.chat.complete,
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": """You are a market sentiment analyst. Given Finviz HTML and news sentiment data,
                    extract analyst ratings and sentiment signals. Return JSON with exactly these keys:
                    {
                        "overall_sentiment": "bullish/bearish/neutral",
                        "retail_sentiment": "bullish/bearish/neutral",
                        "institutional_sentiment": "bullish/bearish/neutral",
                        "sentiment_score": 1-10,
                        "analyst_consensus": "buy/hold/sell",
                        "key_sentiment_drivers": ["driver1", "driver2"],
                        "summary": "2 sentence summary"
                    }
                    Return only raw JSON, no markdown."""
                },
                {
                    "role": "user",
                    "content": f"""Analyze sentiment for {ticker}:
                    News sentiment: {news_data.get('overall_sentiment')}
                    News themes: {news_data.get('key_themes')}
                    Supply chain risks: {news_data.get('supply_chain_risks')}
                    Finviz HTML (extract analyst ratings): {finviz_html[:3000]}"""
                }
            ]
        )
        logger.info(f"Sentiment Agent complete for {ticker}")
        raw = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        mistral_errors.labels(agent_name='Sentiment').inc()
        logger.error(f"Sentiment agent failed for {ticker}: {e}")
        raise
    finally:
        agent_latency.labels(agent_name='Sentiment').observe(time.time() - start)