"""
Verification suite for Phase 4 & Phase 5 Risk Analyst tasks:
- RSK-012: Beta & Sector ETF Hedge Calculator + Drawdown Control Rules (R-P1-4, R-P1-5)
- RSK-013: AI Agent Model-Risk Monitor, Disagreement Index, Vol Bias & Kill-Switch (R-P2-1, R-P2-2, R-P2-4)
- RSK-014: Executive Morning Risk Tear Sheet & Export (R-P2-3, R-P2-5)
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.risk_router import ensure_risk_schema, _load_portfolio, load_limits
from agents.risk_phase4 import (
    hedge_calculator,
    model_risk_dashboard,
    set_agent_control,
    simulate_agent_degradation,
    get_degraded_agents_for_synthesis,
    morning_tear_sheet,
    tear_sheet_csv,
    tear_sheet_html,
)


def main():
    ensure_risk_schema()
    portfolio_id = 1
    portfolio, raw = _load_portfolio(portfolio_id)
    limits = load_limits(portfolio_id)
    cash = float(portfolio["cash"])

    print("=" * 72)
    print("PHASE 4 & 5 VERIFICATION SUITE (RSK-012, RSK-013, RSK-014)")
    print("=" * 72)

    # ------------------------------------------------------------------
    # 1. RSK-012 Verification
    # ------------------------------------------------------------------
    h0 = hedge_calculator(raw, cash, limits, target_beta=0.0, simulated_dd_pct=None, derisk_mode="pro_rata")
    bh = h0["beta_hedge"]
    print(f"\n[RSK-012] 1. SPY Beta-Neutral Hedge:")
    print(f"  Before Beta: {bh['before']['portfolio_beta']} -> After Beta: {bh['after']['portfolio_beta']} (Residual: {bh['beta_residual']})")
    print(f"  SPY Trade:   {bh['trade']['action']} {bh['trade']['qty']} SPY @ ${bh['trade']['price']} (Notional: ${bh['trade']['notional_usd']:,.2f})")
    print(f"  Before Vol:  {bh['before']['ex_ante_vol_pct']}% -> After Vol: {bh['after']['ex_ante_vol_pct']}%")
    assert bh["within_tolerance_002"], f"Expected post-hedge beta within +-0.02 of 0.0, got {bh['after']['portfolio_beta']}"

    tech_hedge = next((s for s in h0["sector_hedges"] if s["sector"] == "Technology"), None)
    assert tech_hedge is not None, "Technology sector hedge plan missing"
    print(f"\n[RSK-012] 2. Technology Sector Concentration Hedge:")
    print(f"  Current Tech Weight: {tech_hedge['current_weight_pct']}% (Hard Limit: {tech_hedge['hard_limit_pct']}%, Status: {tech_hedge['status']})")
    print(f"  XLK ETF Hedge:       {tech_hedge['etf_hedge']['trade']['action']} {tech_hedge['etf_hedge']['trade']['qty']} {tech_hedge['etf_hedge']['trade']['ticker']} "
          f"-> Post-ETF Tech Weight: {tech_hedge['etf_hedge']['post_sector_weight_pct']}%")
    print(f"  Single-Name Trim:    {len(tech_hedge['single_name_trim']['trades'])} trades "
          f"-> Post-Trim Tech Weight: {tech_hedge['single_name_trim']['post_sector_weight_pct']}%")
    assert tech_hedge["etf_hedge"]["within_hard_limit"], "XLK hedge did not bring Technology within 30% hard limit"
    assert tech_hedge["single_name_trim"]["within_hard_limit"], "Single-name trim did not bring Technology within 30% hard limit"

    h_dd1 = hedge_calculator(raw, cash, limits, simulated_dd_pct=-5.5)
    h_dd2 = hedge_calculator(raw, cash, limits, simulated_dd_pct=-10.5, derisk_mode="pro_rata")
    dc2 = h_dd2["drawdown_control"]
    print(f"\n[RSK-012] 3. Drawdown Control Rules (R-P1-4):")
    print(f"  Actual 252d DD: {h0['drawdown_control']['actual_drawdown_pct']}% (Status: {h0['drawdown_control']['status']})")
    print(f"  Sim -5.5% DD:   Tier {h_dd1['drawdown_control']['tier']} ({h_dd1['drawdown_control']['status']})")
    print(f"  Sim -10.5% DD:  Tier {dc2['tier']} ({dc2['status']}) | Gross Cut Achieved: -{dc2['achieved_gross_cut_pct']}% | Vol Reduction: -{dc2['vol_reduction_pct']}%")
    assert h_dd1["drawdown_control"]["tier"] == 1
    assert dc2["tier"] == 2
    assert 24.0 <= dc2["achieved_gross_cut_pct"] <= 26.0, f"Expected ~25% gross exposure cut, got {dc2['achieved_gross_cut_pct']}%"
    assert 24.0 <= dc2["vol_reduction_pct"] <= 26.0, f"Expected ~25% vol reduction, got {dc2['vol_reduction_pct']}%"

    # ------------------------------------------------------------------
    # 2. RSK-013 Verification
    # ------------------------------------------------------------------
    # First ensure all agents are restored to healthy
    for ag in ("news", "sentiment", "fundamentals", "technical", "equity", "risk", "portfolio_manager"):
        simulate_agent_degradation(ag, restore=True, actor="verifier")

    mr0 = model_risk_dashboard(raw, cash)
    print(f"\n[RSK-013] 1. Baseline Model-Risk Dashboard:")
    print(f"  Healthy: {mr0['summary']['healthy_count']}/{mr0['summary']['total_agents']} | Banner: {mr0['summary']['active_banner']}")
    print(f"  Vol Bias Statistic: {mr0['volatility_bias']['bias_statistic']} ({mr0['volatility_bias']['status']}) "
          f"| Ex-Ante {mr0['volatility_bias']['ex_ante_vol_ann_pct']}% vs Realized {mr0['volatility_bias']['ex_post_vol_ann_pct']}%")
    print(f"  Disagreement Index Top Ticker: {mr0['disagreement_index'][0]['ticker']} = {mr0['disagreement_index'][0]['disagreement_index']}")
    assert mr0["summary"]["healthy_count"] == 7

    # Simulate degradation of sentiment agent below 0.70
    simulate_agent_degradation("sentiment", simulated_quality_score=0.52, ticker="AAPL", restore=False, actor="verifier")
    mr_deg = model_risk_dashboard(raw, cash)
    syn_state = get_degraded_agents_for_synthesis()
    print(f"\n[RSK-013] 2. After Simulating Sentiment Agent Degradation (score=0.52 < 0.70):")
    print(f"  Degraded Count: {mr_deg['summary']['degraded_count']} | Banner: {syn_state['model_risk_banner']}")
    assert mr_deg["summary"]["degraded_count"] == 1
    assert any(d["agent_name"] == "sentiment" for d in syn_state["degraded_agents"])
    assert syn_state["model_risk_banner"] is not None

    # Test manual kill-switch on technical agent
    set_agent_control("technical", kill_switch=True, reason="Verifier kill-switch test", actor="verifier")
    mr_kill = model_risk_dashboard(raw, cash)
    print(f"\n[RSK-013] 3. After Engaging Manual Kill-Switch on Technical Agent:")
    print(f"  Degraded: {mr_kill['summary']['degraded_count']}, Killed: {mr_kill['summary']['killed_count']}")
    assert mr_kill["summary"]["killed_count"] == 1

    # Restore both agents to healthy so clean state is left in DB
    simulate_agent_degradation("sentiment", restore=True, actor="verifier")
    set_agent_control("technical", kill_switch=False, forced_degraded=False, enabled=True, reason="Restored by verifier", actor="verifier")
    mr_restored = model_risk_dashboard(raw, cash)
    assert mr_restored["summary"]["healthy_count"] == 7
    print(f"  Restored All Agents -> Healthy: {mr_restored['summary']['healthy_count']}/7")

    # ------------------------------------------------------------------
    # 3. RSK-014 Verification
    # ------------------------------------------------------------------
    sheet = morning_tear_sheet(portfolio_id, portfolio, raw, limits)
    csv_out = tear_sheet_csv(sheet)
    html_out = tear_sheet_html(sheet)
    print(f"\n[RSK-014] Executive Morning Risk Tear Sheet:")
    print(f"  Portfolio:         {sheet['portfolio_name']} (NAV ${sheet['overview']['nav']:,.2f})")
    print(f"  Risk Health Score: {sheet['health_score']['score']}/100 ({sheet['health_score']['grade']})")
    print(f"  Deductions:        {sheet['health_score']['deductions']}")
    print(f"  Top 5 Stress #1:   {sheet['top5_stress_scenarios'][0]['name']} ({sheet['top5_stress_scenarios'][0]['pnl_pct']}% NAV)")
    print(f"  Top 3 Risk #1:     {sheet['top3_risk_contributors'][0]['ticker']} ({sheet['top3_risk_contributors'][0]['pct_contribution']:.2f}% of VaR)")
    print(f"  Export Sizes:      CSV = {len(csv_out)} bytes | HTML = {len(html_out)} bytes")
    assert 0 <= sheet["health_score"]["score"] <= 100
    assert len(sheet["top5_stress_scenarios"]) == 5
    assert len(sheet["top3_risk_contributors"]) == 3
    assert "MARKETPULSE EXECUTIVE MORNING RISK TEAR SHEET" in csv_out
    assert "<title>Morning Risk Tear Sheet" in html_out

    print("\n" + "=" * 72)
    print("ALL PHASE 4 & PHASE 5 CHECKS PASSED SUCCESSFULLY!")
    print("=" * 72)


if __name__ == "__main__":
    main()
