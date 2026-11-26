"""
FastAPI router for the Risk Manager track (RSK-002 limits, RSK-003 breaches + pre-trade what-if).
Reuses portfolio_engine via agents.risk_limits; all persistence goes through agents.db.query.
"""

import json
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agents.db import query
from auth import get_service_or_user
from agents.risk_limits import (
    DEFAULT_LIMITS,
    DEFAULTS_BY_METRIC,
    RISK_SCHEMA_SQL,
    breach_items,
    compute_headroom,
    compute_limit_metrics,
    evaluate_limits,
    suggest_derisk,
    validate_limit_values,
    what_if,
)

risk_router = APIRouter(tags=["Risk Management"])

_schema_lock = threading.Lock()
_schema_ready = False


def ensure_risk_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if not _schema_ready:
            query(RISK_SCHEMA_SQL)
            _schema_ready = True


def _actor(user: dict) -> str:
    return str(user.get("email") or user.get("sub") or "unknown")


def _load_portfolio(portfolio_id: int, user: Optional[dict] = None):
    p = query("SELECT * FROM portfolios WHERE id = %s", [portfolio_id])
    if not p.rows:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    portfolio = p.rows[0]
    if user is not None and user.get("role") != "service":
        from agents.portfolio_router import _resolve_user_id
        uid = _resolve_user_id(user)
        if int(portfolio["user_id"]) != uid:
            raise HTTPException(status_code=403, detail="Forbidden: portfolio does not belong to current user")
    pos = query("SELECT ticker, quantity, avg_cost, side FROM positions WHERE portfolio_id = %s ORDER BY id", [portfolio_id])
    return portfolio, [dict(r) for r in pos.rows]


def ensure_default_limits(portfolio_id: int):
    for metric, _label, unit, direction, soft, hard, soft_low, hard_low, _scope in DEFAULT_LIMITS:
        query(
            """INSERT INTO risk_limits (portfolio_id, metric, soft_limit, hard_limit, soft_limit_low, hard_limit_low,
                                        direction, unit, active, updated_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, 'system-default')
               ON CONFLICT (portfolio_id, metric) DO NOTHING;""",
            [portfolio_id, metric, soft, hard, soft_low, hard_low, direction, unit],
        )


def load_limits(portfolio_id: int) -> list:
    ensure_risk_schema()
    ensure_default_limits(portfolio_id)
    res = query("SELECT * FROM risk_limits WHERE portfolio_id = %s ORDER BY id", [portfolio_id])
    return [dict(r) for r in res.rows]


def sync_breaches(portfolio_id: int, rows: list) -> dict:
    """
    Breach lifecycle: open on first crossing, refresh last_seen/value while it persists,
    auto-resolve (history kept) once back inside the limit.
    """
    current = {(i["metric"], i["scope"]): i for i in breach_items(rows)}
    active = query(
        "SELECT * FROM limit_breaches WHERE portfolio_id = %s AND status IN ('open', 'acknowledged')",
        [portfolio_id],
    ).rows
    seen = set()
    opened = resolved = 0
    for b in active:
        key = (b["metric"], b["scope"])
        if key in current and key not in seen:
            i = current[key]
            query(
                """UPDATE limit_breaches SET last_seen = CURRENT_TIMESTAMP, value = %s, limit_value = %s, severity = %s
                   WHERE id = %s""",
                [i["value"], i["limit_value"], i["severity"], b["id"]],
            )
            seen.add(key)
        else:
            query(
                "UPDATE limit_breaches SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP WHERE id = %s",
                [b["id"]],
            )
            resolved += 1
    for key, i in current.items():
        if key not in seen:
            query(
                """INSERT INTO limit_breaches (portfolio_id, metric, scope, value, limit_value, severity, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'open')""",
                [portfolio_id, i["metric"], i["scope"], i["value"], i["limit_value"], i["severity"]],
            )
            opened += 1
    return {"opened": opened, "resolved": resolved, "active": len(current)}


def evaluate_portfolio(portfolio_id: int, sync: bool = True, user: Optional[dict] = None) -> dict:
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    metrics = compute_limit_metrics(raw, float(portfolio["cash"]), portfolio.get("benchmark") or "SPY")
    rows = evaluate_limits(limits, metrics)
    sync_result = sync_breaches(portfolio_id, rows) if sync else None
    return {"portfolio": portfolio, "raw": raw, "limits": limits, "metrics": metrics, "rows": rows, "sync": sync_result}


def pre_trade_check(portfolio_id: int, ticker: str, qty: float, price: float, fees: float = 0.0, user: Optional[dict] = None) -> dict:
    """Used by POST /transactions before executing (RSK-003)."""
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    try:
        return what_if(raw, float(portfolio["cash"]), limits, ticker, qty, price, fees,
                       portfolio.get("benchmark") or "SPY")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def record_override(portfolio_id: int, transaction_id, ticker: str, qty: float, price: float,
                    blocking: list, reason: str, actor: str):
    ensure_risk_schema()
    query(
        """INSERT INTO limit_overrides (portfolio_id, transaction_id, ticker, qty, price, breaches, reason, overridden_by)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
        [portfolio_id, transaction_id, ticker, qty, price, json.dumps(blocking), reason, actor],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
class LimitUpdateRequest(BaseModel):
    soft_limit: Optional[float] = None
    hard_limit: Optional[float] = None
    soft_limit_low: Optional[float] = None
    hard_limit_low: Optional[float] = None
    active: Optional[bool] = None
    reason: Optional[str] = None


class WhatIfRequest(BaseModel):
    ticker: str
    qty: float
    price: Optional[float] = None
    fees: Optional[float] = 0.0


class AcknowledgeRequest(BaseModel):
    owner: Optional[str] = None
    comment: str


def _limits_payload(portfolio_id: int, ev: dict) -> dict:
    rows = ev["rows"]
    open_rows = query(
        "SELECT severity, status FROM limit_breaches WHERE portfolio_id = %s AND status IN ('open','acknowledged')",
        [portfolio_id],
    ).rows
    open_hard = sum(1 for r in open_rows if r["severity"] == "hard" and r["status"] == "open")
    open_soft = sum(1 for r in open_rows if r["severity"] == "soft" and r["status"] == "open")
    return {
        "portfolio_id": portfolio_id,
        "portfolio_name": ev["portfolio"]["name"],
        "nav": ev["metrics"]["nav"],
        "limits": rows,
        "summary": {
            "hard_breaches": open_hard,
            "soft_breaches": open_soft,
            "hard_breach_metrics": sum(1 for r in rows if r["status"] == "hard_breach"),
            "soft_breach_metrics": sum(1 for r in rows if r["status"] == "soft_breach"),
            "ok": sum(1 for r in rows if r["status"] == "ok"),
            "not_available": sum(1 for r in rows if r["status"] == "na"),
            "active_breach_records": len(open_rows),
        },
        "days_to_liquidate": ev["metrics"]["days_to_liquidate"],
        "_provenance": {
            "source": "mock_engine + LedoitWolf_Shrunk_Covariance",
            "window": "252d",
            "method": "utilisation = current / hard (max), (100 - current) / (100 - hard) (floor), max(v/high, low/v) (band); "
                      "liquidity = cash + min(MV, 5d x 20% ADV x price) per name",
        },
    }


@risk_router.get("/portfolios/{portfolio_id}/limits")
async def get_limits(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    ev = evaluate_portfolio(portfolio_id, sync=True, user=user)
    return _limits_payload(portfolio_id, ev)


@risk_router.put("/portfolios/{portfolio_id}/limits/{metric}")
async def update_limit(portfolio_id: int, metric: str, req: LimitUpdateRequest,
                       user: dict = Depends(get_service_or_user)):
    _load_portfolio(portfolio_id, user=user)
    limits = {l["metric"]: l for l in load_limits(portfolio_id)}
    if metric not in limits:
        raise HTTPException(status_code=404, detail=f"Unknown limit metric '{metric}'")
    cur = limits[metric]
    old = {k: (float(cur[k]) if cur[k] is not None and k != "active" else cur[k])
           for k in ("soft_limit", "hard_limit", "soft_limit_low", "hard_limit_low", "active")}
    new = dict(old)
    for k in ("soft_limit", "hard_limit", "soft_limit_low", "hard_limit_low", "active"):
        v = getattr(req, k)
        if v is not None:
            new[k] = v
    if new == old:
        raise HTTPException(status_code=400, detail="No change requested")
    direction = cur["direction"] or DEFAULTS_BY_METRIC[metric][3]
    try:
        validate_limit_values(direction, new["soft_limit"], new["hard_limit"], new["soft_limit_low"], new["hard_limit_low"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    actor = _actor(user)
    query(
        """UPDATE risk_limits SET soft_limit = %s, hard_limit = %s, soft_limit_low = %s, hard_limit_low = %s,
                  active = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
           WHERE portfolio_id = %s AND metric = %s""",
        [new["soft_limit"], new["hard_limit"], new["soft_limit_low"], new["hard_limit_low"], new["active"],
         actor, portfolio_id, metric],
    )
    query(
        """INSERT INTO risk_limit_audit (portfolio_id, metric, old_values, new_values, reason, changed_by)
           VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s)""",
        [portfolio_id, metric, json.dumps(old), json.dumps(new), req.reason, actor],
    )
    ev = evaluate_portfolio(portfolio_id, sync=True)
    return _limits_payload(portfolio_id, ev)


@risk_router.get("/portfolios/{portfolio_id}/limits/audit")
async def get_limit_audit(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    _load_portfolio(portfolio_id, user=user)
    ensure_risk_schema()
    rows = query(
        "SELECT * FROM risk_limit_audit WHERE portfolio_id = %s ORDER BY changed_at DESC LIMIT 200",
        [portfolio_id],
    ).rows
    return [{**dict(r), "changed_at": str(r["changed_at"])} for r in rows]


@risk_router.post("/portfolios/{portfolio_id}/what-if")
async def post_what_if(portfolio_id: int, req: WhatIfRequest, user: dict = Depends(get_service_or_user)):
    from agents.mock_market_data import get_deterministic_mock_profile
    if req.qty == 0:
        raise HTTPException(status_code=400, detail="qty must be non-zero (positive = buy, negative = sell)")
    price = req.price if req.price and req.price > 0 else get_deterministic_mock_profile(req.ticker)["current_price"]
    return pre_trade_check(portfolio_id, req.ticker, req.qty, price, req.fees or 0.0, user=user)


def _breach_json(r):
    out = dict(r)
    for k in ("first_seen", "last_seen", "acknowledged_at", "resolved_at"):
        out[k] = str(out[k]) if out.get(k) else None
    for k in ("value", "limit_value"):
        out[k] = float(out[k]) if out.get(k) is not None else None
    d = DEFAULTS_BY_METRIC.get(out["metric"])
    out["label"] = d[1] if d else out["metric"]
    return out


@risk_router.get("/portfolios/{portfolio_id}/breaches")
async def get_breaches(portfolio_id: int, status: Optional[str] = None, user: dict = Depends(get_service_or_user)):
    evaluate_portfolio(portfolio_id, sync=True, user=user)  # refresh lifecycle first
    if status == "active":
        rows = query("""SELECT * FROM limit_breaches WHERE portfolio_id = %s AND status IN ('open','acknowledged')
                        ORDER BY (severity = 'hard') DESC, first_seen DESC""", [portfolio_id]).rows
    elif status:
        rows = query("SELECT * FROM limit_breaches WHERE portfolio_id = %s AND status = %s ORDER BY first_seen DESC",
                     [portfolio_id, status]).rows
    else:
        rows = query("SELECT * FROM limit_breaches WHERE portfolio_id = %s ORDER BY first_seen DESC LIMIT 500",
                     [portfolio_id]).rows
    return [_breach_json(r) for r in rows]


@risk_router.post("/portfolios/{portfolio_id}/breaches/{breach_id}/acknowledge")
async def acknowledge_breach(portfolio_id: int, breach_id: int, req: AcknowledgeRequest,
                             user: dict = Depends(get_service_or_user)):
    _load_portfolio(portfolio_id, user=user)
    ensure_risk_schema()
    if not req.comment or not req.comment.strip():
        raise HTTPException(status_code=400, detail="An acknowledgement comment is required")
    res = query(
        """UPDATE limit_breaches SET status = 'acknowledged', owner = %s, comment = %s, acknowledged_at = CURRENT_TIMESTAMP
           WHERE id = %s AND portfolio_id = %s AND status = 'open' RETURNING *""",
        [req.owner or _actor(user), req.comment.strip(), breach_id, portfolio_id],
    )
    if not res.rows:
        raise HTTPException(status_code=404, detail="Open breach not found")
    return _breach_json(res.rows[0])


@risk_router.get("/portfolios/{portfolio_id}/overrides")
async def get_overrides(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    _load_portfolio(portfolio_id, user=user)
    ensure_risk_schema()
    rows = query("SELECT * FROM limit_overrides WHERE portfolio_id = %s ORDER BY created_at DESC LIMIT 200",
                 [portfolio_id]).rows
    return [{**dict(r), "qty": float(r["qty"]), "price": float(r["price"]), "created_at": str(r["created_at"])} for r in rows]


# ---------------------------------------------------------------------------
# RSK-007: headroom
# ---------------------------------------------------------------------------
@risk_router.get("/portfolios/{portfolio_id}/headroom/{ticker}")
async def get_headroom(portfolio_id: int, ticker: str, user: dict = Depends(get_service_or_user)):
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    return compute_headroom(raw, float(portfolio["cash"]), limits, ticker)


# ---------------------------------------------------------------------------
# RSK-008: cross-portfolio breach summary for the navbar badge + drawer
# ---------------------------------------------------------------------------
@risk_router.get("/risk/breaches/summary")
async def get_breach_summary(user: dict = Depends(get_service_or_user)):
    from datetime import datetime, timezone
    from agents.portfolio_router import _resolve_user_id
    user_id = _resolve_user_id(user)
    ports = query("SELECT id, name FROM portfolios WHERE user_id = %s ORDER BY id", [user_id]).rows
    out = []
    now = datetime.now(timezone.utc)
    for p in ports:
        ev = evaluate_portfolio(p["id"], sync=True)
        hard_by_metric = {r["metric"]: r["hard_limit"] for r in ev["rows"]}
        rows = query(
            """SELECT * FROM limit_breaches WHERE portfolio_id = %s AND status IN ('open','acknowledged')
               ORDER BY (severity = 'hard') DESC, (status = 'open') DESC, first_seen ASC""",
            [p["id"]],
        ).rows
        for r in rows:
            b = _breach_json(r)
            b["portfolio_id"] = p["id"]
            b["portfolio_name"] = p["name"]
            b["age_seconds"] = int((now - r["first_seen"]).total_seconds()) if r.get("first_seen") else None
            b["suggestion"] = suggest_derisk(ev["raw"], float(ev["portfolio"]["cash"]), r["metric"], r["scope"],
                                             hard_by_metric.get(r["metric"]))
            out.append(b)
    open_hard = sum(1 for b in out if b["severity"] == "hard" and b["status"] == "open")
    open_soft = sum(1 for b in out if b["severity"] == "soft" and b["status"] == "open")
    return {
        "open_hard": open_hard,
        "open_soft": open_soft,
        "acknowledged": sum(1 for b in out if b["status"] == "acknowledged"),
        "active_total": len(out),
        "level": "hard" if open_hard else ("soft" if open_soft else ("acknowledged" if out else "clear")),
        "breaches": out,
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# RSK-004 / 005 / 006
# ---------------------------------------------------------------------------
_RANGES = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def _persist_history(portfolio_id: int, rows: list):
    """Replace the pro-forma backfill for this portfolio (one multi-row insert)."""
    query("DELETE FROM portfolio_risk_history WHERE portfolio_id = %s", [portfolio_id])
    if not rows:
        return
    vals, params = [], []
    for r in rows:
        vals.append("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")
        params += [portfolio_id, r["date"], r["nav"], r["gross_pct"], r["net_pct"], r["beta"], r["vol_exante"],
                   r["var95"], r["es975"], r["pnl_usd"], r["hwm"], r["drawdown"]]
    query("INSERT INTO portfolio_risk_history (portfolio_id, date, nav, gross, net, beta, vol_exante, var95, es975, pnl, hwm, drawdown) VALUES "
          + ",".join(vals), params)


@risk_router.get("/portfolios/{portfolio_id}/risk-history")
async def get_risk_history(portfolio_id: int, range: str = "1Y", user: dict = Depends(get_service_or_user)):
    from agents.risk_models import risk_history
    ensure_risk_schema()
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    h = risk_history(raw, float(portfolio["cash"]))
    _persist_history(portfolio_id, h["rows"])
    n = _RANGES.get((range or "1Y").upper(), 252)
    h["rows"] = h["rows"][-n:]
    h["range"] = (range or "1Y").upper()
    return h


@risk_router.get("/portfolios/{portfolio_id}/var")
async def get_var(portfolio_id: int, confidence: float = 0.99, horizon: int = 1, tickers: Optional[str] = None,
                  user: dict = Depends(get_service_or_user)):
    from agents.risk_models import var_report
    if confidence not in (0.95, 0.99) or horizon not in (1, 10):
        raise HTTPException(status_code=400, detail="confidence must be 0.95 or 0.99 and horizon 1 or 10")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    extra = tickers.split(",") if tickers else None
    return var_report(raw, float(portfolio["cash"]), confidence, horizon, extra_tickers=extra)


@risk_router.get("/portfolios/{portfolio_id}/var-backtest")
async def get_var_backtest(portfolio_id: int, confidence: float = 0.99, user: dict = Depends(get_service_or_user)):
    from agents.risk_models import proforma_series, backtest_series, BACKTEST_DAYS, BACKTEST_WINDOW
    if confidence not in (0.95, 0.99):
        raise HTTPException(status_code=400, detail="confidence must be 0.95 or 0.99")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    if not raw:
        raise HTTPException(status_code=400, detail="Portfolio has no positions to backtest")
    s = proforma_series(raw, float(portfolio["cash"]))
    bt = backtest_series(s["returns"], s["dates"][1:], confidence)
    return {
        "confidence": confidence, "test_days": BACKTEST_DAYS, "estimation_window": BACKTEST_WINDOW,
        "methods": bt,
        "_provenance": {
            "basis": "pro-forma, current holdings", "source": "mock_engine price_series_504d",
            "method": f"VaR for day t estimated from the {BACKTEST_WINDOW} returns ending t-1 (no lookahead); "
                      "exception when realised return < -VaR; Kupiec POF and Christoffersen independence vs chi2(1), "
                      "Basel zones for 99% (0-4 green, 5-9 amber, 10+ red)",
            "as_of": s["dates"][-1],
        },
    }


# ---------------------------------------------------------------------------
# RSK-009 stress testing + scenario library, RSK-010 liquidity, RSK-011 attribution
# ---------------------------------------------------------------------------
_builtins_seeded = False


def _seed_builtin_scenarios():
    global _builtins_seeded
    if _builtins_seeded:
        return
    from agents.risk_phase3 import BUILTIN_SCENARIOS
    for sc in BUILTIN_SCENARIOS:
        query(
            """INSERT INTO stress_scenarios (key, name, kind, shocks, built_in, created_by)
               VALUES (%s, %s, %s, %s::jsonb, TRUE, 'system')
               ON CONFLICT (key) WHERE built_in DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
                   shocks = EXCLUDED.shocks, updated_at = CURRENT_TIMESTAMP""",
            [sc["key"], sc["name"], sc["kind"], json.dumps(sc["shocks"])],
        )
    _builtins_seeded = True


def _scenarios_for(portfolio_id: int = None) -> list:
    ensure_risk_schema()
    _seed_builtin_scenarios()
    rows = query(
        """SELECT * FROM stress_scenarios WHERE active AND (portfolio_id IS NULL OR portfolio_id = %s)
           ORDER BY built_in DESC, id""",
        [portfolio_id],
    ).rows
    return [_scenario_json(r) for r in rows]


def _scenario_json(r):
    out = dict(r)
    for k in ("created_at", "updated_at"):
        out[k] = str(out[k]) if out.get(k) else None
    if isinstance(out.get("shocks"), str):
        out["shocks"] = json.loads(out["shocks"])
    return out


class ScenarioRequest(BaseModel):
    name: str
    kind: Optional[str] = "custom"
    description: Optional[str] = None
    shocks: dict
    portfolio_id: Optional[int] = None


def _validate_shocks(sh: dict) -> dict:
    from agents.risk_phase3 import SECTORS
    allowed = {"market", "sectors", "tickers", "vol_mult"}
    bad = set(sh) - allowed
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown shock keys: {sorted(bad)}")
    if not (set(sh) & allowed):
        raise HTTPException(status_code=400, detail="shocks must contain market, sectors, tickers or vol_mult")
    def chk(v, what):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{what} must be a number (fractional move, e.g. -0.10)")
        if not -1.0 <= v <= 5.0:
            raise HTTPException(status_code=400, detail=f"{what} = {v} outside [-1, 5] (fractional move)")
        return v
    out = {}
    if "market" in sh:
        out["market"] = chk(sh["market"], "market")
    if "vol_mult" in sh:
        v = chk(sh["vol_mult"], "vol_mult")
        if v <= 0:
            raise HTTPException(status_code=400, detail="vol_mult must be > 0")
        out["vol_mult"] = v
    if "sectors" in sh:
        unknown = [k for k in sh["sectors"] if k not in SECTORS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown sectors {unknown}; valid: {SECTORS}")
        out["sectors"] = {k: chk(v, f"sector {k}") for k, v in sh["sectors"].items()}
    if "tickers" in sh:
        out["tickers"] = {k.strip().upper(): chk(v, f"ticker {k}") for k, v in sh["tickers"].items()}
    return out


@risk_router.get("/stress-scenarios")
async def list_scenarios(portfolio_id: Optional[int] = None, user: dict = Depends(get_service_or_user)):
    return _scenarios_for(portfolio_id)


@risk_router.post("/stress-scenarios")
async def create_scenario(req: ScenarioRequest, user: dict = Depends(get_service_or_user)):
    ensure_risk_schema()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    shocks = _validate_shocks(req.shocks or {})
    res = query(
        """INSERT INTO stress_scenarios (portfolio_id, name, kind, description, shocks, built_in, created_by)
           VALUES (%s, %s, %s, %s, %s::jsonb, FALSE, %s) RETURNING *""",
        [req.portfolio_id, req.name.strip(), req.kind or "custom", req.description, json.dumps(shocks), _actor(user)],
    )
    return _scenario_json(res.rows[0])


@risk_router.put("/stress-scenarios/{scenario_id}")
async def update_scenario(scenario_id: int, req: ScenarioRequest, user: dict = Depends(get_service_or_user)):
    ensure_risk_schema()
    cur = query("SELECT * FROM stress_scenarios WHERE id = %s", [scenario_id]).rows
    if not cur:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if cur[0]["built_in"]:
        raise HTTPException(status_code=403, detail="Built-in scenarios are read-only; save a copy instead")
    shocks = _validate_shocks(req.shocks or {})
    res = query(
        """UPDATE stress_scenarios SET name = %s, kind = %s, description = %s, shocks = %s::jsonb,
                  updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *""",
        [req.name.strip(), req.kind or "custom", req.description, json.dumps(shocks), scenario_id],
    )
    return _scenario_json(res.rows[0])


@risk_router.delete("/stress-scenarios/{scenario_id}")
async def delete_scenario(scenario_id: int, user: dict = Depends(get_service_or_user)):
    ensure_risk_schema()
    cur = query("SELECT built_in FROM stress_scenarios WHERE id = %s", [scenario_id]).rows
    if not cur:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if cur[0]["built_in"]:
        raise HTTPException(status_code=403, detail="Built-in scenarios cannot be deleted")
    query("DELETE FROM stress_scenarios WHERE id = %s", [scenario_id])
    return {"success": True, "id": scenario_id}


@risk_router.get("/portfolios/{portfolio_id}/stress-test")
async def get_stress_test(portfolio_id: int, target_loss_pct: float = 10.0, scenario_id: Optional[int] = None,
                          user: dict = Depends(get_service_or_user)):
    from agents.risk_phase3 import run_scenario, reverse_stress
    from agents.risk_models import current_drawdown
    if not 0 < target_loss_pct < 100:
        raise HTTPException(status_code=400, detail="target_loss_pct must be between 0 and 100")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    cash = float(portfolio["cash"])
    limits = load_limits(portfolio_id)
    scenarios = _scenarios_for(portfolio_id)
    if scenario_id is not None:
        scenarios = [s for s in scenarios if s["id"] == scenario_id]
        if not scenarios:
            raise HTTPException(status_code=404, detail="Scenario not found")
    hwm = None
    if raw:
        _dd, hwm, _nav = current_drawdown(raw, cash)
    results = [run_scenario(raw, cash, sc, limits, hwm) | {"built_in": sc["built_in"], "id": sc["id"]} for sc in scenarios]
    dd_lim = next((l for l in limits if l["metric"] == "drawdown_pct" and l.get("active", True)), None)
    rev = reverse_stress(raw, cash, target_loss_pct, hwm, float(dd_lim["hard_limit"]) if dd_lim else None) if raw else None
    worst = min((r for r in results if "pnl_usd" in r), key=lambda r: r["pnl_usd"], default=None)
    return {
        "portfolio_id": portfolio_id,
        "scenarios": results,
        "worst": {"name": worst["name"], "pnl_usd": worst["pnl_usd"], "pnl_pct": worst["pnl_pct"]} if worst else None,
        "reverse_stress": rev,
        "_provenance": {
            "basis": "current holdings at current mock prices",
            "method": "historical replays = approximate S&P sector moves over each window (illustrative); market shocks via "
                      "position beta; factor shocks via an illustrative sector-sensitivity table; limits re-evaluated on the "
                      "repriced book; reverse stress solved via beta and confirmed by full revaluation",
        },
    }


@risk_router.get("/portfolios/{portfolio_id}/liquidity-risk")
async def get_liquidity_risk(portfolio_id: int, participation: float = 0.20, impact_coeff: float = 1.0,
                             user: dict = Depends(get_service_or_user)):
    from agents.risk_phase3 import liquidity_risk
    if not 0.01 <= participation <= 1.0:
        raise HTTPException(status_code=400, detail="participation must be between 0.01 and 1.0")
    if not 0 <= impact_coeff <= 5:
        raise HTTPException(status_code=400, detail="impact_coeff must be between 0 and 5")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    return liquidity_risk(raw, float(portfolio["cash"]), participation, impact_coeff=impact_coeff)


@risk_router.get("/portfolios/{portfolio_id}/risk-attribution")
async def get_risk_attribution(portfolio_id: int, confidence: float = 0.99, user: dict = Depends(get_service_or_user)):
    from agents.risk_phase3 import risk_attribution
    if confidence not in (0.95, 0.99):
        raise HTTPException(status_code=400, detail="confidence must be 0.95 or 0.99")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    return risk_attribution(raw, float(portfolio["cash"]), confidence)


# ---------------------------------------------------------------------------
# RSK-012: Beta & Sector ETF Hedge Calculator + Drawdown Control Rules
# ---------------------------------------------------------------------------
@risk_router.get("/portfolios/{portfolio_id}/hedge-calculator")
async def get_hedge_calculator(
    portfolio_id: int,
    target_beta: float = 0.0,
    target_sector: Optional[str] = None,
    target_sector_weight_pct: Optional[float] = None,
    simulated_dd_pct: Optional[float] = None,
    derisk_mode: str = "pro_rata",
    user: dict = Depends(get_service_or_user),
):
    from agents.risk_phase4 import hedge_calculator
    if not -1.0 <= target_beta <= 2.0:
        raise HTTPException(status_code=400, detail="target_beta must be between -1.0 and 2.0")
    if derisk_mode not in ("pro_rata", "top_rc"):
        raise HTTPException(status_code=400, detail="derisk_mode must be 'pro_rata' or 'top_rc'")
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    res = hedge_calculator(
        raw,
        float(portfolio["cash"]),
        limits,
        target_beta=target_beta,
        target_sector=target_sector,
        target_sector_weight_pct=target_sector_weight_pct,
        simulated_dd_pct=simulated_dd_pct,
        derisk_mode=derisk_mode,
        benchmark=portfolio.get("benchmark") or "SPY",
    )
    res["portfolio_id"] = portfolio_id
    res["portfolio_name"] = portfolio["name"]
    return res


# ---------------------------------------------------------------------------
# RSK-013: AI Agent Model-Risk Monitor & Kill-Switch
# ---------------------------------------------------------------------------
class AgentControlUpdateRequest(BaseModel):
    kill_switch: Optional[bool] = None
    forced_degraded: Optional[bool] = None
    enabled: Optional[bool] = None
    min_quality_threshold: Optional[float] = None
    reason: Optional[str] = None


class SimulateDegradationRequest(BaseModel):
    agent_name: str
    simulated_quality_score: Optional[float] = 0.52
    ticker: Optional[str] = "AAPL"
    restore: Optional[bool] = False


@risk_router.get("/risk/model-risk")
async def get_model_risk(portfolio_id: Optional[int] = 1, user: dict = Depends(get_service_or_user)):
    from agents.risk_phase4 import model_risk_dashboard
    ensure_risk_schema()
    raw, cash = [], 0.0
    if portfolio_id:
        try:
            portfolio, raw = _load_portfolio(portfolio_id)
            cash = float(portfolio["cash"])
        except Exception:
            pass
    return model_risk_dashboard(raw, cash)


@risk_router.put("/risk/model-risk/agents/{agent_name}")
async def put_agent_control(agent_name: str, req: AgentControlUpdateRequest, user: dict = Depends(get_service_or_user)):
    from agents.risk_phase4 import set_agent_control, model_risk_dashboard
    ensure_risk_schema()
    try:
        set_agent_control(
            agent_name=agent_name.strip().lower(),
            kill_switch=req.kill_switch,
            forced_degraded=req.forced_degraded,
            enabled=req.enabled,
            min_quality_threshold=req.min_quality_threshold,
            reason=req.reason,
            actor=_actor(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model_risk_dashboard()


@risk_router.post("/risk/model-risk/simulate-degradation")
async def post_simulate_degradation(req: SimulateDegradationRequest, user: dict = Depends(get_service_or_user)):
    from agents.risk_phase4 import simulate_agent_degradation, model_risk_dashboard
    ensure_risk_schema()
    try:
        simulate_agent_degradation(
            agent_name=req.agent_name.strip().lower(),
            simulated_quality_score=req.simulated_quality_score if req.simulated_quality_score is not None else 0.52,
            ticker=req.ticker or "AAPL",
            restore=bool(req.restore),
            actor=_actor(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model_risk_dashboard()


# ---------------------------------------------------------------------------
# RSK-014: Executive Morning Risk Tear Sheet & Export
# ---------------------------------------------------------------------------
@risk_router.get("/portfolios/{portfolio_id}/tear-sheet")
async def get_tear_sheet(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    from agents.risk_phase4 import morning_tear_sheet
    ensure_risk_schema()
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    return morning_tear_sheet(portfolio_id, portfolio, raw, limits)


@risk_router.get("/portfolios/{portfolio_id}/tear-sheet/export")
async def export_tear_sheet(portfolio_id: int, format: str = "csv", user: dict = Depends(get_service_or_user)):
    from fastapi.responses import Response
    from agents.risk_phase4 import morning_tear_sheet, tear_sheet_csv, tear_sheet_html
    ensure_risk_schema()
    portfolio, raw = _load_portfolio(portfolio_id, user=user)
    limits = load_limits(portfolio_id)
    sheet = morning_tear_sheet(portfolio_id, portfolio, raw, limits)
    fmt = (format or "csv").lower().strip()
    if fmt == "html":
        html_doc = tear_sheet_html(sheet)
        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'inline; filename="portfolio_{portfolio_id}_morning_tear_sheet.html"'},
        )
    csv_doc = tear_sheet_csv(sheet)
    return Response(
        content=csv_doc,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="portfolio_{portfolio_id}_morning_tear_sheet.csv"'},
    )

