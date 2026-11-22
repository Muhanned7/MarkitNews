"""
RSK-001 verification: fat tails, volatility clustering, stress-window correlation,
plus QPM-001 regression checks. No database needed.
Run from backend/:  python3 scripts/verify_rsk001.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.mock_market_data import compute_mock_diagnostics, get_deterministic_mock_profile  # noqa: E402

ANCHORS = ["AAPL", "MSFT", "NVDA", "TSLA", "JPM", "XOM", "GOOGL", "AMZN", "SPY"]
EXTRA = ["IBM", "KO", "PFE", "INTC", "AMD", "META", "NFLX", "BAC", "WMT", "DIS",
         "CRM", "ORCL", "V", "MA", "HD", "PG", "UNH", "CVX", "PEP", "COST"]


def main() -> int:
    ok = True
    for label, universe in (("anchors", ANCHORS), ("extra", EXTRA)):
        d = compute_mock_diagnostics(universe)
        s, c = d["summary"], d["stress_correlation"]
        print(f"[{label}] kurtosis>1: {s['kurtosis_pass_count']}/{s['n']}  "
              f"acf1(r^2)>0.1: {s['acf_pass_count']}/{s['n']} (median {s['median_acf1_squared']})  "
              f"corr calm {c['calm_avg_pairwise_corr']} stress {c['stress_avg_pairwise_corr']} x{c['ratio']}")
        for r in d["tickers"]:
            if not (r["kurtosis_pass"] and r["acf_pass"]):
                print(f"    below threshold: {r['ticker']} kurt={r['excess_kurtosis']} acf1={r['acf1_squared_returns']}")
        ok &= s["kurtosis_pass_count"] > s["n"] / 2 and s["acf_pass_count"] > s["n"] / 2 and c["pass"]

    profs = {t: get_deterministic_mock_profile(t) for t in ["AAPL", "MSFT", "NVDA", "GOOGL"]}
    last_bar = all(p["price_series_504d"][-1] == p["current_price"] for p in profs.values())
    distinct = len({p["current_price"] for p in profs.values()}) == len(profs)
    cm = np.corrcoef(np.array([profs[t]["daily_returns"] for t in ["AAPL", "MSFT", "NVDA"]]))
    pairs = [cm[0, 1], cm[0, 2], cm[1, 2]]
    tech_ok = all(0.3 <= x <= 0.8 for x in pairs)
    print(f"[QPM-001] last bar == price: {last_bar}  distinct prices: {distinct}  "
          f"tech corr 252d: {[round(float(x), 3) for x in pairs]} in [0.3, 0.8]: {tech_ok}")
    ok &= last_bar and distinct and tech_ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
