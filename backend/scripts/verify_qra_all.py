"""
Verification & Edge-Case Audit Suite for Quantitative Research Analyst (QRA-001 .. QRA-013)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.qra_engine import (
    GICS_11_SECTORS,
    MOCK_DELISTINGS,
    N_RESEARCH_DAYS,
    SIGNAL_CATALOG,
    compare_research_runs,
    compute_ic_tear_sheet,
    ensure_qra_schema,
    get_research_panel,
    get_research_panel_csv,
    get_research_universe,
    get_signal_details,
    get_standardized_signal,
    get_universe_as_of,
    list_research_runs,
    run_backtest,
    save_research_run,
    scan_signal_leakage,
)
from agents.qra_advanced import (
    compute_agent_evaluation_lab,
    compute_factor_attribution,
    compute_overfitting_controls,
    compute_signal_blend,
    deploy_strategy_to_screener,
    run_quantitative_screener,
)


def main():
    print("=" * 78)
    print("FINNWINN QRA TRACK — MATHEMATICAL & ACCEPTANCE VERIFICATION (QRA-001 .. QRA-013)")
    print("=" * 78)

    # ------------------------------------------------------------------
    # QRA-001: Research Universe with Planted Signals & 5 Delistings
    # ------------------------------------------------------------------
    u = get_research_universe()
    assert len(u["tickers"]) == 100, f"Expected 100 tickers, got {len(u['tickers'])}"
    assert len(set(u["sectors"])) == 11, f"Expected 11 sectors, got {len(set(u['sectors']))}"
    assert len(u["dates"]) == N_RESEARCH_DAYS == 2520, f"Expected 2520 days, got {len(u['dates'])}"
    assert len(u["delistings"]) == 5, f"Expected 5 delistings, got {len(u['delistings'])}"
    print(f"[PASS] QRA-001 Universe: {len(u['tickers'])} tickers, {len(set(u['sectors']))} sectors, {len(u['dates'])} trading days, {len(u['delistings'])} delistings")

    # ------------------------------------------------------------------
    # QRA-002: Point-in-Time Panel API & Survivorship-Free Universe
    # ------------------------------------------------------------------
    u_2021 = get_universe_as_of("2021-06-15")
    u_2026 = get_universe_as_of("2026-10-14")
    assert u_2021["active_count"] == 100, f"Expected 100 active in 2021, got {u_2021['active_count']}"
    assert u_2021["active_later_delisted_count"] == 5, "All 5 future delistings must be active in 2021"
    assert u_2026["active_count"] == 95, f"Expected 95 active in 2026, got {u_2026['active_count']}"
    assert u_2026["already_delisted_count"] == 5, "All 5 delistings must be excluded by 2026"

    for test_date in ("2019-05-10", "2022-11-15", "2024-08-20", "2026-10-14"):
        panel = get_research_panel(as_of_date=test_date, limit=2000)
        assert panel["pit_verified"] is True and panel["pit_violations"] == 0
        for row in panel["rows"]:
            if row["report_date"] is not None:
                assert row["report_date"] <= row["date"], f"PIT leak: report_date {row['report_date']} > {row['date']}"
    csv_txt = get_research_panel_csv(as_of_date="2026-10-14", limit=200)
    assert "date,ticker,field,value,period_end,report_date" in csv_txt
    print(f"[PASS] QRA-002 PIT Panel & Universe: 2021 active={u_2021['active_count']} (incl. 5 later delisted), 2026 active={u_2026['active_count']}; 0 report_date leaks")

    # ------------------------------------------------------------------
    # QRA-003: Signal Library & Standardisation (Winsorise, Z-Score, Neutralise)
    # ------------------------------------------------------------------
    assert len(SIGNAL_CATALOG) == 12, f"Expected 12 signals, got {len(SIGNAL_CATALOG)}"
    _, diag_raw = get_standardized_signal("value_composite", winsorize=True, sector_neutral=False, beta_neutral=False, zscore=True)
    _, diag_sec = get_standardized_signal("value_composite", winsorize=True, sector_neutral=True, beta_neutral=True, zscore=True)
    assert abs(diag_raw["mean_cross_sectional_mean"]) < 1e-4, f"Expected mean ~0, got {diag_raw['mean_cross_sectional_mean']}"
    assert abs(diag_raw["mean_cross_sectional_sd"] - 1.0) < 1e-3, f"Expected sd ~1, got {diag_raw['mean_cross_sectional_sd']}"
    assert diag_sec["max_abs_sector_dummy_corr"] < 1e-4, f"Expected ~0 sector corr, got {diag_sec['max_abs_sector_dummy_corr']}"
    assert abs(diag_sec["mean_beta_corr"]) < 1e-4, f"Expected ~0 beta corr, got {diag_sec['mean_beta_corr']}"
    print(
        f"[PASS] QRA-003 Signal Standardisation: mean={diag_sec['mean_cross_sectional_mean']:.6f}, "
        f"sd={diag_sec['mean_cross_sectional_sd']:.6f}, max_sec_corr={diag_sec['max_abs_sector_dummy_corr']:.6f}, "
        f"beta_corr={diag_sec['mean_beta_corr']:.6f}"
    )

    # ------------------------------------------------------------------
    # QRA-004 & QRA-007: IC Tear Sheet, Planted IC Recovery & Quintile Monotonicity
    # ------------------------------------------------------------------
    ts_strong = compute_ic_tear_sheet("planted_alpha_strong", horizon=21)
    ts_weak = compute_ic_tear_sheet("planted_alpha_weak", horizon=21)
    ts_noise = compute_ic_tear_sheet("planted_noise", horizon=21)

    ic_strong = ts_strong["summary"]["mean_ic"]
    ic_weak = ts_weak["summary"]["mean_ic"]
    ic_noise = ts_noise["summary"]["mean_ic"]
    t_noise_spread = abs(ts_noise["summary"]["q5_q1_t_stat"])

    assert abs(ic_strong - 0.05) <= 0.01, f"planted_alpha_strong IC={ic_strong} outside 0.05 +/- 0.01"
    assert abs(ic_weak - 0.02) <= 0.01, f"planted_alpha_weak IC={ic_weak} outside 0.02 +/- 0.01"
    assert abs(ic_noise - 0.00) <= 0.01, f"planted_noise IC={ic_noise} outside 0.00 +/- 0.01"
    assert t_noise_spread < 2.0, f"planted_noise Q5-Q1 t-stat={t_noise_spread} must be < 2.0"
    assert ts_strong["summary"]["quintile_monotonic"] is True, "planted_alpha_strong must have strict Q1 < Q2 < Q3 < Q4 < Q5"
    assert len(ts_strong["sector_ic_boxplot"]) == 11, "Must include all 11 GICS sectors in boxplot"
    print(
        f"[PASS] QRA-004 & QRA-007 Tear Sheet: strong IC={ic_strong:.4f} (monotonic={ts_strong['summary']['quintile_monotonic']}), "
        f"weak IC={ic_weak:.4f}, noise IC={ic_noise:.4f} (|t_spread|={t_noise_spread:.2f} < 2.0)"
    )

    # ------------------------------------------------------------------
    # QRA-008: Automated Lookahead Bias & Leakage Scanner
    # ------------------------------------------------------------------
    leak_clean = scan_signal_leakage("planted_alpha_strong", lag=1)
    leak_lookahead = scan_signal_leakage("planted_lookahead", lag=1)
    leak_bad_pit = scan_signal_leakage("value_composite", lag=1, simulate_bad_report_date=True)

    assert leak_clean["passed"] is True and leak_clean["badge"] == "POINT_IN_TIME_VERIFIED"
    assert leak_lookahead["passed"] is False and leak_lookahead["badge"] == "LEAKAGE_WARNING"
    assert leak_lookahead["unlagged_corr_s_t_r_t1"] > 0.35
    assert leak_bad_pit["passed"] is False and leak_bad_pit["pit_breach"] is True
    print(
        f"[PASS] QRA-008 Leakage Scanner: clean={leak_clean['badge']} (corr={leak_clean['unlagged_corr_s_t_r_t1']:.4f}), "
        f"planted_lookahead={leak_lookahead['badge']} (corr={leak_lookahead['unlagged_corr_s_t_r_t1']:.4f} > 0.35)"
    )

    # ------------------------------------------------------------------
    # QRA-005: Backtester (Reproducibility, Monotonic Cost Drag, Lookahead Guard)
    # ------------------------------------------------------------------
    bt1 = run_backtest("planted_alpha_strong", rebalance_freq="monthly", fixed_cost_bps=5.0, lag=1)
    bt2 = run_backtest("planted_alpha_strong", rebalance_freq="monthly", fixed_cost_bps=5.0, lag=1)
    assert bt1["config_hash"] == bt2["config_hash"]
    assert bt1["net_metrics"]["sharpe"] == bt2["net_metrics"]["sharpe"]

    bt_c0 = run_backtest("planted_alpha_strong", rebalance_freq="weekly", fixed_cost_bps=0.0, impact_coeff=0.0, lag=1)
    bt_c10 = run_backtest("planted_alpha_strong", rebalance_freq="weekly", fixed_cost_bps=10.0, impact_coeff=0.10, lag=1)
    bt_c35 = run_backtest("planted_alpha_strong", rebalance_freq="weekly", fixed_cost_bps=35.0, impact_coeff=0.25, lag=1)
    assert bt_c0["net_metrics"]["cagr_pct"] > bt_c10["net_metrics"]["cagr_pct"] > bt_c35["net_metrics"]["cagr_pct"], (
        "Costs must reduce net returns strictly monotonically"
    )

    bt_look_lag0 = run_backtest("planted_lookahead", rebalance_freq="daily", fixed_cost_bps=5.0, impact_coeff=0.10, lag=0)
    bt_look_lag1 = run_backtest("planted_lookahead", rebalance_freq="daily", fixed_cost_bps=5.0, impact_coeff=0.10, lag=1)
    assert bt_look_lag0["net_metrics"]["sharpe"] > 5.0, f"Expected lag=0 lookahead Sharpe > 5, got {bt_look_lag0['net_metrics']['sharpe']}"
    assert abs(bt_look_lag1["gross_metrics"]["sharpe"]) < 1.0 and bt_look_lag1["net_metrics"]["sharpe"] < 1.0, (
        f"Expected lag=1 lookahead Sharpe neutralized (<1.0), got gross={bt_look_lag1['gross_metrics']['sharpe']}"
    )
    print(
        f"[PASS] QRA-005 Backtester: hash={bt1['config_hash']}, monotonic cost CAGR "
        f"({bt_c0['net_metrics']['cagr_pct']}% > {bt_c10['net_metrics']['cagr_pct']}% > {bt_c35['net_metrics']['cagr_pct']}%), "
        f"lookahead Sharpe lag0={bt_look_lag0['net_metrics']['sharpe']:.2f} (>5) vs lag1 gross={bt_look_lag1['gross_metrics']['sharpe']:.2f} (net={bt_look_lag1['net_metrics']['sharpe']:.2f})"
    )

    # ------------------------------------------------------------------
    # QRA-006: Experiment Tracking (`research_runs` Table & Comparison)
    # ------------------------------------------------------------------
    ensure_qra_schema()
    runs_list = list_research_runs()
    assert runs_list["total_runs"] >= 4
    r_ids = [r["id"] for r in runs_list["runs"][:3]]
    comp = compare_research_runs(r_ids)
    assert len(comp["runs"]) == len(r_ids)
    assert len(comp["overlaid_equity_curve"]) > 50
    print(f"[PASS] QRA-006 Experiment Tracker: {runs_list['total_runs']} saved runs, compared IDs={comp['compared_run_ids']}")

    # ------------------------------------------------------------------
    # QRA-009: Factor Model & Orthogonalisation
    # ------------------------------------------------------------------
    fac_mom = compute_factor_attribution("momentum_12_1")
    mom_loading = next(item for item in fac_mom["loadings"] if item["factor"] == "MOM")
    assert abs(mom_loading["beta"] - 1.0) < 0.05, f"Momentum 12-1 must load ~1.0 on MOM factor, got {mom_loading['beta']}"
    assert abs(fac_mom["alpha"]["alpha_annual_pct"]) < 0.5, f"Momentum 12-1 residual alpha must be ~0, got {fac_mom['alpha']['alpha_annual_pct']}"

    fac_strong = compute_factor_attribution("planted_alpha_strong")
    assert fac_strong["alpha"]["significant"] is True and fac_strong["alpha"]["t_stat"] > 3.0
    print(
        f"[PASS] QRA-009 Factor Model: momentum_12_1 MOM beta={mom_loading['beta']:.4f}, alpha={fac_mom['alpha']['alpha_annual_pct']}%; "
        f"planted_alpha_strong residual alpha=+{fac_strong['alpha']['alpha_annual_pct']}% (t={fac_strong['alpha']['t_stat']:.2f})"
    )

    # ------------------------------------------------------------------
    # QRA-010: AI Agent Evaluation Lab
    # ------------------------------------------------------------------
    ag_lab = compute_agent_evaluation_lab("mock100")
    assert ag_lab["hygiene_audit"]["verified_clean"] is True
    assert ag_lab["hygiene_audit"]["contaminated_rows_joined"] == 0
    assert ag_lab["synthesizer_summary"]["conviction_monotonic"] is True
    assert len(ag_lab["per_agent_ic"]) == 6
    assert len(ag_lab["ablation_study"]) == 7
    assert len(ag_lab["version_comparison"]) == 4
    print(
        f"[PASS] QRA-010 AI Agent Lab: Synthesizer IC={ag_lab['synthesizer_summary']['mean_ic_21d']}, "
        f"Brier={ag_lab['synthesizer_summary']['brier_score_63d']}, 0 cross-universe contamination"
    )

    # ------------------------------------------------------------------
    # QRA-011: Overfitting Controls & Deflated Sharpe Ratio (200-Config Sweep)
    # ------------------------------------------------------------------
    ov_strong = compute_overfitting_controls("planted_alpha_strong", horizon=21)
    ov_noise = compute_overfitting_controls("planted_noise", horizon=21)
    sweep = ov_strong["planted_noise_200_sweep"]

    assert ov_strong["deflated_sharpe"]["deflated_sharpe_ratio"] > 0.95
    assert sweep["n_configs_swept"] == 200
    assert sweep["best_in_sample_sharpe"] > 1.0
    assert sweep["deflated_sharpe_ratio"] < 0.50 and sweep["dsr_significant"] is False
    print(
        f"[PASS] QRA-011 Overfitting & DSR: planted_alpha_strong DSR={ov_strong['deflated_sharpe']['deflated_sharpe_ratio']:.4f} (>0.95); "
        f"200-config noise sweep best IS Sharpe={sweep['best_in_sample_sharpe']:.2f} -> DSR={sweep['deflated_sharpe_ratio']:.4f} (non-significant)"
    )

    # ------------------------------------------------------------------
    # QRA-012: Multi-Signal Blending Studio & Alpha Decay
    # ------------------------------------------------------------------
    blend = compute_signal_blend(
        weights={
            "planted_alpha_strong": 0.35,
            "momentum_12_1": 0.25,
            "value_composite": 0.20,
            "quality_composite": 0.20,
        },
        method="custom",
        horizon=21,
    )
    assert blend["diversification_benefit"]["lower_volatility_achieved"] is True
    assert blend["blended_signal"]["ic_ir"] > max(
        c["ic_ir"] for c in blend["constituent_signals"] if c["signal"] != "planted_alpha_strong"
    )
    print(
        f"[PASS] QRA-012 Signal Blending: blended IC Vol={blend['blended_signal']['ic_volatility']:.4f} "
        f"(-{blend['diversification_benefit']['ic_volatility_reduction_pct']}% vs constituents), "
        f"blended IC IR={blend['blended_signal']['ic_ir']:.2f}, half-life={blend['blended_signal']['half_life_days']}d"
    )

    # ------------------------------------------------------------------
    # QRA-013: "Deploy to Screener" Production Handoff & Gate Enforcement
    # ------------------------------------------------------------------
    # 1. Verify that deploying `planted_noise` or `planted_lookahead` is blocked by the gate
    blocked_noise = False
    try:
        deploy_strategy_to_screener("Noise Test", signal_name="planted_noise")
    except PermissionError:
        blocked_noise = True
    assert blocked_noise is True, "planted_noise must be rejected by the DSR/OOS Sharpe gate"

    blocked_leak = False
    try:
        deploy_strategy_to_screener("Leak Test", signal_name="planted_lookahead")
    except PermissionError:
        blocked_leak = True
    assert blocked_leak is True, "planted_lookahead must be rejected by the leakage gate"

    # 2. Verify that deploying `planted_alpha_strong` succeeds and populates `/screen`
    deployed = deploy_strategy_to_screener("Alpha Strong Prod", signal_name="planted_alpha_strong", top_n=15)
    assert deployed["gate_verification"]["all_gates_passed"] is True
    assert len(deployed["candidates"]) == 15

    screen_res = run_quantitative_screener(strategy="planted_alpha_strong", min_z=1.0, exclude_contradictions=True, top_n=15)
    assert screen_res["count"] > 0
    assert screen_res["latest_deployed_handoff"]["handoff_id"] == deployed["handoff_id"]
    print(
        f"[PASS] QRA-013 Screener Handoff: noise & lookahead blocked by gate; planted_alpha_strong deployed "
        f"(Handoff #{deployed['handoff_id']}, DSR={deployed['gate_verification']['dsr']}, OOS Sharpe={deployed['gate_verification']['oos_sharpe']}) -> {screen_res['count']} candidates in /screen"
    )

    print("=" * 78)
    print("ALL 13 QRA TASKS (QRA-001 .. QRA-013) PASSED VERIFICATION SUITE!")
    print("=" * 78)


if __name__ == "__main__":
    main()
