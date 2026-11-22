"""
End-to-End Verification Test Suite for QPM (Quantitative Portfolio Manager) Features
Tests QPM-001 through QPM-008.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import json
import psycopg2

BASE_URL = "http://localhost:8000"
NEXT_URL = "http://localhost:3000"
HEADERS = {
    "Content-Type": "application/json",
    "x-service-key": os.environ.get("INTERNAL_SERVICE_KEY", "")
}

def req(url, method="GET", data=None):
    payload = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=payload, headers=HEADERS, method=method)
    with urllib.request.urlopen(r) as response:
        return json.loads(response.read().decode())

def run_tests():
    print("==================================================")
    print("Running QPM Full Acceptance Verification Suite")
    print("==================================================")

    # 1. QPM-001: Per-ticker seeded mock data
    print("\n[TEST QPM-001] Checking distinct deterministic mock data...")
    from agents.mock_market_data import get_deterministic_mock_profile
    p_aapl = get_deterministic_mock_profile("AAPL")
    p_msft = get_deterministic_mock_profile("MSFT")
    p_nvda = get_deterministic_mock_profile("NVDA")
    assert p_aapl["current_price"] != p_msft["current_price"] != p_nvda["current_price"], "Prices must differ!"
    assert p_aapl["current_price"] != 192.25 or p_msft["current_price"] != 192.25, "Must not be uniform 192.25 placeholder!"
    assert len(p_aapl["price_series_252d"]) == 252, "Must have 252-day price series!"
    print(f"  PASS: AAPL=${p_aapl['current_price']}, MSFT=${p_msft['current_price']}, NVDA=${p_nvda['current_price']}")

    # 2. QPM-002: PostgreSQL Schema Migrations
    print("\n[TEST QPM-002] Checking PostgreSQL tables...")
    conn = psycopg2.connect("postgresql://postgres:123@localhost:5432/MarketPulse")
    cur = conn.cursor()
    for tbl in ["portfolios", "positions", "transactions", "analysis_snapshots"]:
        cur.execute(f"SELECT count(*) FROM {tbl}")
        print(f"  Table '{tbl}' verified (rows: {cur.fetchone()[0]})")
    conn.close()
    print("  PASS: All 4 QPM tables exist in PostgreSQL.")

    # 3. QPM-003: Portfolio REST Endpoints
    print("\n[TEST QPM-003] Checking Portfolio REST endpoints...")
    ports = req(f"{BASE_URL}/portfolios")
    assert len(ports) >= 1, "Must return at least 1 portfolio!"
    p_id = ports[0]["id"]
    port_detail = req(f"{BASE_URL}/portfolios/{p_id}")
    assert "holdings" in port_detail, "Must contain holdings object"
    assert port_detail["holdings"]["nav"] > 0, "NAV must be positive"
    print(f"  PASS: Portfolio {p_id} ('{port_detail['portfolio']['name']}'): NAV=${port_detail['holdings']['nav']:,}")

    # 4. QPM-004: Portfolio Workstation & Weights sum to 100%
    print("\n[TEST QPM-004] Checking Holdings weights and Next.js /portfolio...")
    holdings = port_detail["holdings"]
    pos_weights_sum = sum(p["weight_pct"] for p in holdings["positions"])
    total_weights = holdings["cash_weight_pct"] + pos_weights_sum
    assert round(total_weights, 1) == 100.0, f"Total weights must equal 100%! Got {total_weights}"
    # Next.js route check
    with urllib.request.urlopen(f"{NEXT_URL}/portfolio") as r_page:
        assert r_page.status == 200, "Next.js /portfolio must return 200"
    print(f"  PASS: Total weights sum: {round(total_weights, 2)}% (Cash: {holdings['cash_weight_pct']}%, Positions: {round(pos_weights_sum, 2)}%). /portfolio HTTP 200 OK.")

    # 5. QPM-005: Portfolio Risk & Risk Attribution
    print("\n[TEST QPM-005] Checking Ledoit-Wolf Risk Attribution & Heatmap...")
    risk_res = req(f"{BASE_URL}/portfolios/{p_id}/risk")
    risk = risk_res["risk"]
    rc_sum = sum(r["risk_contribution_pct"] for r in risk["risk_contributions"])
    assert round(rc_sum, 1) == 100.0, f"Risk contributions must sum to 100%! Got {rc_sum}"
    assert len(risk["correlation_matrix"]["tickers"]) > 0, "Must contain correlation matrix"
    print(f"  PASS: Portfolio Vol: {risk['portfolio_volatility']*100:.1f}%, Beta: {risk['portfolio_beta']}, RC Sum: {round(rc_sum, 1)}%, Effective Bets: {risk['effective_bets']}")

    # 6. QPM-006: Position Sizing Engine
    print("\n[TEST QPM-006] Checking quantitative position sizing on NVDA...")
    sizing = req(f"{BASE_URL}/portfolios/{p_id}/sizing/NVDA")
    assert "suggested_weight_pct" in sizing, "Must return suggested weight"
    assert "binding_constraint" in sizing, "Must name binding constraint"
    assert sizing["suggested_shares"] >= 0, "Shares must be non-negative"
    print(f"  PASS: Suggested allocation: {sizing['suggested_weight_pct']}% (~{sizing['suggested_shares']} shares). Binding constraint: '{sizing['binding_constraint']}'")

    # 7. QPM-007: Verdict Actionability & Scenarios
    print("\n[TEST QPM-007] Checking Actionable Verdict and Bull/Base/Bear scenarios...")
    analysis = req(f"{BASE_URL}/analyse/AAPL?nocache=1", method="POST")
    rep = analysis["report"]
    assert "expected_return" in rep, "Must include expected return"
    assert "horizon_days" in rep, "Must include horizon_days"
    assert "invalidation_price" in rep, "Must include invalidation_price"
    scenarios = rep["scenarios"]
    prob_sum = scenarios["bear"]["prob"] + scenarios["base"]["prob"] + scenarios["bull"]["prob"]
    assert round(prob_sum, 2) == 1.0, f"Scenario probabilities must sum to 1.0! Got {prob_sum}"
    print(f"  PASS: Expected return: {rep['expected_return']}%, Horizon: {rep['horizon_days']}d, Stop: ${rep['invalidation_price']}, Scenario probs sum: {prob_sum}")

    # 8. QPM-008: Snapshot Diff Engine
    print("\n[TEST QPM-008] Checking Analysis Snapshot Persistence & Diff Engine...")
    diff = req(f"{BASE_URL}/snapshots/AAPL/diff")
    assert diff["has_prior"] is True, "Must identify prior snapshot for AAPL"
    assert "conviction" in diff and "target" in diff and "price" in diff, "Diff must contain conviction, target, and price comparisons"
    print(f"  PASS: Snapshot diff verified: Prior={diff['as_of_previous'][:19]}, Curr={diff['as_of_current'][:19]}, Conviction Delta={diff['conviction']['delta']}")

    print("\n==================================================")
    print("ALL 8 QPM ACCEPTANCE TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
