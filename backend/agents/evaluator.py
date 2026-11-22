import json
from typing import Dict, Any
from loguru import logger
from agents.db import query
from agents.metrics import (
    agent_faithfulness_score,
    agent_evaluation_score,
    agent_hallucinations_detected_total
)

def evaluate_agent_output(
    agent_name: str,
    ticker: str,
    output_data: Dict[str, Any],
    guardrail_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluates semantic output and records observability metrics for financial analysis agents:
    1. Faithfulness Score (Grounding)
    2. Numerical / Categorical Consistency Score
    3. Completeness Score
    4. Overall Quality Score & Grade
    5. Audit to PostgreSQL table `agent_evaluations`
    6. Prometheus time-series metric export
    """
    clean_t = ticker.upper().strip()
    clean_agent = agent_name.lower().strip()

    faithfulness = guardrail_stats.get("faithfulness", 1.0)
    consistency = guardrail_stats.get("consistency", 1.0)
    completeness = guardrail_stats.get("completeness", 1.0)
    hallucinations_detected = guardrail_stats.get("hallucinations_detected", 0)
    warnings = list(guardrail_stats.get("warnings", []))

    COMPANY_ALIASES = {
        "AAPL": ["APPLE", "IPHONE", "MACBOOK", "IOS", "TIM COOK"],
        "NVDA": ["NVIDIA", "JENSEN HUANG", "GEFORCE", "RTX", "CUDA", "BLACKWELL"],
        "TSLA": ["TESLA", "ELON MUSK", "CYBERTRUCK", "GIGAFACTORY"],
        "JPM": ["JPMORGAN", "JP MORGAN", "CHASE", "JAMIE DIMON"],
        "MSFT": ["MICROSOFT", "AZURE", "SATYA NADELLA", "WINDOWS", "COPILOT"],
        "GOOGL": ["GOOGLE", "ALPHABET", "SUNDAR PICHAI", "YOUTUBE", "GEMINI"],
        "AMZN": ["AMAZON", "AWS", "ANDY JASSY", "PRIME"]
    }

    # Domain-specific semantic consistency & hallucination checks
    if clean_agent in ("equity_research", "portfolio_manager"):
        rec = str(output_data.get("recommendation", "")).lower()
        upside_str = str(output_data.get("upside_downside", "")).lower()
        if ("buy" in rec and "downside" in upside_str) or ("sell" in rec and "upside" in upside_str):
            hallucinations_detected += 1
            consistency = max(0.2, round(consistency - 0.4, 2))
            warnings.append(f"Semantic contradiction: recommendation '{rec.upper()}' conflicts with upside/downside assessment '{output_data.get('upside_downside')}'.")

    if clean_agent == "equity_research":
        moat = str(output_data.get("moat", "")).lower()
        metrics = output_data.get("metrics") or output_data.get("raw", {})
        roe = metrics.get("return_on_equity")
        pm = metrics.get("profit_margins")
        if "wide" in moat:
            if (roe is not None and roe < 0.10) or (pm is not None and pm < 0.10):
                hallucinations_detected += 1
                consistency = max(0.3, round(consistency - 0.3, 2))
                warnings.append(f"Ungrounded economic moat: claimed 'wide' moat but Return on Equity ({roe if roe is not None else 'N/A'}) or Profit Margin ({pm if pm is not None else 'N/A'}) is below the 10% structural threshold.")

    if clean_agent == "risk":
        metrics = output_data.get("metrics", {})
        vol = metrics.get("volatility") or metrics.get("annualized_volatility")
        vol_desc = str(output_data.get("volatility_assessment", "")).lower()
        # Volatility thresholds: < 20% low, 20-40% medium, > 40% high
        if vol is not None:
            if vol >= 0.20 and "low" in vol_desc:
                hallucinations_detected += 1
                consistency = max(0.3, round(consistency - 0.3, 2))
                warnings.append(f"Inconsistent volatility labeling: Annualized volatility {vol:.1%} is >= 20% but labeled as 'low'.")
            elif vol >= 0.40 and "medium" in vol_desc:
                hallucinations_detected += 1
                consistency = max(0.3, round(consistency - 0.2, 2))
                warnings.append(f"Inconsistent volatility labeling: Annualized volatility {vol:.1%} is >= 40% but labeled as 'medium'.")
        
        beta = metrics.get("beta")
        beta_desc = str(output_data.get("beta_assessment", "")).lower()
        if beta is not None:
            if 0.8 <= beta <= 1.2 and any(w in beta_desc for w in ("aggressive", "high", "extreme")):
                hallucinations_detected += 1
                consistency = max(0.3, round(consistency - 0.2, 2))
                warnings.append(f"Inconsistent beta labeling: Beta {beta:.2f} is market-neutral (0.8-1.2) but labeled as '{beta_desc}'.")

    if clean_agent == "news":
        articles = output_data.get("articles", [])
        if articles:
            relevant_count = 0
            search_terms = [clean_t] + COMPANY_ALIASES.get(clean_t, [])
            for art in articles:
                text = (art.get("title", "") + " " + art.get("summary", "")).upper()
                if any(term in text for term in search_terms):
                    relevant_count += 1
            if relevant_count == 0 and len(articles) > 0:
                faithfulness = max(0.4, round(faithfulness - 0.4, 2))
                warnings.append(f"Low entity relevance: none of the {len(articles)} fetched news items explicitly mention '{clean_t}' or its company aliases.")

    # Weighted overall quality
    overall = round((faithfulness * 0.40) + (consistency * 0.35) + (completeness * 0.25), 2)

    # Sub-agent grade propagation for Portfolio Manager synthesis
    sub_evals = guardrail_stats.get("sub_evaluations")
    if clean_agent == "portfolio_manager" and sub_evals:
        flagged = []
        worst_sub_grade = "A"
        grade_order = {"A": 4, "B": 3, "C": 2, "FAIL": 1}
        for s_agent, s_eval in sub_evals.items():
            if isinstance(s_eval, dict):
                s_grade = s_eval.get("grade", "A")
                if grade_order.get(s_grade, 4) < grade_order.get(worst_sub_grade, 4):
                    worst_sub_grade = s_grade
                if s_grade != "A" or s_eval.get("hallucinations_detected", 0) > 0:
                    flagged.append(f"{s_agent} ({s_grade})")
        if flagged:
            warnings.append(f"Sub-agent verification alerts: {len(flagged)} agent(s) flagged: {', '.join(flagged)}.")
            if worst_sub_grade in ("FAIL", "C"):
                overall = min(overall, 0.65)
            elif worst_sub_grade == "B":
                overall = min(overall, 0.82)

    if overall >= 0.85 and hallucinations_detected == 0:
        grade = "A"
    elif overall >= 0.70:
        grade = "B"
    elif overall >= 0.50:
        grade = "C"
    else:
        grade = "FAIL"

    # Enforce strict grade cap for portfolio manager if sub-agents were degraded
    if clean_agent == "portfolio_manager" and sub_evals:
        for s_agent, s_eval in sub_evals.items():
            if isinstance(s_eval, dict):
                s_g = s_eval.get("grade", "A")
                if s_g == "B" and grade == "A":
                    grade = "B"
                elif s_g in ("C", "FAIL") and grade in ("A", "B"):
                    grade = s_g

    guardrails_passed = hallucinations_detected == 0 and overall >= 0.70

    evaluation_report = {
        "agent_name": clean_agent,
        "ticker": clean_t,
        "faithfulness_score": faithfulness,
        "consistency_score": consistency,
        "completeness_score": completeness,
        "overall_quality_score": overall,
        "grade": grade,
        "guardrails_passed": guardrails_passed,
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings
    }

    # Prometheus metrics
    try:
        agent_faithfulness_score.labels(agent_name=clean_agent, ticker=clean_t).set(faithfulness)
        agent_evaluation_score.labels(agent_name=clean_agent, ticker=clean_t, grade=grade).set(overall)
        if hallucinations_detected > 0:
            agent_hallucinations_detected_total.labels(agent_name=clean_agent, ticker=clean_t).inc(hallucinations_detected)
    except Exception as pe:
        logger.warning(f"Prometheus evaluation metric error for {clean_agent}: {pe}")

    # PostgreSQL audit log
    try:
        query(
            """INSERT INTO agent_evaluations
               (agent_name, ticker, faithfulness_score, consistency_score, completeness_score,
                overall_quality_score, grade, guardrails_passed, hallucinations_detected, warnings, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                clean_agent,
                clean_t,
                faithfulness,
                consistency,
                completeness,
                overall,
                grade,
                guardrails_passed,
                hallucinations_detected,
                json.dumps(warnings),
                json.dumps({"keys_evaluated": list(output_data.keys())})
            ]
        )
    except Exception as de:
        logger.warning(f"PostgreSQL evaluation insert error for {clean_agent}: {de}")

    logger.info(
        f"[Evaluation | {clean_agent.upper()} | {clean_t}] Grade: {grade} | "
        f"Score: {overall:.2f} | Faithfulness: {faithfulness} | Consistency: {consistency} | "
        f"Hallucinations Caught: {hallucinations_detected}"
    )

    return evaluation_report
