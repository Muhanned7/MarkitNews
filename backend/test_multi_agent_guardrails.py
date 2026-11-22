import asyncio
from agents.news_agent import news_agent
from agents.sentiment_agent import sentiment_agent
from agents.technical_agent import technical_agent
from agents.fundamentals_agent import fundamentals_agent
from agents.risk_agent import risk_agent
from agents.equity_reasearch_agent import equity_research_agent
from main import synthesizer

async def test_all():
    ticker = "AAPL"
    print(f"--- TESTING ALL 6 FINANCIAL AGENTS FOR {ticker} ---")
    news = await news_agent(ticker)
    sentiment = await sentiment_agent(ticker, news)
    fundamentals = await fundamentals_agent(ticker)
    technical = await technical_agent(ticker)
    equity = await equity_research_agent(ticker)
    risk = await risk_agent(ticker)
    synth = await synthesizer(ticker, news, sentiment, fundamentals, technical, equity, risk)
    
    agents = [
        ("News Agent", news),
        ("Sentiment Agent", sentiment),
        ("Fundamentals Agent", fundamentals),
        ("Technical Agent", technical),
        ("Equity Research Agent", equity),
        ("Risk Agent", risk),
        ("Portfolio Synthesizer", synth)
    ]
    
    print("\n--- EVALUATION AND GUARDRAIL RESULTS ---")
    for name, res in agents:
        ev = res.get("_evaluation", {})
        grade = ev.get("grade", "N/A")
        score = ev.get("overall_quality_score", 0.0)
        faith = ev.get("faithfulness_score", 0.0)
        hallucinations = ev.get("hallucinations_detected", 0)
        print(f"[{name}] Grade: {grade} | Score: {score:.2f} | Faithfulness: {faith:.2f} | Hallucinations: {hallucinations}")

if __name__ == "__main__":
    asyncio.run(test_all())
