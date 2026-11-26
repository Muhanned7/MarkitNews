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

TICKER_SPECIFIC_CATALYSTS = {
    "AAPL": {
        "moat_sources": ["iOS & App Store ecosystem lock-in (2.2B+ active devices)", "Custom Apple Silicon (M-series & A-series) integration", "High-margin Services recurring revenue (~74% gross margin)"],
        "growth_catalysts": ["iPhone upgrade cycle driven by on-device Apple Intelligence", "Double-digit Services revenue expansion (App Store, iCloud, Apple Pay)", "Supply-chain diversification into Tamil Nadu, India and Vietnam"],
        "key_risks": ["Antitrust scrutiny over App Store fee structure & default search payments", "Greater China smartphone market share competition", "Consumer hardware replacement cycle elongation"],
        "thesis": "Apple combines an unmatched installed base of over 2.2 billion active devices with high-margin Services expansion and custom Apple Silicon leadership."
    },
    "NVDA": {
        "moat_sources": ["CUDA software & developer ecosystem lock-in", "Full-stack AI data center architecture (Blackwell GPU, NVLink, InfiniBand)", "Leading-edge TSMC CoWoS packaging allocation"],
        "growth_catalysts": ["Blackwell rack-scale data center ramp across hyperscalers", "Sovereign AI infrastructure buildouts globally", "NIM & enterprise software recurring revenue growth"],
        "key_risks": ["Hyperscaler custom ASIC internal silicon competition (TPU, Trainium)", "Export control restrictions on advanced AI accelerators", "Foundry & HBM3e packaging supply concentration at TSMC and SK Hynix"],
        "thesis": "NVIDIA commands the dominant full-stack compute platform for generative AI infrastructure, pairing proprietary CUDA software lock-in with rapid Blackwell rack deployments."
    },
    "MSFT": {
        "moat_sources": ["Enterprise Microsoft 365 & Active Directory standard", "Hyperscale Azure cloud infrastructure footprint", "Deep enterprise distribution and developer tooling (GitHub, VS Code)"],
        "growth_catalysts": ["Azure AI and enterprise cloud workload migration acceleration", "Microsoft 365 Copilot commercial seat monetization", "Operating leverage across commercial cloud and cybersecurity suites"],
        "key_risks": ["Elevated data center capital expenditure pressuring near-term free cash flow margins", "Cloud price competition from AWS and Google Cloud", "Enterprise IT software budget optimization"],
        "thesis": "Microsoft leverages its entrenched enterprise productivity franchise and hyperscale Azure infrastructure to monetize enterprise AI workloads at scale."
    },
    "TSLA": {
        "moat_sources": ["Vertically integrated EV manufacturing & Gigafactory scale", "Supercharger network standard (NACS) & Megapack energy storage scale", "Fleet telemetry dataset for Full Self-Driving (FSD) neural networks"],
        "growth_catalysts": ["Utility-scale Megapack stationary storage deployment growth", "FSD software attach-rate expansion and autonomous fleet milestones", "Next-generation lower-cost vehicle platform unit cost reductions"],
        "key_risks": ["Automotive gross margin compression from global EV price competition", "Regulatory & liability scrutiny over ADAS / FSD software", "Tariff and battery raw-material supply chain exposure"],
        "thesis": "Tesla balances cyclical automotive margin pressure against rapid high-margin growth in utility-scale Megapack energy storage and autonomous software."
    }
}

MOCK_MODE = os.environ.get("MOCK_MODE", "true").lower() == "true"
async def equity_research_agent(ticker: str, consensus: str = None, street_targets: dict = None) -> dict:

    logger.info(f"equity research agent requested for {ticker}")
    agent_calls.labels(agent_name='equity_research', ticker=ticker).inc()
    
    start = time.time()
    try:
        if os.environ.get("MOCK_MODE", "true").lower() == "true":
            await asyncio.sleep(0.3)  # Simulate network latency
            from agents.mock_market_data import get_deterministic_mock_profile
            prof = get_deterministic_mock_profile(ticker)
            
            target_price = prof["target_price"]
            current_price = prof["current_price"]
            upside = round(((target_price / current_price) - 1) * 100, 2)
            t_up = ticker.upper().strip()
            spec = TICKER_SPECIFIC_CATALYSTS.get(t_up, {
                "moat_sources": [f"Established market share in {prof['industry']}", "Recurring customer relationships & switching costs", "Scale cost advantages"],
                "growth_catalysts": [f"Operating margin expansion across core {prof['industry']} lines", "Disciplined capital allocation and free cash flow conversion"],
                "key_risks": [f"Valuation multiple sensitivity (trailing P/E {prof['pe_ratio']}x)", f"Macroeconomic cyclicality in {prof['sector']}"],
                "thesis": f"{prof['company_name']} ({t_up}) maintains a disciplined competitive position in {prof['industry']} ({prof['sector']}) with free cash flow of ${prof['free_cashflow']:,}."
            })

            mock_res = {
                "recommendation": prof["recommendation"],
                "conviction": prof["conviction"],
                "analyst_consensus": consensus or prof["recommendation"],
                "price_target": target_price,
                "upside_downside": f"{'+' if upside >= 0 else ''}{upside}% {'upside' if upside >= 0 else 'downside'} from current price",
                "competitive_position": "leader" if prof["conviction"] >= 7 else "challenger",
                "moat": "wide" if prof["conviction"] >= 8 else ("narrow" if prof["conviction"] >= 6 else "none"),
                "moat_sources": spec["moat_sources"],
                "growth_catalysts": spec["growth_catalysts"],
                "key_risks": spec["key_risks"],
                "sector_outlook": "positive" if upside >= 0 else "neutral",
                "investment_thesis": f"{spec['thesis']} Based on our 63-day scenario model, we project an expected return of {prof['expected_return']}% toward a ${target_price:.2f} target price.",
                "summary": f"Our analysis yields a {prof['recommendation'].upper()} rating for {t_up} (conviction {prof['conviction']}/10) with a 63-day target of ${target_price:.2f} ({'+' if upside >= 0 else ''}{upside}%)."
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