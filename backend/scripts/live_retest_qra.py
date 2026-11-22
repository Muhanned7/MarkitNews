"""
Live Tester & Quantitative Research Analyst Retest Suite (QRA-001 through QRA-013)
Hits live FastAPI backend (http://127.0.0.1:8000) and Next.js frontend (http://127.0.0.1:3000)
with rigorous mathematical, statistical, edge-case, and UI rendering checks.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:3000"


def http_req(url: str, method: str = "GET", payload: dict = None, expect_json: bool = True):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if expect_json else raw), dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return e.code, parsed, dict(e.headers)


def run_live_retest():
    results = {}
    print("=" * 82)
    print("LIVE TESTER AUDIT - QUANTITATIVE RESEARCH ANALYST (QRA-001 TO QRA-013)")
    print("=" * 82)

    # 1. QRA-001 & QRA-002: Signals Catalog, Survivorship-Bias Audit & Point-in-Time Panel
    st, sig_cat, _ = http_req(f"{FRONTEND_URL}/api/research/signals")
    assert st == 200, f"/api/research/signals failed: {st}"
    assert sig_cat["count"] == 12
    assert len(sig_cat["sectors"]) == 11

    # Survivorship bias trajectory across 4 historical dates via /api/research/universe?date=...
    surv_counts = {}
    for dt_str, expected_active in [
        ("2021-06-15", 100),
        ("2022-09-01", 99),
        ("2023-04-01", 96),
        ("2026-10-14", 95),
    ]:
        st_u, u_data, _ = http_req(f"{FRONTEND_URL}/api/research/universe?date={dt_str}")
        assert st_u == 200
        assert u_data["active_count"] == expected_active, (
            f"Date {dt_str}: got {u_data['active_count']} != {expected_active}"
        )
        surv_counts[dt_str] = u_data["active_count"]

    # Point-in-Time Panel JSON & CSV Export + Edge case (unknown universe -> 400)
    st_p, panel, _ = http_req(
        f"{FRONTEND_URL}/api/research/panel?universe=mock100&as_of=2023-06-15&limit=500"
    )
    assert st_p == 200 and panel["pit_verified"] is True and panel["pit_violations"] == 0
    for r in panel["rows"]:
        if r["report_date"] is not None:
            assert r["report_date"] <= r["date"], "Point-in-time violation in panel!"

    st_csv, csv_body, _ = http_req(
        f"{FRONTEND_URL}/api/research/panel.csv?as_of=2026-10-14&limit=100",
        expect_json=False,
    )
    assert st_csv == 200 and "date,ticker,field,value,period_end,report_date" in csv_body.splitlines()[0]

    st_bad_u, _, _ = http_req(f"{FRONTEND_URL}/api/research/panel?universe=invalid_universe")
    assert st_bad_u == 400, f"Expected 400 on invalid universe, got {st_bad_u}"

    results["QRA-001_002"] = {
        "survivorship_counts": surv_counts,
        "csv_lines": len(csv_body.strip().splitlines()),
        "invalid_universe_http": st_bad_u,
    }
    print(
        f"[PASS] QRA-001 & QRA-002 | Survivorship trajectory: {surv_counts} | "
        f"CSV rows: {len(csv_body.strip().splitlines())} | Bad universe: HTTP {st_bad_u}"
    )

    # 2. QRA-003: Factor Standardization & Neutralization Pipeline + Edge case (unknown signal -> 404)
    st_s, sig_res, _ = http_req(
        f"{FRONTEND_URL}/api/research/signals/value_composite?winsorize=true&sector_neutral=true&beta_neutral=true&zscore=true"
    )
    assert st_s == 200
    diag = sig_res["diagnostics"]
    assert abs(diag["mean_cross_sectional_mean"]) < 1e-4
    assert abs(diag["mean_cross_sectional_sd"] - 1.0) < 1e-3
    assert diag["max_abs_sector_dummy_corr"] < 1e-4
    assert abs(diag["mean_beta_corr"]) < 1e-4

    st_bad_sig, _, _ = http_req(f"{FRONTEND_URL}/api/research/signals/non_existent_factor_999")
    assert st_bad_sig == 404, f"Expected 404 for unknown signal, got {st_bad_sig}"
    results["QRA-003"] = {
        "cs_mean": diag["mean_cross_sectional_mean"],
        "cs_std": diag["mean_cross_sectional_sd"],
        "max_sector_corr": diag["max_abs_sector_dummy_corr"],
        "beta_corr": diag["mean_beta_corr"],
        "unknown_signal_http": st_bad_sig,
    }
    print(
        f"[PASS] QRA-003 | CS Mean={diag['mean_cross_sectional_mean']:.6f}, "
        f"SD={diag['mean_cross_sectional_sd']:.6f}, MaxSectorCorr={diag['max_abs_sector_dummy_corr']:.6f}, "
        f"UnknownSignal=HTTP {st_bad_sig}"
    )

    # 3. QRA-004: Signal IC Tear Sheet across Strong, Weak, and Noise signals
    st_ic_strong, ic_strong, _ = http_req(
        f"{FRONTEND_URL}/api/research/tear-sheet?signal=planted_alpha_strong&horizon=21"
    )
    st_ic_weak, ic_weak, _ = http_req(
        f"{FRONTEND_URL}/api/research/tear-sheet?signal=planted_alpha_weak&horizon=21"
    )
    st_ic_noise, ic_noise, _ = http_req(
        f"{FRONTEND_URL}/api/research/tear-sheet?signal=planted_noise&horizon=21"
    )
    assert st_ic_strong == 200 and st_ic_weak == 200 and st_ic_noise == 200
    assert abs(ic_strong["summary"]["mean_ic"] - 0.05) <= 0.01
    assert ic_strong["summary"]["quintile_monotonic"] is True
    assert abs(ic_weak["summary"]["mean_ic"] - 0.02) <= 0.01
    assert abs(ic_noise["summary"]["mean_ic"]) <= 0.01 and abs(ic_noise["summary"]["q5_q1_t_stat"]) < 2.0
    assert len(ic_strong["sector_ic_boxplot"]) == 11
    results["QRA-004"] = {
        "strong_ic": ic_strong["summary"]["mean_ic"],
        "strong_t": ic_strong["summary"]["newey_west_t_stat"],
        "weak_ic": ic_weak["summary"]["mean_ic"],
        "noise_ic": ic_noise["summary"]["mean_ic"],
        "noise_q5_q1_t": ic_noise["summary"]["q5_q1_t_stat"],
    }
    print(
        f"[PASS] QRA-004 | Strong IC={ic_strong['summary']['mean_ic']:.4f} (t={ic_strong['summary']['newey_west_t_stat']:.2f}), "
        f"Weak IC={ic_weak['summary']['mean_ic']:.4f}, Noise IC={ic_noise['summary']['mean_ic']:.4f}"
    )

    # 4. QRA-005 & QRA-006: Backtester, Cost Drag, Lag=0 Lookahead Warning, and PostgreSQL Persistence
    st_bt1, bt1, _ = http_req(
        f"{FRONTEND_URL}/api/research/backtest",
        method="POST",
        payload={
            "signal_name": "planted_alpha_strong",
            "rebalance_freq": "monthly",
            "weighting": "equal_top_n",
            "mode": "long_short",
            "fixed_cost_bps": 10.0,
            "impact_coeff": 0.12,
            "max_weight": 0.05,
            "sector_cap": 0.25,
            "lag": 1,
            "save_run": True,
            "question_key": "live_tester_audit",
            "tags": ["tester", "live_audit", "strong_alpha"],
            "notes": "Live Tester HTTP retest run #1",
        },
    )
    st_bt2, bt2, _ = http_req(
        f"{FRONTEND_URL}/api/research/backtest",
        method="POST",
        payload={
            "signal_name": "quality_composite",
            "rebalance_freq": "weekly",
            "weighting": "ic_weighted",
            "mode": "long_only",
            "fixed_cost_bps": 20.0,
            "impact_coeff": 0.15,
            "max_weight": 0.05,
            "sector_cap": 0.25,
            "lag": 1,
            "save_run": True,
            "question_key": "live_tester_audit",
            "tags": ["tester", "live_audit", "quality"],
            "notes": "Live Tester HTTP retest run #2",
        },
    )
    # Edge Case: planted_lookahead with lag=0 vs lag=1
    st_bt_lag0, bt_lag0, _ = http_req(
        f"{FRONTEND_URL}/api/research/backtest",
        method="POST",
        payload={
            "signal_name": "planted_lookahead",
            "rebalance_freq": "daily",
            "fixed_cost_bps": 5.0,
            "lag": 0,
            "save_run": False,
        },
    )
    st_bt_lag1, bt_lag1, _ = http_req(
        f"{FRONTEND_URL}/api/research/backtest",
        method="POST",
        payload={
            "signal_name": "planted_lookahead",
            "rebalance_freq": "daily",
            "fixed_cost_bps": 5.0,
            "lag": 1,
            "save_run": False,
        },
    )
    assert st_bt1 == 200 and st_bt2 == 200 and st_bt_lag0 == 200 and st_bt_lag1 == 200
    assert bt1["gross_metrics"]["sharpe"] > bt1["net_metrics"]["sharpe"] > 0.8, (
        f"Expected gross > net > 0.8, got gross={bt1['gross_metrics']['sharpe']}, net={bt1['net_metrics']['sharpe']}"
    )
    assert bt_lag0["net_metrics"]["sharpe"] > 5.0
    assert abs(bt_lag1["gross_metrics"]["sharpe"]) < 1.0 and bt_lag1["net_metrics"]["sharpe"] < 1.0

    # Verify runs list, compare endpoint, PATCH metadata, and 404 edge case
    st_runs, runs_list, _ = http_req(f"{FRONTEND_URL}/api/research/runs")
    assert st_runs == 200 and runs_list["total_runs"] >= 2
    r1_id, r2_id = bt1["saved_run"]["id"], bt2["saved_run"]["id"]
    st_cmp, cmp_data, _ = http_req(f"{FRONTEND_URL}/api/research/runs/compare?ids={r1_id},{r2_id}")
    assert st_cmp == 200 and len(cmp_data["runs"]) == 2

    st_patch, patch_res, _ = http_req(
        f"{FRONTEND_URL}/api/research/runs/{r1_id}",
        method="PATCH",
        payload={"tags": ["tester", "verified_passed"], "notes": "Updated by Tester via PATCH"},
    )
    assert st_patch == 200 and "verified_passed" in patch_res["tags"]

    st_404_run, _, _ = http_req(
        f"{FRONTEND_URL}/api/research/runs/99999999",
        method="PATCH",
        payload={"notes": "Should 404"},
    )
    assert st_404_run == 404
    results["QRA-005_006"] = {
        "bt1_gross_sharpe": bt1["gross_metrics"]["sharpe"],
        "bt1_net_sharpe": bt1["net_metrics"]["sharpe"],
        "lookahead_lag0_sharpe": bt_lag0["net_metrics"]["sharpe"],
        "lookahead_lag1_gross_sharpe": bt_lag1["gross_metrics"]["sharpe"],
        "compared_runs": len(cmp_data["runs"]),
        "missing_run_patch_http": st_404_run,
    }
    print(
        f"[PASS] QRA-005 & QRA-006 | Gross SR={bt1['gross_metrics']['sharpe']:.2f} -> "
        f"Net SR={bt1['net_metrics']['sharpe']:.2f}, Lookahead Lag0 SR={bt_lag0['net_metrics']['sharpe']:.2f} vs "
        f"Lag1 Gross SR={bt_lag1['gross_metrics']['sharpe']:.2f}, Compare={len(cmp_data['runs'])}"
    )

    # 5. QRA-008: Lookahead Bias & Data Leakage Scanner
    st_lk_bad, lk_bad, _ = http_req(f"{FRONTEND_URL}/api/research/leakage-scan?signal=planted_lookahead&lag=1")
    st_lk_pit, lk_pit, _ = http_req(
        f"{FRONTEND_URL}/api/research/leakage-scan?signal=value_composite&lag=1&simulate_bad_report_date=true"
    )
    st_lk_ok, lk_ok, _ = http_req(f"{FRONTEND_URL}/api/research/leakage-scan?signal=planted_alpha_strong&lag=1")
    assert st_lk_bad == 200 and st_lk_pit == 200 and st_lk_ok == 200
    assert lk_bad["passed"] is False and lk_bad["badge"] == "LEAKAGE_WARNING"
    assert lk_pit["passed"] is False and lk_pit["pit_breach"] is True
    assert lk_ok["passed"] is True and lk_ok["badge"] == "POINT_IN_TIME_VERIFIED"
    results["QRA-008"] = {
        "planted_lookahead_badge": lk_bad["badge"],
        "unlagged_corr": lk_bad["unlagged_corr_s_t_r_t1"],
        "simulated_pit_breach_detected": lk_pit["pit_breach"],
        "clean_signal_badge": lk_ok["badge"],
    }
    print(
        f"[PASS] QRA-008 | planted_lookahead={lk_bad['badge']} (corr={lk_bad['unlagged_corr_s_t_r_t1']:.4f}), "
        f"simulated_pit_breach={lk_pit['pit_breach']}, clean={lk_ok['badge']}"
    )

    # 6. QRA-009: Multi-Factor Attribution & Orthogonalization
    st_fa, fa, _ = http_req(
        f"{FRONTEND_URL}/api/research/factors?signal=planted_alpha_strong&orthogonalize=SMB,HML,MOM"
    )
    assert st_fa == 200
    assert fa["alpha"]["significant"] is True and fa["alpha"]["t_stat"] > 3.0
    assert len(fa["orthogonalized_against"]) == 3
    results["QRA-009"] = {
        "annualized_alpha_pct": fa["alpha"]["alpha_annual_pct"],
        "alpha_t_stat": fa["alpha"]["t_stat"],
        "orthogonalized_against": fa["orthogonalized_against"],
    }
    print(
        f"[PASS] QRA-009 | Annualized Alpha=+{fa['alpha']['alpha_annual_pct']:.2f}% "
        f"(t={fa['alpha']['t_stat']:.2f}), OrthoAgainst={fa['orthogonalized_against']}"
    )

    # 7. QRA-010: AI Agent & LLM Signal Evaluation Lab + Universe Hygiene Edge Case
    st_ag, ag, _ = http_req(f"{FRONTEND_URL}/api/research/agent-lab?universe=mock100")
    assert st_ag == 200
    assert len(ag["per_agent_ic"]) == 6
    assert ag["synthesizer_summary"]["brier_score_63d"] < 0.25
    assert ag["synthesizer_summary"]["conviction_monotonic"] is True
    assert ag["hygiene_audit"]["contaminated_rows_joined"] == 0

    st_ag_bad, _, _ = http_req(f"{FRONTEND_URL}/api/research/agent-lab?universe=real_sp500_contaminated")
    assert st_ag_bad == 400, f"Expected 400 for non-mock100 universe in agent-lab, got {st_ag_bad}"
    results["QRA-010"] = {
        "agents_count": len(ag["per_agent_ic"]),
        "brier_score_63d": ag["synthesizer_summary"]["brier_score_63d"],
        "contaminated_rows": ag["hygiene_audit"]["contaminated_rows_joined"],
        "cross_universe_block_http": st_ag_bad,
    }
    print(
        f"[PASS] QRA-010 | 6 Agents evaluated, Brier={ag['synthesizer_summary']['brier_score_63d']:.4f}, "
        f"ContaminatedRows=0, CrossUniverseBlock=HTTP {st_ag_bad}"
    )

    # 8. QRA-011: Overfitting Controls (Purged CV, Walk-Forward, DSR & 200-Trial Noise Sweep)
    st_ov_s, ov_s, _ = http_req(f"{FRONTEND_URL}/api/research/overfitting?signal=planted_alpha_strong&horizon=21")
    st_ov_n, ov_n, _ = http_req(f"{FRONTEND_URL}/api/research/overfitting?signal=planted_noise&horizon=21&n_trials=200")
    assert st_ov_s == 200 and st_ov_n == 200
    assert ov_s["deflated_sharpe"]["deflated_sharpe_ratio"] > 0.95
    sweep = ov_s["planted_noise_200_sweep"]
    assert sweep["n_configs_swept"] == 200 and sweep["dsr_significant"] is False
    results["QRA-011"] = {
        "strong_dsr": ov_s["deflated_sharpe"]["deflated_sharpe_ratio"],
        "noise_best_raw_sr": sweep["best_in_sample_sharpe"],
        "noise_best_dsr": sweep["deflated_sharpe_ratio"],
    }
    print(
        f"[PASS] QRA-011 | Strong DSR={ov_s['deflated_sharpe']['deflated_sharpe_ratio']:.4f}, "
        f"Best-of-200 Noise SR={sweep['best_in_sample_sharpe']:.2f} -> DSR={sweep['deflated_sharpe_ratio']:.4f} (Rejected)"
    )

    # 9. QRA-012: Multi-Signal Blending across all 4 modes
    for mode in ["custom", "equal_weight", "ic_weighted_252d", "ridge_oos"]:
        st_bl, bl, _ = http_req(
            f"{FRONTEND_URL}/api/research/blend",
            method="POST",
            payload={
                "method": mode,
                "horizon": 21,
                "weights": {
                    "planted_alpha_strong": 0.40,
                    "quality_composite": 0.25,
                    "value_composite": 0.20,
                    "low_vol_63d": 0.15,
                },
            },
        )
        assert st_bl == 200, f"Blend mode {mode} failed: {st_bl}"
        assert abs(sum(bl["effective_weights"].values()) - 1.0) < 1e-2
    results["QRA-012"] = {
        "ridge_oos_ic_ir": bl["blended_signal"]["ic_ir"],
        "ridge_oos_mean_ic": bl["blended_signal"]["mean_ic"],
        "half_life_days": bl["blended_signal"]["half_life_days"],
    }
    print(
        f"[PASS] QRA-012 | All 4 blend modes verified | Ridge OOS IC IR={bl['blended_signal']['ic_ir']:.2f}, "
        f"Mean IC={bl['blended_signal']['mean_ic']:.4f}, Half-Life={bl['blended_signal']['half_life_days']}d"
    )

    # 10. QRA-013: Deploy to Screener Gatekeeper (Edge Cases: Reject Noise 422, Reject Lookahead 422, Pass Valid 200)
    st_dep_noise, _, _ = http_req(
        f"{FRONTEND_URL}/api/research/deploy-to-screener",
        method="POST",
        payload={
            "strategy_name": "Overfit Noise Strategy",
            "signal_name": "planted_noise",
        },
    )
    assert st_dep_noise == 422, f"Expected 422 for overfit noise strategy, got {st_dep_noise}"

    st_dep_lk, _, _ = http_req(
        f"{FRONTEND_URL}/api/research/deploy-to-screener",
        method="POST",
        payload={
            "strategy_name": "Lookahead Contaminated Strategy",
            "signal_name": "planted_lookahead",
        },
    )
    assert st_dep_lk == 422, f"Expected 422 for lookahead strategy, got {st_dep_lk}"

    st_dep_ok, dep_ok, _ = http_req(
        f"{FRONTEND_URL}/api/research/deploy-to-screener",
        method="POST",
        payload={
            "strategy_name": "Institutional Alpha Multi-Factor v1",
            "signal_name": "planted_alpha_strong",
            "weights": {
                "planted_alpha_strong": 0.50,
                "quality_composite": 0.20,
                "value_composite": 0.15,
                "low_vol_63d": 0.15,
            },
            "top_n": 20,
        },
    )
    assert st_dep_ok == 200 and dep_ok["gate_verification"]["all_gates_passed"] is True

    st_scr, scr, _ = http_req(
        f"{FRONTEND_URL}/api/screen?strategy=planted_alpha_strong&top_n=25&sector=Technology&exclude_contradictions=true"
    )
    assert st_scr == 200 and scr["count"] > 0
    for row in scr["candidates"]:
        assert row["sector"] == "Technology", f"Sector filter failed on /api/screen: {row['sector']}"
        assert row["contradiction_flag"] is False
        assert "signal_z_score" in row and "rank" in row

    results["QRA-013"] = {
        "noise_deploy_http": st_dep_noise,
        "lookahead_deploy_http": st_dep_lk,
        "valid_deploy_http": st_dep_ok,
        "handoff_id": dep_ok["handoff_id"],
        "screener_it_rows": scr["count"],
    }
    print(
        f"[PASS] QRA-013 | Noise rejected (HTTP {st_dep_noise}), Lookahead rejected (HTTP {st_dep_lk}), "
        f"Valid deployed (HTTP {st_dep_ok}, ID={dep_ok['handoff_id']}), Screener IT rows={scr['count']}"
    )

    # 11. QRA-007: Live Next.js UI Route Rendering Check (GET /research)
    st_ui, ui_html, _ = http_req(f"{FRONTEND_URL}/research", expect_json=False)
    assert st_ui == 200, f"GET /research returned HTTP {st_ui}"
    assert "research" in ui_html.lower()
    results["QRA-007"] = {
        "research_page_http": st_ui,
        "html_bytes": len(ui_html),
    }
    print(f"[PASS] QRA-007 | Next.js /research UI rendered HTTP {st_ui} ({len(ui_html):,} bytes)")

    print("=" * 82)
    print("ALL 13 QRA LIVE HTTP, EDGE-CASE & UI CHECKS PASSED!")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_live_retest()
