"""
MarketPulse — Footprint Agent & Guardrail Benchmark Runner (BENCH-004)
======================================================================
Evaluates the production Corporate Footprint Agent (`footprint_agent.py`),
3-Link Anti-Hallucination Guardrail Pipeline (`ingestion/guardrails.py`),
and Tiered Citation Evaluator (`ingestion/evaluation.py`) against the
industry-standard benchmark matrix defined in `AGENT_BENCHMARKS_AND_EVAL_PLAN.md`:
  - FinanceBench (SEC 10-K Item 2 Property & Supply-Chain Grounding)
  - DocRED / Re-DocRED (Entity-Relation Extraction Precision / Recall / F1)
  - ALCE (Citation Precision & Whitelist Verification)
  - HaluBench (Clause-Scoped Negation, Divestiture & Stitched-Quote Traps)
  - Temporal Regime Classifier (ACTIVE_SHOCK vs RECOVERY_LAG vs HISTORICAL_STRUCTURAL)

Usage:
  .\\backend\\venv\\Scripts\\python.exe backend\\scripts\\run_benchmark_suite.py
  .\\backend\\venv\\Scripts\\python.exe backend\\scripts\\run_benchmark_suite.py --live-e2e NVDA
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# Ensure `backend/` is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from ingestion.guardrails import apply_footprint_guardrails
from ingestion.models import PhysicalHub, SupplierEvidence
from ingestion.evaluation import evaluate_footprint_output
from ingestion.adapters.geo_feed_adapter import classify_article_temporal_regime
from agents.observability import get_langfuse, trace_agent_run, record_guardrail_and_eval

GOLDEN_BENCHMARK_PATH = BACKEND_DIR / "logs" / "golden_footprint_benchmark.json"
BENCHMARK_REPORT_PATH = BACKEND_DIR / "logs" / "footprint_benchmark_report.json"

# Ground-Truth End-to-End Entity Sets for Live Agent Extraction Eval (DocRED / FinanceBench E2E)
E2E_GROUND_TRUTH = {
    "NVDA": {
        "company_name": "NVIDIA Corporation",
        "expected_hub_tokens": ["santa clara", "california", "taiwan", "hsinchu", "taipei", "israel", "tel aviv", "austin", "china", "shanghai", "shenzhen", "hong kong", "india", "bengaluru", "pune", "hyderabad"],
        "expected_supplier_tokens": ["tsmc", "taiwan semiconductor", "samsung", "sk hynix", "micron", "foxconn", "hon hai", "amkor", "ase", "byd", "wistron", "quanta", "fabrinet", "king yuan", "kyec", "siliconware", "spil"],
        "forbidden_negated_tokens": ["shinjuan"]
    },
    "AAPL": {
        "company_name": "Apple Inc.",
        "expected_hub_tokens": ["cupertino", "california", "austin", "texas", "cork", "ireland", "singapore"],
        "expected_supplier_tokens": ["foxconn", "hon hai", "tsmc", "taiwan semiconductor", "pegatron", "luxshare", "wistron", "samsung", "corning", "broadcom", "qualcomm", "sony"],
        "forbidden_negated_tokens": ["ofilm"]
    },
    "TSLA": {
        "company_name": "Tesla, Inc.",
        "expected_hub_tokens": ["austin", "texas", "fremont", "california", "shanghai", "berlin", "brandenburg", "nevada", "sparks", "lathrop", "buffalo"],
        "expected_supplier_tokens": ["panasonic", "catl", "contemporary amperex", "lg energy", "byd", "albemarle", "ganfeng", "livent", "glencore", "tsmc"],
        "forbidden_negated_tokens": []
    }
}


def run_temporal_regime_unit_checks() -> Dict[str, Any]:
    """
    Verifies the deterministic Temporal Regime Classifier in `geo_feed_adapter.py`
    across 3 time horizons:
      - ACTIVE_SHOCK (<= 30 days)
      - RECOVERY_LAG (31 - 180 days)
      - HISTORICAL_STRUCTURAL (> 180 days / 3 years old)
    """
    ref_now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
    test_articles = [
        {
            "name": "Breaking 4-day-old supplier factory fire",
            "pub_date": "Sat, 21 Nov 2026 08:00:00 GMT",
            "expected_regime": "ACTIVE_SHOCK",
            "expected_eligible": True
        },
        {
            "name": "75-day-old wafer cleanroom rebuild (margin/inventory lag phase)",
            "pub_date": "Fri, 11 Sep 2026 08:00:00 GMT",
            "expected_regime": "RECOVERY_LAG",
            "expected_eligible": True
        },
        {
            "name": "3-year-old supplier factory fire / walkout (Nov 2023)",
            "pub_date": "Wed, 15 Nov 2023 08:00:00 GMT",
            "expected_regime": "HISTORICAL_STRUCTURAL",
            "expected_eligible": False
        }
    ]

    passed = 0
    results = []
    for item in test_articles:
        res = classify_article_temporal_regime(item["pub_date"], reference_now=ref_now)
        ok = (
            res["temporal_regime"] == item["expected_regime"]
            and res["is_live_contradiction_eligible"] == item["expected_eligible"]
        )
        if ok:
            passed += 1
        results.append({
            "test": item["name"],
            "pub_date": item["pub_date"],
            "age_days": res["age_days"],
            "actual_regime": res["temporal_regime"],
            "expected_regime": item["expected_regime"],
            "is_live_contradiction_eligible": res["is_live_contradiction_eligible"],
            "passed": ok
        })

    return {
        "total": len(test_articles),
        "passed": passed,
        "accuracy": round(passed / len(test_articles), 4),
        "cases": results
    }


def run_golden_20_suite(upload_langfuse: bool = True) -> Dict[str, Any]:
    """
    Executes the 20-case FinanceBench + DocRED + ALCE + HaluBench Golden Suite
    against `apply_footprint_guardrails()` and computes binary classification
    Precision, Recall, F1, Accuracy, and False-Positive Rate (FPR).
    """
    with open(GOLDEN_BENCHMARK_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    cases = dataset["cases"]
    tp = fp = tn = fn = 0
    category_stats: Dict[str, Dict[str, int]] = {}
    case_results: List[Dict[str, Any]] = []

    start_t = time.perf_counter()

    for c in cases:
        cid = c["case_id"]
        cat = c["category"]
        ticker = c["ticker"]
        company_name = c["company_name"]
        entity_type = c["entity_type"]
        candidate = dict(c["candidate"])
        context_corpus = c["context_corpus"]
        retrieved_urls = c.get("retrieved_urls", [])
        expected_grounded = bool(c["expected_is_grounded"])

        if entity_type == "hub":
            hub_dict = {
                "language_code": "en",
                "local_keywords": "plant OR facility OR production",
                **candidate
            }
            raw_hubs = [PhysicalHub(**hub_dict)]
            raw_suppliers = []
        else:
            raw_hubs = []
            raw_suppliers = [SupplierEvidence(**candidate)]

        sanitized_hubs, sanitized_suppliers, stats = apply_footprint_guardrails(
            raw_hubs=raw_hubs,
            raw_suppliers=raw_suppliers,
            context_corpus=context_corpus,
            ticker=ticker,
            company_name=company_name,
            source_corpora={
                "sec_10k": context_corpus if candidate.get("source_type") == "sec_10k" else "",
                "wikipedia": context_corpus if candidate.get("source_type") == "wikipedia" else "",
                "web_search": context_corpus if candidate.get("source_type") == "web_search" else "",
            },
            retrieved_urls=set(retrieved_urls)
        )

        # Extract the candidate's grounding outcome
        surviving_items = sanitized_hubs if entity_type == "hub" else sanitized_suppliers
        item_score = float(stats.get("avg_grounding_score", 0.0))
        hallucinations = int(stats.get("hallucinations_detected", 0))
        url_unverified = (
            surviving_items and getattr(surviving_items[0], "source_type", None) == "repaired_fallback"
        )

        # An item is accepted as grounded by the guardrail pipeline iff:
        # 1. It survived into sanitized output,
        # 2. Its grounding score >= 0.70,
        # 3. Zero hallucinations (including Link A, Negation Polarity, Co-Mention, and URL Whitelist) were flagged.
        actual_grounded = (
            len(surviving_items) == 1
            and item_score >= 0.70
            and hallucinations == 0
            and not url_unverified
        )

        if expected_grounded and actual_grounded:
            tp += 1
            outcome = "TP"
        elif not expected_grounded and not actual_grounded:
            tn += 1
            outcome = "TN"
        elif not expected_grounded and actual_grounded:
            fp += 1
            outcome = "FP"
        else:
            fn += 1
            outcome = "FN"

        cat_bucket = category_stats.setdefault(cat, {"total": 0, "correct": 0})
        cat_bucket["total"] += 1
        if outcome in ("TP", "TN"):
            cat_bucket["correct"] += 1

        case_results.append({
            "case_id": cid,
            "category": cat,
            "ticker": ticker,
            "entity_type": entity_type,
            "expected_grounded": expected_grounded,
            "actual_grounded": actual_grounded,
            "outcome": outcome,
            "grounding_score": round(item_score, 3),
            "hallucinations_detected": hallucinations,
            "warnings": stats.get("warnings", [])
        })

    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round((2 * precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    accuracy = round((tp + tn) / len(cases), 4) if cases else 0.0
    fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0

    sota_target_f1 = dataset["thresholds"]["institutional_sota_f1"]
    baseline_f1 = dataset["thresholds"]["industry_baseline_f1"]
    meets_sota = f1 >= sota_target_f1 and fpr == 0.0

    summary = {
        "benchmark_name": dataset["benchmark_name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "elapsed_ms": elapsed_ms,
        "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "accuracy": accuracy,
            "false_positive_rate": fpr
        },
        "benchmarks_comparison": {
            "industry_baseline_f1": baseline_f1,
            "institutional_sota_f1": sota_target_f1,
            "meets_institutional_sota": meets_sota
        },
        "category_breakdown": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"], 4)
            }
            for k, v in category_stats.items()
        },
        "case_results": case_results
    }

    if upload_langfuse:
        _sync_benchmark_to_langfuse(dataset, summary)

    return summary


def _sync_benchmark_to_langfuse(dataset: Dict[str, Any], summary: Dict[str, Any]) -> None:
    """
    Seeds/updates the Langfuse Dataset `marketpulse-footprint-bench-v1` and
    records a traced benchmark evaluation observation with Precision, Recall, F1, and FPR.
    """
    lf = get_langfuse()
    if not lf:
        return

    dataset_name = dataset["benchmark_name"]
    try:
        try:
            lf.create_dataset(
                name=dataset_name,
                description="FinanceBench + DocRED + ALCE + HaluBench 20-Case Golden Benchmark for MarketPulse Footprint Agent",
                metadata=dataset.get("thresholds", {})
            )
        except Exception:
            pass

        with trace_agent_run(
            ticker="BENCH",
            trace_name="footprint_benchmark_suite",
            input_payload={
                "benchmark_name": dataset_name,
                "total_cases": summary["total_cases"],
                "standards": dataset["standards"]
            },
            metadata={"suite_version": "v1", "benchmarks": "FinanceBench+DocRED+ALCE+HaluBench"}
        ) as root_obs:
            if root_obs and hasattr(root_obs, "update"):
                root_obs.update(
                    output={
                        "metrics": summary["metrics"],
                        "confusion_matrix": summary["confusion_matrix"],
                        "category_breakdown": summary["category_breakdown"],
                        "meets_institutional_sota": summary["benchmarks_comparison"]["meets_institutional_sota"]
                    }
                )
            for metric_name, val in summary["metrics"].items():
                try:
                    if hasattr(lf, "score_current_trace"):
                        lf.score_current_trace(
                            name=f"footprint_bench_{metric_name}",
                            value=float(val),
                            comment=f"{dataset_name} ({summary['total_cases']} cases)"
                        )
                except Exception:
                    pass
        lf.flush()
    except Exception as e:
        print(f"[Langfuse Benchmark Sync Notice] {e}")


async def run_live_e2e_ticker_eval(ticker: str) -> Dict[str, Any]:
    """
    Runs an end-to-end live MCP + LLM extraction via `research_company_footprint(ticker, force_refresh=True)`
    and computes real DocRED Entity Recall, ALCE Citation Precision, and Negation Trap Resistance.
    """
    from ingestion.footprint_agent import research_company_footprint

    t_up = ticker.upper().strip()
    gt = E2E_GROUND_TRUTH.get(t_up)
    footprint = await research_company_footprint(t_up, force_live=True)

    extracted_hubs = [f"{h.hub_name} ({h.region_name}, {h.country_code})" for h in footprint.hubs]
    extracted_suppliers = [
        s.name if hasattr(s, "name") else (s.get("name") if isinstance(s, dict) else str(s))
        for s in footprint.key_suppliers
    ]

    result: Dict[str, Any] = {
        "ticker": t_up,
        "archetype": footprint.archetype,
        "extracted_hubs": extracted_hubs,
        "extracted_suppliers": extracted_suppliers,
        "evaluation": footprint.evaluation.model_dump() if footprint.evaluation else {}
    }

    if gt:
        hub_blob = " ".join(extracted_hubs).lower()
        sup_blob = " ".join(extracted_suppliers).lower()

        matched_hubs = [
            h for h in extracted_hubs
            if any(tok in h.lower() for tok in gt["expected_hub_tokens"])
        ]
        matched_suppliers = [
            s for s in extracted_suppliers
            if any(tok in s.lower() for tok in gt["expected_supplier_tokens"])
        ]
        forbidden_hits = [
            tok for tok in gt["forbidden_negated_tokens"]
            if tok in hub_blob or tok in sup_blob
        ]

        hub_precision = round(len(matched_hubs) / len(extracted_hubs), 4) if extracted_hubs else 0.0
        supplier_precision = round(len(matched_suppliers) / len(extracted_suppliers), 4) if extracted_suppliers else 0.0

        result["ground_truth_alignment"] = {
            "matched_hubs": matched_hubs,
            "matched_suppliers": matched_suppliers,
            "hub_ground_truth_precision": hub_precision,
            "supplier_ground_truth_precision": supplier_precision,
            "forbidden_negated_leaks": forbidden_hits,
            "passed_zero_negated_leaks": len(forbidden_hits) == 0
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="Run MarketPulse Footprint Agent Benchmark Suite")
    parser.add_argument("--live-e2e", type=str, default=None, help="Optional ticker (e.g. NVDA, AAPL, TSLA) for live E2E MCP extraction benchmark")
    parser.add_argument("--no-langfuse", action="store_true", help="Skip Langfuse trace upload")
    args = parser.parse_args()

    print("=" * 78)
    print(" MARKETPULSE — FOOTPRINT AGENT & TEMPORAL REGIME BENCHMARK SUITE (BENCH-004)")
    print("=" * 78)

    # 1. Temporal Regime Classifier Checks
    temporal_report = run_temporal_regime_unit_checks()
    print(f"\n[1/2] Temporal Supply-Chain Regime Classifier: {temporal_report['passed']}/{temporal_report['total']} PASSED (Accuracy: {temporal_report['accuracy']*100:.1f}%)")
    for tc in temporal_report["cases"]:
        status = "PASS" if tc["passed"] else "FAIL"
        print(f"  - [{status}] {tc['test']} -> age={tc['age_days']}d | regime={tc['actual_regime']} | live_eligible={tc['is_live_contradiction_eligible']}")

    # 2. 20-Case FinanceBench + DocRED + ALCE + HaluBench Golden Suite
    golden_report = run_golden_20_suite(upload_langfuse=not args.no_langfuse)
    m = golden_report["metrics"]
    cm = golden_report["confusion_matrix"]
    print(f"\n[2/2] Footprint Guardrail Golden Suite ({golden_report['total_cases']} cases in {golden_report['elapsed_ms']} ms):")
    print(f"  - Confusion Matrix : TP={cm['TP']} | TN={cm['TN']} | FP={cm['FP']} | FN={cm['FN']}")
    print(f"  - Precision        : {m['precision']:.4f}")
    print(f"  - Recall           : {m['recall']:.4f}")
    print(f"  - F1 Score         : {m['f1_score']:.4f}  (Industry Baseline: 0.7500 | Institutional SOTA Target: >= 0.9500)")
    print(f"  - False Pos. Rate  : {m['false_positive_rate']:.4f}  (Target: 0.0000)")
    print("\n  Category Breakdown:")
    for cat, cstats in golden_report["category_breakdown"].items():
        print(f"    * {cat:<28}: {cstats['correct']}/{cstats['total']} ({cstats['accuracy']*100:.1f}%)")

    full_report: Dict[str, Any] = {
        "temporal_regime_benchmark": temporal_report,
        "footprint_golden_suite": golden_report
    }

    if args.live_e2e:
        print(f"\n[Live E2E Extraction Benchmark] Running autonomous MCP loop for {args.live_e2e.upper()}...")
        e2e_res = asyncio.run(run_live_e2e_ticker_eval(args.live_e2e))
        full_report["live_e2e_benchmark"] = e2e_res
        eval_info = e2e_res.get("evaluation", {})
        print(f"  - Extracted Hubs      : {e2e_res['extracted_hubs']}")
        print(f"  - Extracted Suppliers : {e2e_res['extracted_suppliers']}")
        print(
            f"  - Evaluation          : Grade={eval_info.get('grade')} | "
            f"Overall={eval_info.get('overall_quality_score')} | "
            f"Faithfulness={eval_info.get('faithfulness_score')} | "
            f"Citations={eval_info.get('citation_grounding_score')}"
        )
        if "ground_truth_alignment" in e2e_res:
            gta = e2e_res["ground_truth_alignment"]
            print(
                f"  - Ground-Truth Match  : Hub Precision={gta['hub_ground_truth_precision']:.2f} | "
                f"Supplier Precision={gta['supplier_ground_truth_precision']:.2f} | "
                f"Zero Negated Leaks={gta['passed_zero_negated_leaks']}"
            )

    BENCHMARK_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BENCHMARK_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)
    print(f"\nSaved full benchmark report to: {BENCHMARK_REPORT_PATH}")
    print("=" * 78)


if __name__ == "__main__":
    main()
