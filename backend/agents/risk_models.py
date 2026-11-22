"""
Phase 2 risk models (RSK-004 / RSK-005 / RSK-006). Pure functions over the mock price history.

All series are PRO-FORMA: today's holdings and today's cash replayed over the 504-day mock
history (NAV_t = cash + sum_i q_i * P_i,t). Nothing is fabricated; everything is derived from
mock_market_data.price_series_504d, which already contains the RSK-001 stress windows.

Sign convention: VaR and ES are reported as POSITIVE loss fractions of NAV (0.021 = 2.1%).
"""

import math
from statistics import NormalDist

import numpy as np

from agents.mock_market_data import (
    N_HISTORY_DAYS,
    _history_dates,
    get_deterministic_mock_profile,
    get_stress_windows,
)

_N = NormalDist()
EWMA_LAMBDA = 0.94
HIST_WINDOW = 500          # R-P0-5 "Historical (500d)"
BACKTEST_DAYS = 250        # R-P0-6
BACKTEST_WINDOW = 250      # rolling estimation window used inside the backtest (no lookahead)


# ---------------------------------------------------------------------------
# Pro-forma portfolio series
# ---------------------------------------------------------------------------
def proforma_series(raw_positions: list, cash: float) -> dict:
    dates = _history_dates(N_HISTORY_DAYS)
    tickers, qty, prices, betas, sectors = [], [], [], [], []
    for p in raw_positions:
        q = float(p["quantity"])
        if q == 0:
            continue
        prof = get_deterministic_mock_profile(p["ticker"])
        tickers.append(prof["ticker"])
        qty.append(q)
        prices.append(np.array(prof["price_series_504d"], dtype=float))
        betas.append(float(prof["beta"]))
        sectors.append(prof["sector"])
    n = N_HISTORY_DAYS
    if tickers:
        P = np.vstack(prices)                      # (k, 504)
        mv = (np.array(qty)[:, None] * P)          # (k, 504)
        invested = mv.sum(axis=0)
        beta_dollars = (np.array(betas)[:, None] * mv).sum(axis=0)
    else:
        P = np.zeros((0, n)); mv = np.zeros((0, n)); invested = np.zeros(n); beta_dollars = np.zeros(n)
    nav = cash + invested
    ret = nav[1:] / nav[:-1] - 1.0                 # (503,) return of day t vs t-1, belongs to dates[1:]
    asset_ret = (P[:, 1:] / P[:, :-1] - 1.0) if tickers else np.zeros((0, n - 1))
    return {
        "dates": dates, "nav": nav, "invested": invested, "beta_dollars": beta_dollars,
        "returns": ret, "tickers": tickers, "qty": qty, "betas": betas, "sectors": sectors,
        "asset_returns": asset_ret, "cash": cash,
    }


# ---------------------------------------------------------------------------
# VaR / ES estimators (single return vector -> positive loss fractions)
# ---------------------------------------------------------------------------
def _moments(r: np.ndarray):
    mu = float(r.mean())
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    x = r - mu
    m2 = float((x ** 2).mean())
    skew = float((x ** 3).mean() / m2 ** 1.5) if m2 > 0 else 0.0
    exk = float((x ** 4).mean() / m2 ** 2 - 3.0) if m2 > 0 else 0.0
    return mu, sd, skew, exk


def hist_var_es(r: np.ndarray, conf: float):
    q = float(np.quantile(r, 1.0 - conf))
    tail = r[r <= q]
    es = float(tail.mean()) if len(tail) else q
    return max(-q, 0.0), max(-es, 0.0)


def normal_var_es(sd: float, conf: float, mu: float = 0.0):
    z = _N.inv_cdf(1.0 - conf)                    # negative
    var = -(mu + z * sd)
    es = -(mu - sd * _N.pdf(z) / (1.0 - conf))
    return max(var, 0.0), max(es, 0.0)


def ewma_sigma(r: np.ndarray, lam: float = EWMA_LAMBDA) -> float:
    """RiskMetrics: sigma2_t = lam * sigma2_{t-1} + (1 - lam) * r_{t-1}^2, seeded with the first 20d variance."""
    if len(r) < 2:
        return 0.0
    s2 = float(np.var(r[:20])) if len(r) >= 20 else float(np.var(r))
    for x in r:
        s2 = lam * s2 + (1.0 - lam) * x * x
    return math.sqrt(s2)


def cf_quantile(p: float, skew: float, exk: float) -> float:
    z = _N.inv_cdf(p)
    return (z + (z * z - 1) * skew / 6.0 + (z ** 3 - 3 * z) * exk / 24.0
            - (2 * z ** 3 - 5 * z) * skew * skew / 36.0)


def cornish_fisher_var_es(sd: float, skew: float, exk: float, conf: float, mu: float = 0.0):
    p = 1.0 - conf
    var = -(mu + cf_quantile(p, skew, exk) * sd)
    # ES = average of the CF quantile over the tail p' in (0, p], midpoint rule on 400 slices
    grid = (np.arange(400) + 0.5) / 400.0 * p
    qs = np.array([cf_quantile(g, skew, exk) for g in grid])
    es = -(mu + float(qs.mean()) * sd)
    return max(var, 0.0), max(es, var, 0.0)


def var_methods(r: np.ndarray, conf: float, horizon: int = 1) -> dict:
    """All four methods at one confidence; horizon scaled by sqrt(h) (caveat in provenance)."""
    r = np.asarray(r, dtype=float)
    mu, sd, skew, exk = _moments(r)
    scale = math.sqrt(horizon)
    hv, he = hist_var_es(r, conf)
    nv, ne = normal_var_es(sd, conf)
    es_ = ewma_sigma(r)
    ev, ee = normal_var_es(es_, conf)
    cv, ce = cornish_fisher_var_es(sd, skew, exk, conf)
    out = {
        "historical": {"var": hv * scale, "es": he * scale, "window": f"{len(r)}d", "method": "empirical quantile; ES = mean of returns at or below it"},
        "parametric": {"var": nv * scale, "es": ne * scale, "window": f"{len(r)}d", "method": "normal, zero mean, sample sigma"},
        "ewma": {"var": ev * scale, "es": ee * scale, "window": f"{len(r)}d, lambda {EWMA_LAMBDA}", "method": "normal with RiskMetrics EWMA sigma"},
        "cornish_fisher": {"var": cv * scale, "es": ce * scale, "window": f"{len(r)}d", "method": "normal quantile adjusted for sample skew and excess kurtosis"},
    }
    return {"methods": out, "moments": {"mean": mu, "sd": sd, "skew": skew, "excess_kurtosis": exk, "ewma_sd": es_}}


# ---------------------------------------------------------------------------
# RSK-004: risk history, HWM, drawdown
# ---------------------------------------------------------------------------
def risk_history(raw_positions: list, cash: float, days: int = 252, var_window: int = 252) -> dict:
    s = proforma_series(raw_positions, cash)
    nav, dates, ret = s["nav"], s["dates"], s["returns"]
    n = len(nav)
    start = n - days
    rows = []
    hwm = -math.inf
    for t in range(start, n):
        hwm = max(hwm, float(nav[t]))
        # trailing window of returns strictly BEFORE day t (returns index t-1 is day t's own return)
        win = ret[max(0, t - 1 - var_window):t - 1]
        sd = float(win.std(ddof=1)) if len(win) > 1 else 0.0
        hv, he = hist_var_es(win, 0.95) if len(win) > 20 else (0.0, 0.0)
        _, he975 = hist_var_es(win, 0.975) if len(win) > 20 else (0.0, 0.0)
        pnl = float(nav[t] - nav[t - 1]) if t > 0 else 0.0
        rows.append({
            "date": dates[t],
            "nav": round(float(nav[t]), 2),
            "gross_pct": round(float(s["invested"][t] / nav[t] * 100.0), 4),
            "net_pct": round(float(s["invested"][t] / nav[t] * 100.0), 4),
            "beta": round(float(s["beta_dollars"][t] / nav[t]), 4),
            "vol_exante": round(sd * math.sqrt(252), 6),
            "var95": round(hv, 6),
            "es975": round(he975, 6),
            "var95_usd": round(hv * float(nav[t - 1]), 2),
            "pnl_usd": round(pnl, 2),
            "return": round(float(ret[t - 1]), 6) if t > 0 else 0.0,
            "hwm": round(hwm, 2),
            "drawdown": round(float(nav[t]) / hwm - 1.0, 6),
        })
    dd = [r["drawdown"] for r in rows]
    worst = int(np.argmin(dd)) if rows else 0
    windows = [w for w in get_stress_windows(N_HISTORY_DAYS) if w["start"] >= start or w["end"] >= start]
    return {
        "rows": rows,
        "summary": {
            "latest_nav": rows[-1]["nav"] if rows else None,
            "latest_hwm": rows[-1]["hwm"] if rows else None,
            "latest_drawdown": rows[-1]["drawdown"] if rows else None,
            "max_drawdown": rows[worst]["drawdown"] if rows else None,
            "max_drawdown_date": rows[worst]["date"] if rows else None,
            "days": len(rows),
        },
        "stress_windows": windows,
        "_provenance": {
            "basis": "pro-forma, current holdings",
            "source": "mock_engine price_series_504d",
            "window": f"{days}d history; VaR/vol from trailing {var_window}d returns ending the day before (no lookahead)",
            "as_of": dates[-1],
        },
    }


def current_drawdown(raw_positions: list, cash: float, days: int = 252):
    """(drawdown fraction <= 0, hwm, nav) on the latest date, for the RSK-002 drawdown limit."""
    s = proforma_series(raw_positions, cash)
    nav = s["nav"][-days:]
    hwm = float(np.max(nav))
    return float(nav[-1]) / hwm - 1.0, hwm, float(nav[-1])


# ---------------------------------------------------------------------------
# RSK-005: VaR / ES report
# ---------------------------------------------------------------------------
def var_report(raw_positions: list, cash: float, conf: float = 0.99, horizon: int = 1, window: int = HIST_WINDOW,
               extra_tickers: list = None) -> dict:
    s = proforma_series(raw_positions, cash)
    nav_now = float(s["nav"][-1])
    r = s["returns"][-window:]
    port = var_methods(r, conf, horizon)
    port97 = var_methods(r, 0.975, horizon)

    def fmt(m, nav):
        return {k: {**v, "var_usd": round(v["var"] * nav, 2), "es_usd": round(v["es"] * nav, 2),
                    "var": round(v["var"], 6), "es": round(v["es"], 6)} for k, v in m["methods"].items()}

    names = []
    seen = set()
    for t in list(s["tickers"]) + [x.strip().upper() for x in (extra_tickers or []) if x and x.strip()]:
        if t in seen:
            continue
        seen.add(t)
        prices = np.array(get_deterministic_mock_profile(t)["price_series_504d"], dtype=float)
        rr = (prices[1:] / prices[:-1] - 1.0)[-window:]
        m = var_methods(rr, conf, horizon)
        names.append({
            "ticker": t,
            "held": t in s["tickers"],
            "methods": {k: {"var": round(v["var"], 6), "es": round(v["es"], 6)} for k, v in m["methods"].items()},
            "moments": {k: round(v, 4) for k, v in m["moments"].items()},
            "cf_exceeds_normal": m["methods"]["cornish_fisher"]["var"] > m["methods"]["parametric"]["var"],
        })
    all_rows = [port["methods"]] + [n["methods"] for n in names]
    es_ge_var = all(v["es"] >= v["var"] - 1e-12 for rows in all_rows for v in rows.values())
    return {
        "confidence": conf, "horizon_days": horizon, "nav": round(nav_now, 2),
        "portfolio": {"methods": fmt(port, nav_now), "moments": {k: round(v, 6) for k, v in port["moments"].items()},
                      "es975": {k: round(v["es"], 6) for k, v in port97["methods"].items() if k in ("historical", "parametric")}},
        "positions": names,
        "checks": {
            "es_ge_var_everywhere": es_ge_var,
            "cf_var_gt_normal_var_count": sum(1 for n in names if n["cf_exceeds_normal"]),
            "names": len(names),
        },
        "_provenance": {
            "basis": "pro-forma, current holdings", "source": "mock_engine price_series_504d",
            "window": f"last {len(r)} daily returns", "as_of": s["dates"][-1],
            "horizon_caveat": (None if horizon == 1 else
                               f"{horizon}-day figures are 1-day x sqrt({horizon}); this assumes i.i.d. returns and "
                               "understates risk when volatility clusters (it does in this data)."),
        },
    }


# ---------------------------------------------------------------------------
# RSK-006: backtest, Kupiec POF, Christoffersen independence, Basel zone
# ---------------------------------------------------------------------------
def _chi2_1_sf(x: float) -> float:
    return math.erfc(math.sqrt(max(x, 0.0) / 2.0))


def _xlogy(x, y):
    return 0.0 if x == 0 else x * math.log(y)


def kupiec_pof(x: int, T: int, p: float) -> dict:
    phat = x / T if T else 0.0
    lr = -2.0 * (_xlogy(T - x, 1 - p) + _xlogy(x, p)) + 2.0 * (_xlogy(T - x, 1 - phat) + _xlogy(x, phat))
    return {"lr": round(lr, 4), "p_value": round(_chi2_1_sf(lr), 4), "critical_95": 3.841, "reject_95": lr > 3.841}


def christoffersen_ind(hits: list) -> dict:
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(hits[:-1], hits[1:]):
        if a == 0 and b == 0: n00 += 1
        elif a == 0 and b == 1: n01 += 1
        elif a == 1 and b == 0: n10 += 1
        else: n11 += 1
    pi0 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi1 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11) if (n00 + n01 + n10 + n11) else 0.0
    l0 = _xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
    l1 = _xlogy(n00, 1 - pi0) + _xlogy(n01, pi0) + _xlogy(n10, 1 - pi1) + _xlogy(n11, pi1)
    lr = -2.0 * (l0 - l1)
    return {"lr": round(lr, 4), "p_value": round(_chi2_1_sf(lr), 4), "reject_95": lr > 3.841,
            "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11}, "pi0": round(pi0, 4), "pi1": round(pi1, 4)}


def basel_zone(x: int) -> str:
    return "green" if x <= 4 else ("amber" if x <= 9 else "red")


def backtest_series(r: np.ndarray, dates: list, conf: float, test_days: int = BACKTEST_DAYS,
                    window: int = BACKTEST_WINDOW) -> dict:
    """
    For each of the last `test_days` returns r_t, forecast VaR from returns t-window..t-1 only,
    then count r_t < -VaR_t. dates[i] is the date of r[i].
    """
    r = np.asarray(r, dtype=float)
    n = len(r)
    first = n - test_days
    if first < window:
        raise ValueError("not enough history for a no-lookahead backtest")
    p = 1.0 - conf
    methods = ("historical", "parametric", "ewma", "cornish_fisher")
    forecasts = {m: [] for m in methods}
    for t in range(first, n):
        est = var_methods(r[t - window:t], conf)["methods"]
        for m in methods:
            forecasts[m].append(est[m]["var"])
    realised = r[first:]
    out = {}
    for m in methods:
        v = np.array(forecasts[m])
        hits = [int(x) for x in (realised < -v)]
        x = sum(hits)
        out[m] = {
            "exceptions": x, "expected": round(p * test_days, 2), "T": test_days,
            "exception_rate": round(x / test_days, 4),
            "kupiec": kupiec_pof(x, test_days, p),
            "christoffersen": christoffersen_ind(hits),
            "basel_zone": basel_zone(x) if abs(conf - 0.99) < 1e-9 else None,
            "series": [{"date": dates[first + i], "return": round(float(realised[i]), 6), "var": round(float(v[i]), 6),
                        "exception": bool(hits[i])} for i in range(test_days)],
        }
    return out


def gaussian_control(conf: float, seeds: int = 40, n: int = 503, sd: float = 0.01) -> dict:
    """
    Control experiment: i.i.d. normal returns, averaged over many seeds (a single seed is too noisy:
    with 2.5 expected exceptions, 0-7 is the normal spread). Used by scripts/verify_rsk_phase2.py.
    """
    acc = {}
    for seed in range(seeds):
        rng = np.random.RandomState(seed)
        r = rng.normal(0.0, sd, n)
        bt = backtest_series(r, [f"t{i}" for i in range(n)], conf)
        for m, res in bt.items():
            a = acc.setdefault(m, {"exceptions": [], "kupiec_rejects": 0})
            a["exceptions"].append(res["exceptions"])
            a["kupiec_rejects"] += int(res["kupiec"]["reject_95"])
    return {m: {"mean_exceptions": round(float(np.mean(a["exceptions"])), 2),
                "expected": round((1 - conf) * BACKTEST_DAYS, 2),
                "kupiec_reject_rate": round(a["kupiec_rejects"] / seeds, 3), "seeds": seeds} for m, a in acc.items()}
