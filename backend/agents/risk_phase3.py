"""
Phase 3 risk analytics (RSK-009 stress, RSK-010 liquidity, RSK-011 attribution). Pure functions, no DB.

Mock caveat: historical-crisis scenarios are expressed as APPROXIMATE S&P sector moves over each
window (rounded, illustrative) and factor sensitivities (rates/oil/USD) are an illustrative mock
table. The engine, not the numbers, is what this track validates; real data replaces them later.
"""

import math
from statistics import NormalDist

import numpy as np

from agents.mock_market_data import get_deterministic_mock_profile, get_stress_windows, N_HISTORY_DAYS, _history_dates
from agents.portfolio_engine import calculate_portfolio_holdings, ledoit_wolf_shrinkage
from agents.risk_models import proforma_series, hist_var_es, normal_var_es

_N = NormalDist()
SECTORS = ["Technology", "Healthcare", "Financials", "Consumer Discretionary", "Energy", "Industrials",
           "Communication Services", "Consumer Staples", "Utilities"]


def _sec(d):
    """Sector map helper: d gives the listed sectors; 'Index' (SPY) follows 'market'."""
    return d


# ---------------------------------------------------------------------------
# Built-in scenario library (seeded into stress_scenarios; editable copies allowed)
# shocks: {"market": x}                -> P&L_i = beta_i * x * MV_i
#         {"sectors": {...}, "market": x} -> P&L_i = sector move * MV_i (Index/unknown sectors use market)
#         {"tickers": {...}}             -> overrides for named tickers
# ---------------------------------------------------------------------------
BUILTIN_SCENARIOS = [
    # Historical replays (approximate sector moves over the stated window)
    {"key": "gfc_2008", "name": "GFC 2008 (2008-09-15 to 2008-11-20)", "kind": "historical",
     "shocks": {"market": -0.39, "sectors": _sec({"Technology": -0.37, "Healthcare": -0.25, "Financials": -0.50,
               "Consumer Discretionary": -0.40, "Energy": -0.38, "Industrials": -0.40, "Communication Services": -0.35,
               "Consumer Staples": -0.22, "Utilities": -0.28})}},
    {"key": "covid_2020", "name": "COVID crash (2020-02-19 to 2020-03-23)", "kind": "historical",
     "shocks": {"market": -0.34, "sectors": _sec({"Technology": -0.30, "Healthcare": -0.28, "Financials": -0.42,
               "Consumer Discretionary": -0.35, "Energy": -0.55, "Industrials": -0.42, "Communication Services": -0.30,
               "Consumer Staples": -0.24, "Utilities": -0.34})}},
    {"key": "rates_2022", "name": "2022 rates shock (2022-01-03 to 2022-10-12)", "kind": "historical",
     "shocks": {"market": -0.25, "sectors": _sec({"Technology": -0.32, "Healthcare": -0.13, "Financials": -0.22,
               "Consumer Discretionary": -0.38, "Energy": 0.40, "Industrials": -0.20, "Communication Services": -0.42,
               "Consumer Staples": -0.12, "Utilities": -0.08})}},
    {"key": "svb_2023", "name": "SVB banking stress (2023-03-08 to 2023-03-13)", "kind": "historical",
     "shocks": {"market": -0.035, "sectors": _sec({"Technology": -0.01, "Healthcare": -0.02, "Financials": -0.08,
               "Consumer Discretionary": -0.03, "Energy": -0.06, "Industrials": -0.04, "Communication Services": -0.01,
               "Consumer Staples": -0.02, "Utilities": -0.03})}},
    {"key": "yen_carry_2024", "name": "Yen-carry unwind (2024-07-31 to 2024-08-05)", "kind": "historical",
     "shocks": {"market": -0.06, "sectors": _sec({"Technology": -0.09, "Healthcare": -0.03, "Financials": -0.06,
               "Consumer Discretionary": -0.07, "Energy": -0.05, "Industrials": -0.06, "Communication Services": -0.07,
               "Consumer Staples": -0.02, "Utilities": -0.02})}},
    # Hypothetical market shocks via beta
    *[{"key": f"spx_{'up' if x > 0 else 'dn'}{abs(int(x * 100))}", "name": f"S&P 500 {x:+.0%}", "kind": "market",
       "shocks": {"market": x}} for x in (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20)],
    # Factor / sector shocks (illustrative sensitivities)
    {"key": "rates_up_100", "name": "Rates +100bp", "kind": "factor",
     "shocks": {"market": -0.04, "sectors": {"Technology": -0.08, "Healthcare": -0.03, "Financials": 0.03,
               "Consumer Discretionary": -0.06, "Energy": 0.01, "Industrials": -0.04, "Communication Services": -0.06,
               "Consumer Staples": -0.03, "Utilities": -0.05}}},
    {"key": "oil_up_30", "name": "Oil +30%", "kind": "factor",
     "shocks": {"market": -0.01, "sectors": {"Technology": -0.01, "Healthcare": -0.01, "Financials": 0.0,
               "Consumer Discretionary": -0.03, "Energy": 0.15, "Industrials": -0.02, "Communication Services": -0.01,
               "Consumer Staples": -0.01, "Utilities": -0.01}}},
    {"key": "oil_dn_30", "name": "Oil -30%", "kind": "factor",
     "shocks": {"market": -0.01, "sectors": {"Technology": 0.01, "Healthcare": 0.0, "Financials": -0.01,
               "Consumer Discretionary": 0.02, "Energy": -0.18, "Industrials": 0.01, "Communication Services": 0.0,
               "Consumer Staples": 0.01, "Utilities": 0.0}}},
    {"key": "usd_up_5", "name": "USD +5%", "kind": "factor",
     "shocks": {"market": -0.015, "sectors": {"Technology": -0.025, "Healthcare": -0.015, "Financials": 0.005,
               "Consumer Discretionary": -0.01, "Energy": -0.01, "Industrials": -0.02, "Communication Services": -0.015,
               "Consumer Staples": -0.015, "Utilities": 0.005}}},
    {"key": "tech_dn_25", "name": "Technology -25%, others flat", "kind": "sector",
     "shocks": {"market": 0.0, "sectors": {"Technology": -0.25, **{s: 0.0 for s in SECTORS if s != "Technology"}}}},
    # Volatility spikes: an all-long cash-equity book has no direct vega, so these restate risk, not P&L
    {"key": "vol_up_50", "name": "Volatility +50%", "kind": "volatility", "shocks": {"vol_mult": 1.5}},
    {"key": "vol_up_100", "name": "Volatility +100% (VIX ~40)", "kind": "volatility", "shocks": {"vol_mult": 2.0}},
]


def _book(raw_positions, cash):
    h = calculate_portfolio_holdings(raw_positions, cash)
    return h, h["positions"], h["nav"]


def position_shock(p: dict, shocks: dict) -> float:
    """Return the fractional price move a scenario applies to one position."""
    t = (shocks.get("tickers") or {}).get(p["ticker"])
    if t is not None:
        return float(t)
    secs = shocks.get("sectors")
    mkt = float(shocks.get("market", 0.0) or 0.0)
    if secs is not None:
        if p["sector"] in secs:
            return float(secs[p["sector"]])
        return mkt  # Index (SPY) or unmapped sector follows the market move
    return float(p.get("beta", 1.0)) * mkt


def run_scenario(raw_positions: list, cash: float, scenario: dict, limits: list = None, hwm: float = None) -> dict:
    from agents.risk_limits import compute_limit_metrics, evaluate_limits
    h, positions, nav = _book(raw_positions, cash)
    shocks = scenario.get("shocks") or {}
    out = {"key": scenario.get("key"), "id": scenario.get("id"), "name": scenario["name"], "kind": scenario.get("kind"),
           "shocks": shocks}

    if "vol_mult" in shocks:
        k = float(shocks["vol_mult"])
        s = proforma_series(raw_positions, cash)
        r = s["returns"][-252:]
        sd = float(np.std(r, ddof=1))
        v99, e99 = normal_var_es(sd * k, 0.99)
        b99, _ = normal_var_es(sd, 0.99)
        out.update({"pnl_usd": 0.0, "pnl_pct": 0.0, "worst_positions": [], "breaches_after": [],
                    "stressed_var99_pct": round(v99 * 100, 3), "base_var99_pct": round(b99 * 100, 3),
                    "stressed_es99_pct": round(e99 * 100, 3),
                    "note": "No direct P&L: the book holds only cash equities (no options/vega). Shown as parametric "
                            "VaR99 with daily volatility scaled by the shock."})
        return out

    rows = []
    for p in positions:
        x = position_shock(p, shocks)
        pnl = x * p["market_value"]
        rows.append({"ticker": p["ticker"], "sector": p["sector"], "shock_pct": round(x * 100, 2),
                     "market_value": p["market_value"], "pnl_usd": round(pnl, 2)})
    pnl = sum(r["pnl_usd"] for r in rows)
    out.update({
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl / nav * 100.0, 4) if nav > 0 else 0.0,
        "nav_after": round(nav + pnl, 2),
        "positions": rows,
        "worst_positions": sorted(rows, key=lambda r: r["pnl_usd"])[:5],
    })
    # beta approximation for comparison (acceptance: SPX -10% P&L ~= -10% x beta x NAV within 5%)
    if "market" in shocks:
        beta_p = sum(p["market_value"] * p["beta"] for p in positions) / nav if nav > 0 else 0.0
        out["beta_approx_pnl_usd"] = round(float(shocks["market"]) * beta_p * nav, 2)
        out["portfolio_beta"] = round(beta_p, 4)

    # limit status after the shock: same holdings repriced = quantities scaled by (1 + shock) at today's price
    if limits is not None:
        shocked = []
        for p, r in zip(positions, rows):
            q = p["quantity"] * (1.0 + r["shock_pct"] / 100.0)
            if q > 1e-9:
                shocked.append({"ticker": p["ticker"], "quantity": q, "avg_cost": p["avg_cost"], "side": "long"})
        m = compute_limit_metrics(shocked, cash)
        if hwm:
            m["values"]["drawdown_pct"] = max(0.0, -((nav + pnl) / hwm - 1.0) * 100.0)
        ev = evaluate_limits(limits, m)
        out["breaches_after"] = [
            {"metric": e["metric"], "label": e["label"], "value": e["value"], "unit": e["unit"], "status": e["status"],
             "scopes": [b["scope"] for b in e["breaching"]]}
            for e in ev if e["status"] in ("hard_breach", "soft_breach")]
    return out


def reverse_stress(raw_positions: list, cash: float, target_loss_pct: float, hwm: float = None,
                   drawdown_hard_pct: float = None) -> dict:
    """
    1) SPX move that loses target_loss_pct of NAV, solved via beta, then confirmed by full revaluation.
    2) Most plausible multi-asset shock with the same loss: x = -L * Sigma w / (w' Sigma w)
       (minimum Mahalanobis distance under the 252d Ledoit-Wolf covariance), aggregated by sector.
    3) If a drawdown hard limit is given, the extra loss that would breach it from the current HWM.
    """
    h, positions, nav = _book(raw_positions, cash)
    L = target_loss_pct / 100.0 * nav
    beta_dollars = sum(p["market_value"] * p["beta"] for p in positions)
    res = {"target_loss_pct": target_loss_pct, "target_loss_usd": round(L, 2), "nav": nav}
    if beta_dollars <= 0:
        res["spx_move_pct"] = None
        res["note"] = "Book has no positive beta exposure; no market move produces this loss."
    else:
        x = -L / beta_dollars
        res["spx_move_pct"] = round(x * 100, 3)
        res["reachable"] = x > -1.0
        full = run_scenario(raw_positions, cash, {"name": "reverse", "shocks": {"market": x}})
        res["confirm_full_revaluation_pnl_usd"] = full["pnl_usd"]
        res["round_trip_error_usd"] = round(full["pnl_usd"] + L, 6)

    # most plausible (Mahalanobis) shock
    s = proforma_series(raw_positions, cash)
    if s["tickers"]:
        R = s["asset_returns"][:, -252:].T
        cov, _, _ = ledoit_wolf_shrinkage(R)
        mv = np.array([q * get_deterministic_mock_profile(t)["current_price"] for t, q in zip(s["tickers"], s["qty"])])
        sig_w = cov @ mv
        denom = float(mv @ sig_w)
        shock = -L * sig_w / denom
        realised = float(mv @ shock)
        sigma_dist = math.sqrt(float(shock @ np.linalg.solve(cov, shock)))
        by_sector = {}
        for t, sec, m, x in zip(s["tickers"], s["sectors"], mv, shock):
            d = by_sector.setdefault(sec, {"mv": 0.0, "pnl": 0.0})
            d["mv"] += m; d["pnl"] += m * x
        res["most_plausible"] = {
            "per_ticker": [{"ticker": t, "shock_pct": round(float(x) * 100, 3)} for t, x in zip(s["tickers"], shock)],
            "per_sector": [{"sector": k, "shock_pct": round(v["pnl"] / v["mv"] * 100, 3)} for k, v in by_sector.items()],
            "pnl_usd": round(realised, 2),
            "mahalanobis_daily_sigmas": round(sigma_dist, 2),
            "method": "x = -L * Sigma w / (w' Sigma w); 252d Ledoit-Wolf covariance; shocks are total moves",
        }
    if hwm and drawdown_hard_pct is not None:
        extra = 1.0 - (1.0 - drawdown_hard_pct / 100.0) * hwm / nav
        res["drawdown_limit"] = {
            "hard_pct": drawdown_hard_pct, "hwm": round(hwm, 2),
            "current_drawdown_pct": round((nav / hwm - 1.0) * 100, 3),
            "extra_loss_to_breach_pct": round(extra * 100, 3),
            "spx_move_to_breach_pct": round(-extra * nav / beta_dollars * 100, 3) if beta_dollars > 0 else None,
        }
    return res


# ---------------------------------------------------------------------------
# RSK-010 liquidity
# ---------------------------------------------------------------------------
LADDER_DAYS = [1, 2, 3, 5, 10, 20]


def liquidity_risk(raw_positions: list, cash: float, participation: float = 0.20, confidence: float = 0.99,
                   impact_coeff: float = 1.0) -> dict:
    """
    DTL_i = qty / (participation x ADV20). Ladder = cumulative % NAV sellable by day d (cash at day 0).
    LVaR = VaR + sum(1/2 x spread x MV) + sum(market impact), impact_i = k x sigma_daily_i x sqrt(qty/ADV) x MV_i
    (square-root law, k = impact_coeff).
    """
    h, positions, nav = _book(raw_positions, cash)
    s = proforma_series(raw_positions, cash)
    rows = []
    spread_cost = impact_cost = 0.0
    for p in positions:
        prof = get_deterministic_mock_profile(p["ticker"])
        adv = float(prof["adv_20d_shares"])
        daily = participation * adv
        dtl = p["quantity"] / daily if daily > 0 else math.inf
        spread_bps = float(prof["bid_ask_spread_bps"])
        sig_d = float(prof["annualized_volatility"]) / math.sqrt(252)
        half_spread = 0.5 * spread_bps / 1e4 * p["market_value"]
        impact = impact_coeff * sig_d * math.sqrt(p["quantity"] / adv) * p["market_value"] if adv > 0 else 0.0
        spread_cost += half_spread
        impact_cost += impact
        rows.append({
            "ticker": p["ticker"], "sector": p["sector"], "quantity": p["quantity"], "market_value": p["market_value"],
            "adv_20d_shares": adv, "pct_of_adv": round(p["quantity"] / adv * 100, 4) if adv > 0 else None,
            "days_to_liquidate": round(dtl, 4), "flag_over_10pct_adv": (p["quantity"] / adv > 0.10) if adv > 0 else True,
            "spread_bps": spread_bps, "half_spread_cost_usd": round(half_spread, 2), "impact_cost_usd": round(impact, 2),
        })

    def sellable_by(d):
        v = max(cash, 0.0)
        for p, r in zip(positions, rows):
            frac = min(1.0, d / r["days_to_liquidate"]) if r["days_to_liquidate"] > 0 else 1.0
            v += frac * p["market_value"]
        return v

    ladder = [{"days": d, "cum_pct_nav": round(sellable_by(d) / nav * 100, 4) if nav > 0 else 100.0} for d in LADDER_DAYS]
    max_dtl = max([r["days_to_liquidate"] for r in rows], default=0.0)
    ladder.append({"days": "all", "cum_pct_nav": 100.0, "max_days_to_liquidate": round(max_dtl, 2)})
    cum = {l["days"]: l["cum_pct_nav"] for l in ladder}
    cash_pct = max(cash, 0.0) / nav * 100 if nav > 0 else 100.0
    bands = [
        {"band": "Cash", "pct_nav": round(cash_pct, 4)},
        {"band": "Within 1 day", "pct_nav": round(cum[1] - cash_pct, 4)},
        {"band": "2-3 days", "pct_nav": round(cum[3] - cum[1], 4)},
        {"band": "4-5 days", "pct_nav": round(cum[5] - cum[3], 4)},
        {"band": "Over 5 days", "pct_nav": round(100.0 - cum[5], 4)},
    ]

    r = s["returns"][-500:]
    lv = {}
    for conf in (0.95, 0.99):
        hv, _ = hist_var_es(r, conf)
        pv, _ = normal_var_es(float(np.std(r, ddof=1)), conf)
        for name, v in (("historical", hv), ("parametric", pv)):
            var_usd = v * nav
            lv[f"{name}_{int(conf * 100)}"] = {
                "var_usd": round(var_usd, 2), "spread_cost_usd": round(spread_cost, 2),
                "impact_cost_usd": round(impact_cost, 2),
                "lvar_usd": round(var_usd + spread_cost + impact_cost, 2),
                "lvar_pct": round((var_usd + spread_cost + impact_cost) / nav * 100, 4) if nav > 0 else 0.0,
                "var_pct": round(v * 100, 4),
            }
    return {
        "participation": participation, "nav": nav, "positions": rows, "ladder": ladder, "bands": bands,
        "lvar": lv,
        "checks": {
            "ladder_monotonic": all(b["cum_pct_nav"] >= a["cum_pct_nav"] - 1e-9 for a, b in zip(ladder, ladder[1:])),
            "ladder_reaches_100": abs(ladder[-1]["cum_pct_nav"] - 100.0) < 1e-6,
            "lvar_ge_var": all(v["lvar_usd"] >= v["var_usd"] for v in lv.values()),
        },
        "_provenance": {
            "basis": "current holdings; mock ADV20 and quoted spread", "as_of": s["dates"][-1],
            "method": f"DTL at {participation:.0%} ADV; LVaR = VaR + 1/2 spread x MV + {impact_coeff:g} x sigma_daily x "
                      "sqrt(qty/ADV) x MV (square-root impact); VaR from last 500 pro-forma returns",
        },
    }


# ---------------------------------------------------------------------------
# RSK-011 attribution + correlation regime
# ---------------------------------------------------------------------------
def risk_attribution(raw_positions: list, cash: float, confidence: float = 0.99, window: int = 252,
                     spike_threshold: float = 0.15) -> dict:
    h, positions, nav = _book(raw_positions, cash)
    s = proforma_series(raw_positions, cash)
    tickers = s["tickers"]
    if not tickers:
        return {"positions": [], "note": "No positions"}
    R = s["asset_returns"][:, -window:].T                 # (window, k)
    cov, delta, _ = ledoit_wolf_shrinkage(R)
    mv = np.array([q * get_deterministic_mock_profile(t)["current_price"] for t, q in zip(tickers, s["qty"])])
    z = -_N.inv_cdf(1.0 - confidence)                     # positive, e.g. 2.326
    sig_usd = math.sqrt(float(mv @ cov @ mv))             # daily $ sigma
    var_usd = z * sig_usd
    mvar = z * (cov @ mv) / sig_usd                       # dVaR/d$ for each position
    cvar = mv * mvar                                      # Euler: sum(cvar) == var_usd
    vols = np.sqrt(np.diag(cov))
    div_ratio = float((mv * vols).sum() / sig_usd)
    rows = []
    for i, t in enumerate(tickers):
        rows.append({
            "ticker": t, "sector": s["sectors"][i], "market_value": round(float(mv[i]), 2),
            "weight_pct": round(float(mv[i] / nav * 100), 3),
            "marginal_var": round(float(mvar[i]), 6),
            "component_var_usd": round(float(cvar[i]), 2),
            "pct_contribution": round(float(cvar[i] / var_usd * 100), 4),
            "var_change_if_cut_1pct_usd": round(float(-0.01 * cvar[i]), 2),
            "standalone_var_usd": round(float(z * vols[i] * mv[i]), 2),
        })

    corr = None
    if len(tickers) >= 2:
        A = s["asset_returns"]                            # (k, 503)
        dates = s["dates"][1:]
        iu = np.triu_indices(len(tickers), 1)
        series = []
        n = A.shape[1]
        for t in range(n - 252, n):
            c60 = float(np.corrcoef(A[:, t - 59:t + 1])[iu].mean())
            c252 = float(np.corrcoef(A[:, t - 251:t + 1])[iu].mean())
            series.append({"date": dates[t], "corr_60d": round(c60, 4), "corr_252d": round(c252, 4),
                           "spread": round(c60 - c252, 4), "spike": (c60 - c252) > spike_threshold})
        windows = get_stress_windows(N_HISTORY_DAYS)
        mask = np.zeros(n, dtype=bool)
        for w in windows:
            mask[max(0, w["start"] - 1):w["end"]] = True   # returns index = day index - 1
        calm = np.corrcoef(A[:, ~mask]); stress = np.corrcoef(A[:, mask])
        flagged = [r["date"] for r in series if r["spike"]]
        in_window = [d for d in flagged if any(w["start_date"] <= d <= w["end_date"] for w in windows)]
        corr = {
            "threshold": spike_threshold, "latest": series[-1], "series": series,
            "flagged_dates": flagged, "flagged_inside_stress_windows": in_window,
            "stress_windows": windows,
            "calm_matrix": {"tickers": tickers, "matrix": np.round(calm, 3).tolist(), "avg": round(float(calm[iu].mean()), 4)},
            "stress_matrix": {"tickers": tickers, "matrix": np.round(stress, 3).tolist(), "avg": round(float(stress[iu].mean()), 4)},
        }
    return {
        "confidence": confidence, "nav": nav, "var_usd": round(var_usd, 2), "var_pct": round(var_usd / nav * 100, 4),
        "sum_component_var_usd": round(float(cvar.sum()), 2),
        "diversification_ratio": round(div_ratio, 4),
        "positions": rows,
        "correlation": corr,
        "_provenance": {
            "basis": "current holdings", "window": f"{window}d", "as_of": s["dates"][-1],
            "method": "parametric Euler decomposition on the 252d Ledoit-Wolf covariance (same as the QPM Risk tab): "
                      "MVaR_i = z (Sigma w)_i / sigma_p, CVaR_i = w_i MVaR_i, sum CVaR = VaR. "
                      "Diversification ratio = sum(w_i sigma_i) / sigma_p.",
            "shrinkage": round(delta, 4),
        },
    }
