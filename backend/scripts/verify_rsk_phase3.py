"""
RSK-009/010/011 verification (no database). Run from backend/:  python3 scripts/verify_rsk_phase3.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# These checks never touch the database; stub the pool so the script runs without Postgres.
import types  # noqa: E402
_db = types.ModuleType("agents.db")
_db.query = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("DB not used by this script"))
sys.modules["agents.db"] = _db
from agents.mock_market_data import get_deterministic_mock_profile  # noqa: E402
from agents.risk_limits import DEFAULT_LIMITS  # noqa: E402
from agents.risk_models import current_drawdown  # noqa: E402
from agents.risk_phase3 import BUILTIN_SCENARIOS, liquidity_risk, reverse_stress, risk_attribution, run_scenario  # noqa: E402

SEEDED = [{"ticker": "AAPL", "quantity": 80, "avg_cost": 215}, {"ticker": "MSFT", "quantity": 45, "avg_cost": 410},
          {"ticker": "NVDA", "quantity": 100, "avg_cost": 125}]
CASH = 100000.0
LIMITS = [dict(metric=m, soft_limit=s, hard_limit=h, soft_limit_low=sl, hard_limit_low=hl, direction=d, unit=u, active=True)
          for m, _, u, d, s, h, sl, hl, _ in DEFAULT_LIMITS]


def main() -> int:
    ok = True
    _dd, hwm, nav = current_drawdown(SEEDED, CASH)
    spx = next(sc for sc in BUILTIN_SCENARIOS if sc["key"] == "spx_dn10")
    r = run_scenario(SEEDED, CASH, spx, LIMITS, hwm)
    rel = abs(r["pnl_usd"] - r["beta_approx_pnl_usd"]) / abs(r["beta_approx_pnl_usd"])
    print(f"[RSK-009] SPX -10%: full revaluation {r['pnl_usd']:.2f} vs -10% x beta {r['portfolio_beta']} x NAV "
          f"{r['beta_approx_pnl_usd']:.2f} -> rel diff {rel:.4%} (<5%: {rel < 0.05})")
    ok &= rel < 0.05
    for target in (5.0, 10.0, 20.0):
        rv = reverse_stress(SEEDED, CASH, target, hwm, 12.0)
        mp = rv["most_plausible"]["pnl_usd"]
        rt = abs(rv["round_trip_error_usd"]) < 0.05 and abs(mp + rv["target_loss_usd"]) < 0.05
        print(f"[RSK-009] reverse {target:>4}% NAV: SPX {rv['spx_move_pct']}%  full-reval {rv['confirm_full_revaluation_pnl_usd']} "
              f"vs target -{rv['target_loss_usd']}  most-plausible {mp}  round-trips: {rt}")
        ok &= rt
    n = len(BUILTIN_SCENARIOS)
    res = [run_scenario(SEEDED, CASH, sc, LIMITS, hwm) for sc in BUILTIN_SCENARIOS]
    print(f"[RSK-009] {n} built-in scenarios ran; worst: {min((x for x in res if 'pnl_usd' in x), key=lambda x: x['pnl_usd'])['name']}")

    # liquidity: seeded book is tiny vs ADV, so also test a large book holding 3x a day's 20% participation
    lows = sorted(["ZM", "ROKU", "SNOW", "PLTR", "SHOP", "SQ"], key=lambda t: get_deterministic_mock_profile(t)["adv_20d_shares"])
    big = [{"ticker": t, "quantity": round(k * 0.2 * get_deterministic_mock_profile(t)["adv_20d_shares"]), "avg_cost": 100.0}
           for t, k in zip(lows[:3], (0.5, 3.0, 12.0))]
    for label, book, cash in (("seeded", SEEDED, CASH), ("large", big, 5_000_000.0)):
        L = liquidity_risk(book, cash)
        print(f"[RSK-010] {label}: ladder {[(l['days'], round(l['cum_pct_nav'], 1)) for l in L['ladder']]}  checks {L['checks']}")
        ok &= all(L["checks"].values())
    L = liquidity_risk(big, 5_000_000.0)
    print(f"          large-book DTL {[(p['ticker'], p['days_to_liquidate']) for p in L['positions']]}  "
          f"flags >10% ADV {[p['ticker'] for p in L['positions'] if p['flag_over_10pct_adv']]}")

    for conf in (0.95, 0.99):
        A = risk_attribution(SEEDED, CASH, conf)
        sums = abs(A["sum_component_var_usd"] - A["var_usd"]) < 0.02 and abs(sum(p["pct_contribution"] for p in A["positions"]) - 100) < 0.01
        print(f"[RSK-011] conf {conf}: VaR {A['var_usd']} = sum CVaR {A['sum_component_var_usd']}  %RC sum "
              f"{sum(p['pct_contribution'] for p in A['positions']):.4f}  -> {sums}  DR {A['diversification_ratio']}")
        ok &= sums
    c = A["correlation"]
    fires = len(c["flagged_inside_stress_windows"]) > 0
    print(f"[RSK-011] correlation spike flagged on {len(c['flagged_dates'])} days; inside injected stress window: "
          f"{c['flagged_inside_stress_windows']} -> {fires}; calm avg {c['calm_matrix']['avg']} vs stress avg {c['stress_matrix']['avg']}")
    ok &= fires
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
