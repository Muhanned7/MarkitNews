"""
RSK-002 / RSK-003: risk limits framework, breach lifecycle and pre-trade what-if.

All numbers are computed in code from the existing QPM engine
(calculate_portfolio_holdings / calculate_portfolio_risk); nothing here is LLM-generated.

Units: every percentage limit is stored and reported in percent of NAV (e.g. 30 = 30%).
Portfolio beta is unitless. VaR / ES / drawdown are reported as positive loss magnitudes.

Limit directions:
  max  - breach when value > limit                utilisation = value / hard
  min  - breach when value < limit (liquidity)    utilisation = (100 - value) / (100 - hard)  [share of the allowed illiquid buffer used]
  band - breach when value outside [low, high]    utilisation = max(value / hard_high, hard_low / value)
Utilisation bands: green < 80%, amber 80-100%, red > 100%.
"""

import math
from datetime import datetime

from agents.portfolio_engine import calculate_portfolio_holdings, calculate_portfolio_risk
from agents.mock_market_data import get_deterministic_mock_profile

LIQUIDITY_PARTICIPATION = 0.20   # fraction of ADV we can trade per day
LIQUIDITY_HORIZON_DAYS = 5
UTIL_TOLERANCE = 0.01            # utilisation points; below this a change is "no change"

DEFAULT_LIMITS = [
    # metric, label, unit, direction, soft, hard, soft_low, hard_low, scope_type
    ("gross_exposure_pct", "Gross exposure", "% NAV", "max", 95.0, 100.0, None, None, "portfolio"),
    ("net_exposure_pct", "Net exposure", "% NAV", "max", 90.0, 100.0, None, None, "portfolio"),
    ("single_name_weight_pct", "Single-name weight", "% NAV", "max", 7.0, 8.0, None, None, "ticker"),
    ("sector_weight_pct", "Sector weight", "% NAV", "max", 27.0, 30.0, None, None, "sector"),
    ("portfolio_beta", "Portfolio beta", "beta", "band", 1.2, 1.3, 0.6, 0.5, "portfolio"),
    ("ex_ante_vol_pct", "Ex-ante volatility (ann.)", "%", "max", 14.0, 16.0, None, None, "portfolio"),
    ("var95_1d_pct", "VaR 95% 1-day", "% NAV", "max", 1.6, 2.0, None, None, "portfolio"),
    ("es975_1d_pct", "ES 97.5% 1-day", "% NAV", "max", 2.4, 3.0, None, None, "portfolio"),
    ("drawdown_pct", "Drawdown from HWM", "% NAV", "max", 8.0, 12.0, None, None, "portfolio"),
    ("top_risk_contributor_pct", "Top single risk contributor", "% of risk", "max", 30.0, 40.0, None, None, "ticker"),
    ("liquidity_5d_pct", "NAV liquidatable in 5 days (20% ADV)", "% NAV", "min", 90.0, 80.0, None, None, "portfolio"),
]
DEFAULTS_BY_METRIC = {d[0]: d for d in DEFAULT_LIMITS}
METRIC_ORDER = [d[0] for d in DEFAULT_LIMITS]

# ---------------------------------------------------------------------------
# Schema (created lazily so the feature works without a manual migration step;
# scripts/migrate_rsk.py runs the same DDL explicitly)
# ---------------------------------------------------------------------------
RISK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS risk_limits (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    metric VARCHAR(50) NOT NULL,
    soft_limit NUMERIC(12, 4),
    hard_limit NUMERIC(12, 4),
    soft_limit_low NUMERIC(12, 4),
    hard_limit_low NUMERIC(12, 4),
    direction VARCHAR(10) NOT NULL DEFAULT 'max',
    unit VARCHAR(20),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by VARCHAR(100) DEFAULT 'system',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_risk_limits_portfolio_metric UNIQUE (portfolio_id, metric)
);
CREATE INDEX IF NOT EXISTS idx_risk_limits_portfolio ON risk_limits(portfolio_id);

CREATE TABLE IF NOT EXISTS risk_limit_audit (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    metric VARCHAR(50) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    reason TEXT,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_risk_limit_audit_portfolio ON risk_limit_audit(portfolio_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS limit_breaches (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    metric VARCHAR(50) NOT NULL,
    scope VARCHAR(100) NOT NULL DEFAULT '',
    value NUMERIC(14, 4),
    limit_value NUMERIC(14, 4),
    severity VARCHAR(10) NOT NULL,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    owner VARCHAR(100),
    comment TEXT,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_limit_breaches_portfolio_status ON limit_breaches(portfolio_id, status);

CREATE TABLE IF NOT EXISTS limit_overrides (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    transaction_id INTEGER,
    ticker VARCHAR(10) NOT NULL,
    qty NUMERIC(15, 4) NOT NULL,
    price NUMERIC(15, 4) NOT NULL,
    breaches JSONB NOT NULL,
    reason TEXT NOT NULL,
    overridden_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_limit_overrides_portfolio ON limit_overrides(portfolio_id, created_at DESC);

CREATE TABLE IF NOT EXISTS portfolio_risk_history (
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    nav NUMERIC(16, 2),
    gross NUMERIC(10, 4),
    net NUMERIC(10, 4),
    beta NUMERIC(10, 4),
    vol_exante NUMERIC(10, 6),
    var95 NUMERIC(10, 6),
    es975 NUMERIC(10, 6),
    pnl NUMERIC(16, 2),
    hwm NUMERIC(16, 2),
    drawdown NUMERIC(10, 6),
    basis VARCHAR(40) NOT NULL DEFAULT 'pro-forma, current holdings',
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (portfolio_id, date)
);

CREATE TABLE IF NOT EXISTS stress_scenarios (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
    key VARCHAR(60),
    name VARCHAR(120) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'custom',
    description TEXT,
    shocks JSONB NOT NULL,
    built_in BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stress_scenarios_builtin_key ON stress_scenarios(key) WHERE built_in;

CREATE TABLE IF NOT EXISTS agent_model_risk_controls (
    agent_name VARCHAR(50) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    kill_switch BOOLEAN NOT NULL DEFAULT FALSE,
    forced_degraded BOOLEAN NOT NULL DEFAULT FALSE,
    min_quality_threshold NUMERIC(6, 3) NOT NULL DEFAULT 0.70,
    reason TEXT,
    updated_by VARCHAR(100) DEFAULT 'system',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_audit_log (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    target VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    details JSONB,
    actor VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_risk_audit_log_created ON risk_audit_log(created_at DESC);
"""


def _f(x):
    return None if x is None else float(x)


def _r(x, nd=2):
    return None if x is None else round(float(x), nd)


# ---------------------------------------------------------------------------
# Metric computation (pure functions, no DB)
# ---------------------------------------------------------------------------
def _drawdown_pct(raw_positions, cash):
    """Positive magnitude of the current drawdown from the 252d pro-forma high-water mark (RSK-004)."""
    if not raw_positions:
        return 0.0
    from agents.risk_models import current_drawdown
    dd, _hwm, _nav = current_drawdown(raw_positions, cash)
    return -dd * 100.0


def compute_limit_metrics(raw_positions: list, cash: float, benchmark: str = "SPY") -> dict:
    """
    Current value of every limit metric for a book, plus per-entity breakdowns
    for the scoped limits (single name, sector, top risk contributor).
    """
    holdings = calculate_portfolio_holdings(raw_positions, cash)
    positions = holdings["positions"]
    nav = holdings["nav"]
    risk = calculate_portfolio_risk(positions, cash, benchmark) if positions else None

    by_ticker = {p["ticker"]: p["weight_pct"] for p in positions}
    by_sector = dict(holdings["sector_breakdown"])
    rc = {x["ticker"]: x["risk_contribution_pct"] for x in (risk or {}).get("risk_contributions", [])}

    # 5-day liquidity: cash is liquid; each position can sell/cover 20% of ADV per day
    liquid_value = max(cash, 0.0)
    liquidity_detail = {}
    for p in positions:
        prof = get_deterministic_mock_profile(p["ticker"])
        adv = float(prof["adv_20d_shares"])
        daily_shares = LIQUIDITY_PARTICIPATION * adv
        days = (abs(p["quantity"]) / daily_shares) if daily_shares > 0 else math.inf
        sellable = min(abs(p["market_value"]), LIQUIDITY_HORIZON_DAYS * daily_shares * p["current_price"])
        if p["market_value"] >= 0:
            liquid_value += sellable
        else:
            # Unliquidated tail of a short hedge reduces liquid NAV
            unliquidated_short = max(0.0, abs(p["market_value"]) - sellable)
            liquid_value -= unliquidated_short
        liquidity_detail[p["ticker"]] = round(days, 4)
    liquidity_pct = min(100.0, (liquid_value / nav * 100.0)) if nav > 0 else 100.0

    values = {
        "gross_exposure_pct": holdings["gross_exposure_pct"],
        "net_exposure_pct": holdings["net_exposure_pct"],
        "single_name_weight_pct": max(by_ticker.values()) if by_ticker else 0.0,
        "sector_weight_pct": max(by_sector.values()) if by_sector else 0.0,
        # unrounded sum(w_i * beta_i); the QPM engine's portfolio_beta is rounded to 2 dp,
        # which would let a 0.4996 beta pass a 0.50 floor
        "portfolio_beta": (sum(p["market_value"] * p["beta"] for p in positions) / nav) if (positions and nav > 0) else 0.0,
        "ex_ante_vol_pct": risk["portfolio_volatility"] * 100.0 if risk else 0.0,
        "var95_1d_pct": abs(risk["var_95_1d"]) * 100.0 if risk else 0.0,
        "es975_1d_pct": abs(risk["cvar_975_1d"]) * 100.0 if risk else 0.0,
        "drawdown_pct": _drawdown_pct(raw_positions, cash),  # RSK-004: pro-forma 252d HWM
        "top_risk_contributor_pct": max(rc.values()) if rc else 0.0,
        "liquidity_5d_pct": liquidity_pct,
    }
    entities = {
        "single_name_weight_pct": by_ticker,
        "sector_weight_pct": by_sector,
        "top_risk_contributor_pct": rc,
    }
    return {
        "nav": nav,
        "cash": holdings["cash"],
        "values": values,
        "entities": entities,
        "days_to_liquidate": liquidity_detail,
    }


def _status_and_util(direction, value, soft, hard, soft_low=None, hard_low=None):
    if value is None or hard is None:
        return "na", None
    if direction == "min":
        # floor on a 0-100% quantity: utilisation = share of the allowed shortfall (100 - hard) used up
        if hard < 100.0:
            util = max(0.0, (100.0 - value) / (100.0 - hard) * 100.0)
        else:
            util = (hard / value * 100.0) if value > 0 else math.inf
        if value < hard:
            return "hard_breach", util
        if soft is not None and value < soft:
            return "soft_breach", util
        return "ok", util
    if direction == "band":
        lo = hard_low if hard_low is not None else -math.inf
        util_hi = value / hard * 100.0 if hard else 0.0
        util_lo = (hard_low / value * 100.0) if (hard_low and value > 0) else (math.inf if hard_low and value <= 0 else 0.0)
        util = max(util_hi, util_lo)
        if value > hard or value < lo:
            return "hard_breach", util
        if (soft is not None and value > soft) or (soft_low is not None and value < soft_low):
            return "soft_breach", util
        return "ok", util
    # max
    util = (value / hard * 100.0) if hard else math.inf
    if value > hard:
        return "hard_breach", util
    if soft is not None and value > soft:
        return "soft_breach", util
    return "ok", util


def _band(util, status=None):
    """Colour band from utilisation, never better than the soft/hard status implies."""
    if util is None:
        return "na"
    if status == "hard_breach" or util > 100.0:
        return "red"
    if status == "soft_breach" or util >= 80.0:
        return "amber"
    return "green"


def evaluate_limits(limits: list, metrics: dict) -> list:
    """
    limits: list of dicts with metric/soft_limit/hard_limit/soft_limit_low/hard_limit_low/direction/unit/active.
    Returns one row per limit with value, utilisation, status, band and the breaching entities.
    """
    rows = []
    by_metric = {l["metric"]: l for l in limits}
    for metric in METRIC_ORDER + [m for m in by_metric if m not in METRIC_ORDER]:
        lim = by_metric.get(metric)
        if not lim:
            continue
        d = DEFAULTS_BY_METRIC.get(metric)
        direction = lim.get("direction") or (d[3] if d else "max")
        soft, hard = _f(lim.get("soft_limit")), _f(lim.get("hard_limit"))
        soft_low, hard_low = _f(lim.get("soft_limit_low")), _f(lim.get("hard_limit_low"))
        value = metrics["values"].get(metric)
        status, util = _status_and_util(direction, value, soft, hard, soft_low, hard_low)
        if not lim.get("active", True):
            status = "inactive"

        breaching = []
        ent = metrics["entities"].get(metric)
        if ent and lim.get("active", True):
            for name, v in sorted(ent.items(), key=lambda kv: -kv[1]):
                s, u = _status_and_util(direction, v, soft, hard, soft_low, hard_low)
                if s in ("soft_breach", "hard_breach"):
                    breaching.append({"scope": name, "value": _r(v), "status": s, "utilisation_pct": _r(u, 1)})

        note = None
        if metric == "drawdown_pct":
            note = ("n/a - needs RSK-004 risk history (high-water mark)" if value is None
                    else "loss from 252d pro-forma high-water mark (current holdings)")
        rows.append({
            "metric": metric,
            "label": d[1] if d else metric,
            "unit": lim.get("unit") or (d[2] if d else ""),
            "direction": direction,
            "scope_type": d[8] if d else "portfolio",
            "value": _r(value, 4 if metric == "portfolio_beta" else 2),
            "soft_limit": soft,
            "hard_limit": hard,
            "soft_limit_low": soft_low,
            "hard_limit_low": hard_low,
            "utilisation_pct": None if util is None or math.isinf(util) else round(util, 1),
            "band": "na" if status in ("na", "inactive") else _band(util, status),
            "status": status,
            "active": bool(lim.get("active", True)),
            "breaching": breaching,
            "note": note,
            "updated_by": lim.get("updated_by"),
            "updated_at": str(lim["updated_at"]) if lim.get("updated_at") else None,
        })
    return rows


def breach_items(rows: list) -> list:
    """Flatten evaluated rows into (metric, scope) breach items for the breach log."""
    items = []
    for r in rows:
        if r["status"] in ("na", "inactive"):
            continue
        if r["scope_type"] != "portfolio":
            for b in r["breaching"]:
                limit_value = r["hard_limit"] if b["status"] == "hard_breach" else r["soft_limit"]
                items.append({"metric": r["metric"], "scope": b["scope"], "value": b["value"],
                              "limit_value": limit_value, "severity": "hard" if b["status"] == "hard_breach" else "soft"})
        elif r["status"] in ("soft_breach", "hard_breach"):
            hard = r["status"] == "hard_breach"
            if r["direction"] == "band" and r["value"] is not None and r["hard_limit_low"] is not None and r["value"] < (r["hard_limit_low"] if hard else (r["soft_limit_low"] or -math.inf)):
                limit_value = r["hard_limit_low"] if hard else r["soft_limit_low"]
            else:
                limit_value = r["hard_limit"] if hard else r["soft_limit"]
            items.append({"metric": r["metric"], "scope": "", "value": r["value"],
                          "limit_value": limit_value, "severity": "hard" if hard else "soft"})
    return items


def what_if(raw_positions: list, cash: float, limits: list, ticker: str, qty: float, price: float,
            fees: float = 0.0, benchmark: str = "SPY") -> dict:
    """
    Before/after value of every limit for a proposed trade (qty > 0 buy, qty < 0 sell).
    A trade is *blocking* if it creates a new hard breach or worsens an existing one
    (for scoped limits, judged per entity: e.g. the Technology sector, not just the max).
    """
    clean = ticker.strip().upper()
    before_m = compute_limit_metrics(raw_positions, cash, benchmark)
    before = evaluate_limits(limits, before_m)

    after_positions = []
    found = False
    for p in raw_positions:
        q = float(p["quantity"])
        if p["ticker"].strip().upper() == clean:
            found = True
            q_new = q + qty
            if q_new < -1e-9:
                raise ValueError(f"Cannot sell {abs(qty)} shares of {clean}: only {q} held")
            if q_new > 1e-9:
                avg = float(p["avg_cost"]) if qty < 0 else (q * float(p["avg_cost"]) + qty * price) / q_new
                after_positions.append({**p, "quantity": q_new, "avg_cost": avg})
        else:
            after_positions.append(p)
    if not found:
        if qty < 0:
            raise ValueError(f"Cannot sell {abs(qty)} shares of {clean}: no open position")
        after_positions.append({"ticker": clean, "quantity": qty, "avg_cost": price, "side": "long"})
    after_cash = cash - qty * price - (fees or 0.0)
    after_m = compute_limit_metrics(after_positions, after_cash, benchmark)
    after = evaluate_limits(limits, after_m)

    rows = []
    blocking = []
    after_by_metric = {r["metric"]: r for r in after}
    for b in before:
        a = after_by_metric[b["metric"]]
        row = {
            "metric": b["metric"], "label": b["label"], "unit": b["unit"], "direction": b["direction"],
            "soft_limit": b["soft_limit"], "hard_limit": b["hard_limit"],
            "soft_limit_low": b["soft_limit_low"], "hard_limit_low": b["hard_limit_low"],
            "before": b["value"], "after": a["value"],
            "before_status": b["status"], "after_status": a["status"],
            "before_utilisation_pct": b["utilisation_pct"], "after_utilisation_pct": a["utilisation_pct"],
            "note": a["note"], "entities": [],
        }
        if b["scope_type"] != "portfolio":
            ent_b = before_m["entities"][b["metric"]]
            ent_a = after_m["entities"][b["metric"]]
            for name in sorted(set(ent_b) | set(ent_a)):
                vb, va = ent_b.get(name, 0.0), ent_a.get(name, 0.0)
                sb, ub = _status_and_util(b["direction"], vb, b["soft_limit"], b["hard_limit"])
                sa, ua = _status_and_util(b["direction"], va, b["soft_limit"], b["hard_limit"])
                if sa != "ok" or sb != "ok" or name == clean or (b["metric"] == "sector_weight_pct" and name == get_deterministic_mock_profile(clean)["sector"]):
                    row["entities"].append({"scope": name, "before": _r(vb), "after": _r(va),
                                            "before_status": sb, "after_status": sa,
                                            "before_utilisation_pct": _r(ub, 1), "after_utilisation_pct": _r(ua, 1)})
                if a["active"] and sa == "hard_breach" and (sb != "hard_breach" or ua > ub + UTIL_TOLERANCE):
                    blocking.append({"metric": b["metric"], "label": b["label"], "scope": name,
                                     "before": _r(vb), "after": _r(va), "hard_limit": b["hard_limit"],
                                     "message": f"{b['label']} {name} {vb:.1f}% -> {va:.1f}% (hard {b['hard_limit']:g}%)"})
        else:
            if a["active"] and a["status"] == "hard_breach":
                ub = b["utilisation_pct"] if b["utilisation_pct"] is not None else 0.0
                ua = a["utilisation_pct"] if a["utilisation_pct"] is not None else math.inf
                if b["status"] != "hard_breach" or ua > ub + UTIL_TOLERANCE:
                    blocking.append({"metric": b["metric"], "label": b["label"], "scope": "",
                                     "before": b["value"], "after": a["value"], "hard_limit": b["hard_limit"],
                                     "message": f"{b['label']} {b['value']} -> {a['value']} (hard {_limit_text(b)})"})
        rows.append(row)

    return {
        "ticker": clean, "qty": qty, "price": price,
        "nav_before": before_m["nav"], "nav_after": after_m["nav"],
        "cash_before": round(cash, 2), "cash_after": round(after_cash, 2),
        "limits": rows,
        "blocking_breaches": blocking,
        "requires_override": len(blocking) > 0,
        "_provenance": {
            "source": "mock_engine + LedoitWolf_Shrunk_Covariance",
            "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": "252d",
            "method": "pro-forma holdings after trade, all limit metrics recomputed with portfolio_engine",
        },
    }


def _limit_text(r):
    if r["direction"] == "band":
        return f"{r['hard_limit_low']:g}-{r['hard_limit']:g}"
    if r["direction"] == "min":
        return f">= {r['hard_limit']:g}"
    return f"{r['hard_limit']:g}"


def validate_limit_values(direction, soft, hard, soft_low=None, hard_low=None):
    """Raise ValueError if the soft/hard ordering makes no sense for the direction."""
    if hard is None:
        raise ValueError("hard_limit is required")
    if direction == "max" and soft is not None and soft > hard:
        raise ValueError("soft_limit must be <= hard_limit for an upper limit")
    if direction == "min" and soft is not None and soft < hard:
        raise ValueError("soft_limit must be >= hard_limit for a minimum (floor) limit")
    if direction == "band":
        if hard_low is None or soft_low is None or soft is None:
            raise ValueError("band limits need soft_limit, hard_limit, soft_limit_low and hard_limit_low")
        if not (hard_low <= soft_low <= soft <= hard):
            raise ValueError("band limits must satisfy hard_low <= soft_low <= soft <= hard")


# ---------------------------------------------------------------------------
# RSK-007: pre-trade headroom (limit capacity) per ticker
# ---------------------------------------------------------------------------
LIQUIDITY_TRADE_CAP_ADV = 0.10   # a single order may not exceed 10% of 20-day ADV (R-P0-7)


def _limit_lookup(limits: list) -> dict:
    return {l["metric"]: l for l in limits}


def compute_headroom(raw_positions: list, cash: float, limits: list, ticker: str) -> dict:
    """
    Max whole shares that can be bought / sold in `ticker` at the current mock price without
    crossing a hard limit. Buying with cash leaves NAV unchanged, so caps are linear:
      single name:  (hard% x NAV - MV_ticker) / P
      sector:       (hard% x NAV - MV_sector) / P   (sector MV includes the ticker itself)
      liquidity:    10% x ADV20 shares per order
      cash:         cash / P (no leverage on a long-only book)
    Sells are bounded by shares held, the same liquidity cap and the portfolio-beta floor:
      beta floor:   (beta_p - hard_low) x NAV / (P x beta_ticker)
    """
    clean = ticker.strip().upper()
    holdings = calculate_portfolio_holdings(raw_positions, cash)
    nav = holdings["nav"]
    prof = get_deterministic_mock_profile(clean)
    price = float(prof["current_price"])
    sector = prof["sector"]
    adv = float(prof["adv_20d_shares"])
    beta_t = float(prof["beta"])
    lim = _limit_lookup(limits)

    pos = next((p for p in holdings["positions"] if p["ticker"] == clean), None)
    held = float(pos["quantity"]) if pos else 0.0
    mv_t = float(pos["market_value"]) if pos else 0.0
    mv_sector = sum(p["market_value"] for p in holdings["positions"] if p["sector"] == sector)
    beta_p = (sum(p["market_value"] * p["beta"] for p in holdings["positions"]) / nav) if nav > 0 else 0.0

    def cap_row(key, label, limit_pct, current_value_usd, active=True):
        if not active or limit_pct is None:
            return None
        cap_usd = limit_pct / 100.0 * nav
        room = cap_usd - current_value_usd
        shares = max(0, math.floor(room / price + 1e-9)) if price > 0 else 0
        cur_pct = current_value_usd / nav * 100.0 if nav > 0 else 0.0
        reason = None
        if room <= 0:
            reason = f"{label} already {'breached' if cur_pct > limit_pct + 1e-9 else 'at limit'} ({cur_pct:.1f}% vs {limit_pct:g}%)"
        return {"key": key, "label": label, "limit_pct": limit_pct, "current_pct": round(cur_pct, 2),
                "max_shares": shares, "max_dollars": round(shares * price, 2), "reason": reason}

    sn, sec = lim.get("single_name_weight_pct"), lim.get("sector_weight_pct")
    buy_caps = [c for c in (
        cap_row("single_name", f"Single-name cap {_f(sn['hard_limit']):g}%" if sn else "", _f(sn["hard_limit"]) if sn else None, mv_t, bool(sn and sn.get("active", True))),
        cap_row("sector", f"Sector cap {_f(sec['hard_limit']):g}% ({sector})" if sec else "", _f(sec["hard_limit"]) if sec else None, mv_sector, bool(sec and sec.get("active", True))),
    ) if c]
    liq_shares = math.floor(LIQUIDITY_TRADE_CAP_ADV * adv)
    buy_caps.append({"key": "liquidity", "label": "Liquidity cap 10% ADV20", "limit_pct": None, "current_pct": None,
                     "max_shares": liq_shares, "max_dollars": round(liq_shares * price, 2), "reason": None})
    cash_shares = max(0, math.floor(cash / price + 1e-9)) if price > 0 else 0
    buy_caps.append({"key": "cash", "label": "Available cash", "limit_pct": None, "current_pct": None,
                     "max_shares": cash_shares, "max_dollars": round(cash_shares * price, 2),
                     "reason": None if cash_shares > 0 else "No cash available"})
    buy_bind = min(buy_caps, key=lambda c: c["max_shares"])

    sell_caps = [{"key": "position", "label": "Shares held", "max_shares": int(math.floor(held + 1e-9)),
                  "reason": None if held > 0 else "No open position"},
                 {"key": "liquidity", "label": "Liquidity cap 10% ADV20", "max_shares": liq_shares, "reason": None}]
    beta_lim = lim.get("portfolio_beta")
    if beta_lim and beta_lim.get("active", True) and _f(beta_lim.get("hard_limit_low")) is not None and beta_t > 0:
        floor_b = _f(beta_lim["hard_limit_low"])
        room = (beta_p - floor_b) * nav
        shares = max(0, math.floor(room / (price * beta_t) + 1e-9))
        sell_caps.append({"key": "beta_floor", "label": f"Portfolio beta floor {floor_b:g}", "max_shares": shares,
                          "reason": None if room > 0 else f"Portfolio beta already below floor ({beta_p:.2f} < {floor_b:g})"})
    sell_bind = min(sell_caps, key=lambda c: c["max_shares"])
    for c in sell_caps:
        c["max_dollars"] = round(c["max_shares"] * price, 2)

    def summary(b, caps):
        # every constraint tied at the minimum is reported, e.g. both single-name and sector already breached
        tied = [c for c in caps if c["max_shares"] == b["max_shares"]]
        reasons = [c["reason"] for c in tied if c.get("reason")]
        return {"shares": b["max_shares"], "dollars": b["max_dollars"],
                "pct_nav": round(b["max_dollars"] / nav * 100.0, 2) if nav > 0 else 0.0,
                "binding": b["key"], "binding_label": " + ".join(c["label"] for c in tied),
                "binding_keys": [c["key"] for c in tied],
                "reason": "; ".join(reasons) if reasons else None}

    by_key = {c["key"]: c for c in buy_caps}
    return {
        "ticker": clean, "sector": sector, "price": price, "nav": nav, "cash": round(cash, 2),
        "held_shares": held, "adv_20d_shares": adv,
        "current_weight_pct": round(mv_t / nav * 100.0, 2) if nav > 0 else 0.0,
        "current_sector_pct": round(mv_sector / nav * 100.0, 2) if nav > 0 else 0.0,
        "portfolio_beta": round(beta_p, 4),
        # spec field names (R-P0-7)
        "max_shares_single_name": by_key["single_name"]["max_shares"] if "single_name" in by_key else None,
        "max_shares_sector": by_key["sector"]["max_shares"] if "sector" in by_key else None,
        "max_shares_liquidity": liq_shares,
        "binding_headroom": summary(buy_bind, buy_caps),
        "buy": {"caps": buy_caps, **summary(buy_bind, buy_caps)},
        "sell": {"caps": sell_caps, **summary(sell_bind, sell_caps)},
        "_provenance": {
            "source": "mock_engine", "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "method": "linear caps at current price; NAV unchanged by cash-funded trades; whole shares (floor)",
        },
    }


# ---------------------------------------------------------------------------
# RSK-008: de-risking suggestion for a breach (used by the navbar drawer)
# ---------------------------------------------------------------------------
def suggest_derisk(raw_positions: list, cash: float, metric: str, scope: str, hard_limit: float):
    """
    Smallest sells (whole shares, at current price) that bring a single-name or sector
    weight back to its hard limit. Other metrics return None (review on the Limits tab).
    """
    if hard_limit is None or metric not in ("single_name_weight_pct", "sector_weight_pct"):
        return None
    holdings = calculate_portfolio_holdings(raw_positions, cash)
    nav = holdings["nav"]
    if metric == "single_name_weight_pct":
        names = [p for p in holdings["positions"] if p["ticker"] == scope]
    else:
        names = sorted([p for p in holdings["positions"] if p["sector"] == scope], key=lambda p: -p["market_value"])
    excess = sum(p["market_value"] for p in names) - hard_limit / 100.0 * nav
    if excess <= 0:
        return None
    sells = []
    for p in names:
        if excess <= 1e-9:
            break
        price = p["current_price"]
        cap = p["market_value"]
        take = min(cap, excess)
        shares = min(int(math.ceil(take / price - 1e-9)), int(math.floor(p["quantity"] + 1e-9)))
        if shares <= 0:
            continue
        sells.append({"ticker": p["ticker"], "qty": -shares, "price": price, "dollars": round(shares * price, 2)})
        excess -= shares * price
    return {"type": "sell_to_hard_limit", "trades": sells,
            "text": "Sell " + ", ".join(f"{-t['qty']} {t['ticker']}" for t in sells) + f" to return to the {hard_limit:g}% hard limit"}
