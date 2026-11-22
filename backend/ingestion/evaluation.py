import json
from typing import Dict, Any, List, Optional
from loguru import logger
from ingestion.models import CompanyFootprint, FootprintEvaluation
from agents.metrics import (
    footprint_faithfulness_score,
    footprint_evaluation_score,
    footprint_hallucinations_detected_total
)

TIER_1_DOMAINS = ("sec.gov",)
TIER_2_DOMAINS = (
    "wikipedia.org",
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "apnews.com",
)


def _score_source_credibility(source_url: Optional[str], source_type: Optional[str] = None) -> float:
    """
    Scores source authority across 4 tiers:
      - Tier 1 (1.00): Official SEC regulatory filings (sec.gov)
      - Tier 2 (0.90): Curated encyclopedia & institutional financial wires (Wikipedia, Reuters, Bloomberg, FT, WSJ)
      - Tier 3 (0.75): Verified third-party web search / blog articles
      - Tier 4 (0.25): Repaired fallback or missing citation
    """
    if not source_url or not isinstance(source_url, str):
        return 0.25
    src_t = (source_type or "").lower().strip()
    if src_t == "repaired_fallback":
        return 0.25

    url_lower = source_url.lower().strip()
    if any(d in url_lower for d in TIER_1_DOMAINS):
        return 1.00
    if any(d in url_lower for d in TIER_2_DOMAINS):
        return 0.90
    if url_lower.startswith("http"):
        return 0.75
    return 0.25


def evaluate_footprint_output(
    footprint: CompanyFootprint,
    guardrail_stats: Dict[str, Any]
) -> FootprintEvaluation:
    """
    Computes rigorous semantic evaluation metrics on the agent's output:
    1. Faithfulness Score (Grounding): Ratio of claims backed by evidence quotes matching source texts (Link A + B + C).
    2. Citation Grounding Score: Tiered source credibility (SEC 1.0, Wiki/Wires 0.90, Web Search 0.75, Fallback 0.25).
    3. Completeness Score: Breadth of operational coverage across hubs and tier-1 suppliers.
    4. Hallucination Detection Count: Any hallucinated domains, ungrounded quotes, or invalid entities caught.
    """
    ticker = footprint.ticker.upper().strip()
    
    # 1. Faithfulness Score (from guardrail Link A/B/C quote overlap)
    avg_grounding = guardrail_stats.get("avg_grounding_score", 1.0)
    faithfulness = round(max(0.0, min(1.0, float(avg_grounding))), 2)

    # 2. Tiered Citation Grounding Score
    credibility_scores: List[float] = []
    for h in footprint.hubs:
        credibility_scores.append(_score_source_credibility(h.source_url, h.source_type))
    for s in footprint.key_suppliers:
        s_url = getattr(s, "source_url", None) if hasattr(s, "source_url") else (s.get("source_url") if isinstance(s, dict) else None)
        s_type = getattr(s, "source_type", None) if hasattr(s, "source_type") else (s.get("source_type") if isinstance(s, dict) else None)
        credibility_scores.append(_score_source_credibility(s_url, s_type))

    citation_score = round(sum(credibility_scores) / len(credibility_scores), 2) if credibility_scores else 0.0

    # 3. Completeness Score (target: at least 2 hubs and 2 suppliers)
    hub_ratio = min(1.0, len(footprint.hubs) / 2.0)
    supplier_ratio = min(1.0, len(footprint.key_suppliers) / 2.0)
    completeness = round((hub_ratio * 0.5) + (supplier_ratio * 0.5), 2)

    # 4. Overall Weighted Score
    # Weights: Faithfulness 40%, Citation Grounding 35%, Completeness 25%
    overall = round(
        (faithfulness * 0.40) + (citation_score * 0.35) + (completeness * 0.25),
        2
    )

    # Grade Assignment
    if overall >= 0.85:
        grade = "A"
    elif overall >= 0.70:
        grade = "B"
    elif overall >= 0.50:
        grade = "C"
    else:
        grade = "FAIL"

    hallucinations_detected = guardrail_stats.get("hallucinations_detected", 0)
    warnings = guardrail_stats.get("warnings", [])
    guardrails_passed = hallucinations_detected == 0 or len(footprint.hubs) >= 1

    evaluation = FootprintEvaluation(
        faithfulness_score=faithfulness,
        citation_grounding_score=citation_score,
        completeness_score=completeness,
        overall_quality_score=overall,
        grade=grade,
        guardrails_passed=guardrails_passed,
        hallucinations_detected=hallucinations_detected,
        warnings=warnings,
        details={
            "hubs_analyzed": len(footprint.hubs),
            "suppliers_analyzed": len(footprint.key_suppliers),
            "grounding_check": f"{faithfulness*100:.0f}%",
            "citation_check": f"{citation_score*100:.0f}%",
            "coverage_check": f"{completeness*100:.0f}%"
        }
    )

    # 5. Update Prometheus Metrics
    try:
        footprint_faithfulness_score.labels(ticker=ticker).set(faithfulness)
        footprint_evaluation_score.labels(ticker=ticker, grade=grade).set(overall)
        if hallucinations_detected > 0:
            footprint_hallucinations_detected_total.labels(ticker=ticker).inc(hallucinations_detected)
    except Exception as pe:
        logger.warning(f"Failed to record evaluation metrics to Prometheus: {pe}")

    # 6. Record Audit into PostgreSQL
    try:
        from agents.db import query
        query(
            """INSERT INTO footprint_evaluations
               (ticker, faithfulness_score, citation_grounding_score, completeness_score, 
                overall_quality_score, grade, guardrails_passed, hallucinations_detected, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                ticker,
                faithfulness,
                citation_score,
                completeness,
                overall,
                grade,
                guardrails_passed,
                hallucinations_detected,
                json.dumps(evaluation.details)
            ]
        )
    except Exception as de:
        logger.warning(f"Failed to record footprint evaluation into DB: {de}")

    # 7. Push Output Guardrail & Evaluation Scores to Langfuse & Local Trace Log
    try:
        from agents.observability import record_guardrail_and_eval
        record_guardrail_and_eval(
            ticker=ticker,
            agent_name="footprint_agent",
            guardrail_stats=guardrail_stats,
            evaluation_obj=evaluation,
            raw_counts={
                "hubs": guardrail_stats.get("initial_hubs_count", len(footprint.hubs)),
                "suppliers": guardrail_stats.get("initial_suppliers_count", len(footprint.key_suppliers)),
            },
            sanitized_counts={
                "hubs": len(footprint.hubs),
                "suppliers": len(footprint.key_suppliers),
            },
        )
    except Exception as lfe:
        logger.debug(f"Langfuse evaluation score recording skipped: {lfe}")

    logger.info(
        f"[Evaluation | {ticker}] Grade: {grade} | Overall: {overall:.2f} | "
        f"Faithfulness: {faithfulness} | Citations: {citation_score} | Coverage: {completeness} | "
        f"Hallucinations: {hallucinations_detected}"
    )

    return evaluation
