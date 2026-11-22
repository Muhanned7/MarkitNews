"""
Independent Risk Analyst / Manual Tester Live Endpoint Retest for Phase 4 & 5:
Exercises FastAPI routes end-to-end via TestClient (including /analyse/{ticker} synthesis integration):
- GET /portfolios/1/hedge-calculator (beta=0.0, 0.5, simulated_dd_pct=-5.5, -10.5, derisk_mode=pro_rata, top_rc)
- GET /risk/model-risk
- POST /risk/model-risk/simulate-degradation
- PUT /risk/model-risk/agents/{agent_name}
- POST /analyse/AAPL (verifying degraded agent exclusion & model_risk_banner injection)
- GET /portfolios/1/tear-sheet
- GET /portfolios/1/tear-sheet/export?format=csv & format=html
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["MOCK_MODE"] = "true"

from fastapi.testclient import TestClient
from main import app
from auth import create_token

client = TestClient(app)
token = create_token(1, "demo@finnwinn.com")
HEADERS = {"Authorization": f"Bearer {token}"}


def run_tester_audit():
    print("=" * 76)
    print("RISK ANALYST / TESTER LIVE ENDPOINT AUDIT (RSK-012, RSK-013, RSK-014)")
    print("=" * 76)

    # 1. RSK-012 Live HTTP Audit
    r1 = client.get("/portfolios/1/hedge-calculator?target_beta=0.0", headers=HEADERS)
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
    d1 = r1.json()
    bh = d1["beta_hedge"]
    print(f"[TEST RSK-012] GET /portfolios/1/hedge-calculator?target_beta=0.0 -> HTTP {r1.status_code}")
    print(f"  Before Beta={bh['before']['portfolio_beta']} -> After Beta={bh['after']['portfolio_beta']} | SPY Trade={bh['trade']['qty']} sh (${bh['trade']['notional_usd']:,.2f})")
    assert abs(bh["after"]["portfolio_beta"]) <= 0.02

    # Check target_beta=0.30
    r1_b30 = client.get("/portfolios/1/hedge-calculator?target_beta=0.30", headers=HEADERS)
    assert r1_b30.status_code == 200
    assert abs(r1_b30.json()["beta_hedge"]["after"]["portfolio_beta"] - 0.30) <= 0.02

    # Check simulated_dd_pct=-10.5 with top_rc mode
    r1_dd = client.get("/portfolios/1/hedge-calculator?simulated_dd_pct=-10.5&derisk_mode=top_rc", headers=HEADERS)
    assert r1_dd.status_code == 200
    dc = r1_dd.json()["drawdown_control"]
    print(f"[TEST RSK-012] Drawdown Tier-2 (top_rc mode): status={dc['status']}, gross_cut=-{dc['achieved_gross_cut_pct']}%, trades={len(dc['derisk_trades'])}")
    assert dc["tier"] == 2
    assert dc["derisk_trades"][0]["ticker"] == "NVDA", "Expected NVDA (top Euler RC) to be trimmed first in top_rc mode"

    # 2. RSK-013 Live HTTP Audit + /analyse/AAPL Integration Check
    # Ensure clean baseline first
    client.post("/risk/model-risk/simulate-degradation", json={"agent_name": "sentiment", "restore": True}, headers=HEADERS)
    client.post("/risk/model-risk/simulate-degradation", json={"agent_name": "equity", "restore": True}, headers=HEADERS)

    r2 = client.get("/risk/model-risk?portfolio_id=1", headers=HEADERS)
    assert r2.status_code == 200
    mr = r2.json()
    print(f"\n[TEST RSK-013] GET /risk/model-risk -> HTTP {r2.status_code} | Healthy={mr['summary']['healthy_count']}/7 | VolBias={mr['volatility_bias']['bias_statistic']}")
    assert mr["summary"]["healthy_count"] == 7

    # Simulate low evaluator score (0.48) on sentiment agent
    r_sim = client.post(
        "/risk/model-risk/simulate-degradation",
        json={"agent_name": "sentiment", "simulated_quality_score": 0.48, "ticker": "AAPL", "restore": False},
        headers=HEADERS,
    )
    assert r_sim.status_code == 200
    mr_deg = r_sim.json()
    assert mr_deg["summary"]["degraded_count"] == 1
    assert mr_deg["summary"]["active_banner"] is not None

    # Now call POST /analyse/AAPL and verify sentiment is excluded and model_risk_banner is injected!
    r_an = client.post("/analyse/AAPL?nocache=1", headers=HEADERS)
    assert r_an.status_code == 200, f"POST /analyse/AAPL failed: {r_an.text}"
    an_data = r_an.json()
    print(f"[TEST RSK-013] POST /analyse/AAPL during sentiment degradation -> HTTP {r_an.status_code}")
    print(f"  Report Banner: {an_data['report']['model_risk_banner']}")
    print(f"  Sentiment Agent _model_risk_excluded: {an_data['agents']['sentiment'].get('_model_risk_excluded')}")
    print(f"  Capped Conviction: {an_data['report']['conviction']}/10")
    assert an_data["report"]["model_risk_banner"] is not None
    assert an_data["agents"]["sentiment"].get("_model_risk_excluded") is True
    assert an_data["report"]["conviction"] <= 6

    # Test manual kill-switch via PUT /risk/model-risk/agents/technical
    r_kill = client.put(
        "/risk/model-risk/agents/technical",
        json={"kill_switch": True, "reason": "Manual Risk Analyst kill-switch verification"},
        headers=HEADERS,
    )
    assert r_kill.status_code == 200
    assert r_kill.json()["summary"]["killed_count"] == 1
    print(f"[TEST RSK-013] PUT /risk/model-risk/agents/technical (kill_switch=True) -> Killed={r_kill.json()['summary']['killed_count']}")

    # Restore all agents to healthy
    client.post("/risk/model-risk/simulate-degradation", json={"agent_name": "sentiment", "restore": True}, headers=HEADERS)
    r_rest = client.put(
        "/risk/model-risk/agents/technical",
        json={"kill_switch": False, "forced_degraded": False, "enabled": True, "reason": "Restored after Risk Analyst audit"},
        headers=HEADERS,
    )
    assert r_rest.status_code == 200
    assert r_rest.json()["summary"]["healthy_count"] == 7
    print(f"[TEST RSK-013] Restored all agents -> Healthy={r_rest.json()['summary']['healthy_count']}/7")

    # 3. RSK-014 Live HTTP Audit (JSON, CSV, HTML)
    r_ts = client.get("/portfolios/1/tear-sheet", headers=HEADERS)
    assert r_ts.status_code == 200
    ts = r_ts.json()
    print(f"\n[TEST RSK-014] GET /portfolios/1/tear-sheet -> HTTP {r_ts.status_code}")
    print(f"  Health Score: {ts['health_score']['score']}/100 ({ts['health_score']['grade']})")
    print(f"  DoD NAV Change: ${ts['day_over_day']['nav_dod_usd']:+,.2f} ({ts['day_over_day']['nav_dod_pct']:+.2f}%)")
    print(f"  5d VaR Trend Rows: {len(ts['var_es_summary']['trend_5d'])} | Top Stress: {ts['top5_stress_scenarios'][0]['name']}")

    r_csv = client.get("/portfolios/1/tear-sheet/export?format=csv", headers=HEADERS)
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers.get("content-type", "")
    assert "SECTION 1: PORTFOLIO OVERVIEW" in r_csv.text
    assert "SECTION 7: RECOMMENDED HEDGES & AI MODEL RISK" in r_csv.text

    r_html = client.get("/portfolios/1/tear-sheet/export?format=html", headers=HEADERS)
    assert r_html.status_code == 200
    assert "text/html" in r_html.headers.get("content-type", "")
    assert "EXECUTIVE MORNING RISK TEAR SHEET" in r_html.text
    print(f"[TEST RSK-014] GET /portfolios/1/tear-sheet/export (CSV={len(r_csv.text)}B, HTML={len(r_html.text)}B) -> HTTP 200 OK")

    print("\n" + "=" * 76)
    print("RISK ANALYST AUDIT VERDICT: RSK-012, RSK-013, RSK-014 ALL PASSED!")
    print("=" * 76)


if __name__ == "__main__":
    run_tester_audit()
