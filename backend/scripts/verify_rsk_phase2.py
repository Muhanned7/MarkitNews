"""
RSK-004/005/006 verification (no database). Run from backend/:  python3 scripts/verify_rsk_phase2.py
Uses the seeded book (AAPL 80, MSFT 45, NVDA 100, cash 100,000) unless --tickers/qty are edited below.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.risk_models import (  # noqa: E402
    backtest_series, gaussian_control, proforma_series, risk_history, var_report,
)

BOOK = [{"ticker": "AAPL", "quantity": 80}, {"ticker": "MSFT", "quantity": 45}, {"ticker": "NVDA", "quantity": 100}]
CASH = 100000.0
NAMES = ["TSLA", "JPM", "XOM", "GOOGL", "AMZN", "SPY", "IBM", "KO", "PFE", "INTC", "AMD", "META"]


def main() -> int:
    ok = True
    h = risk_history(BOOK, CASH)
    rows = h["rows"]
    dd_ok = all(r["drawdown"] <= 0 for r in rows)
    hwm_ok = all(b["hwm"] >= a["hwm"] for a, b in zip(rows, rows[1:]))
    last = rows[-1]
    last_ok = abs(last["nav"] / last["hwm"] - 1 - last["drawdown"]) < 1e-5
    print(f"[RSK-004] {len(rows)}d  drawdown<=0: {dd_ok}  HWM non-decreasing: {hwm_ok}  "
          f"latest dd {last['drawdown']:.4%} == nav/hwm-1: {last_ok}  max dd {h['summary']['max_drawdown']:.2%} on {h['summary']['max_drawdown_date']}")
    ok &= dd_ok and hwm_ok and last_ok

    for conf in (0.95, 0.99):
        for hz in (1, 10):
            v = var_report(BOOK, CASH, conf, hz, extra_tickers=NAMES)
            c = v["checks"]
            print(f"[RSK-005] conf {conf} h{hz}: ES>=VaR everywhere: {c['es_ge_var_everywhere']}  "
                  f"CF VaR > normal VaR: {c['cf_var_gt_normal_var_count']}/{c['names']}")
            ok &= c["es_ge_var_everywhere"]
            if conf == 0.99:
                ok &= c["cf_var_gt_normal_var_count"] > c["names"] / 2

    s = proforma_series(BOOK, CASH)
    bt = backtest_series(s["returns"], s["dates"][1:], 0.99)
    ex = {m: r["exceptions"] for m, r in bt.items()}
    print(f"[RSK-006] 99% exceptions (expected 2.5): {ex}  zones: { {m: r['basel_zone'] for m, r in bt.items()} }")
    more = ex["parametric"] > ex["historical"] and ex["parametric"] > ex["cornish_fisher"]
    print(f"          parametric-normal has more exceptions than historical and Cornish-Fisher: {more}")
    ok &= more
    ctrl = gaussian_control(0.99)
    print(f"[RSK-006] Gaussian control (40 seeds) mean exceptions vs 2.5: "
          f"{ {m: r['mean_exceptions'] for m, r in ctrl.items()} }  Kupiec reject rate: "
          f"{ {m: r['kupiec_reject_rate'] for m, r in ctrl.items()} }")
    ok &= abs(ctrl["parametric"]["mean_exceptions"] - 2.5) < 1.0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
