"""
Quantitative Portfolio Management (QPM) Engine
Handles portfolio accounting, Ledoit-Wolf covariance shrinkage,
portfolio-level risk attribution (Euler decomposition), concentration metrics,
and multi-model position sizing.
"""

import math
import json
import numpy as np
import pandas as pd
from datetime import datetime
from agents.mock_market_data import get_deterministic_mock_profile, get_multi_asset_returns
from agents.db import query

def ledoit_wolf_shrinkage(X: np.ndarray):
    """
    Computes Ledoit-Wolf shrinkage covariance matrix targeting scaled identity (mu * I_p)
    matching sklearn.covariance.LedoitWolf in pure NumPy.
    X: (n_samples, p_features) return matrix.
    """
    n_samples, n_features = X.shape
    if n_features == 1:
        var = float(np.var(X[:, 0], ddof=1))
        return np.array([[var]]), 0.0, "scaled_identity"

    X_centered = X - np.mean(X, axis=0)
    emp_cov = np.dot(X_centered.T, X_centered) / n_samples
    mu = float(np.trace(emp_cov) / n_features)
    
    delta_ = emp_cov.copy()
    delta_.flat[::n_features + 1] -= mu
    delta = float((delta_ ** 2).sum())
    
    X2 = X_centered ** 2
    beta_ = float(1.0 / n_samples * (np.dot(X2.T, X2) / n_samples - emp_cov ** 2).sum())
    beta = min(beta_, delta)
    shrinkage = float(beta / delta) if delta > 0 else 0.0
    
    shrunk_cov = (1.0 - shrinkage) * emp_cov
    shrunk_cov.flat[::n_features + 1] += shrinkage * mu
    
    # Ensure positive definiteness
    min_eig = np.min(np.linalg.eigvalsh(shrunk_cov))
    if min_eig < 1e-8:
        shrunk_cov += (1e-8 - min_eig) * np.eye(n_features)
        
    return shrunk_cov, shrinkage, "scaled_identity"

def calculate_portfolio_holdings(raw_positions: list[dict], cash: float) -> dict:
    """
    Computes real-time market value, cost basis, unrealized P&L, day P&L,
    and portfolio weights (including cash) summing exactly to 100%.
    """
    positions = []
    total_market_value = 0.0
    gross_market_value = 0.0
    total_cost_basis = 0.0
    total_day_pnl = 0.0

    for pos in raw_positions:
        ticker = pos["ticker"].strip().upper()
        qty = float(pos["quantity"])
        avg_cost = float(pos["avg_cost"])
        side = pos.get("side", "short" if qty < 0 else "long").lower()
        
        prof = get_deterministic_mock_profile(ticker)
        curr_price = prof["current_price"]
        day_change = prof["day_change"]
        day_change_pct = prof["day_change_pct"]
        
        market_val = qty * curr_price
        cost_basis = qty * avg_cost
        unrealized_pnl = (market_val - cost_basis) if qty >= 0 else (abs(cost_basis) - abs(market_val))
        unrealized_pnl_pct = (unrealized_pnl / abs(cost_basis) * 100.0) if abs(cost_basis) > 0 else 0.0
        day_pnl = qty * day_change
        
        total_market_value += market_val
        gross_market_value += abs(market_val)
        total_cost_basis += cost_basis
        total_day_pnl += day_pnl
        
        positions.append({
            "id": pos.get("id"),
            "ticker": ticker,
            "company_name": prof["company_name"],
            "sector": prof["sector"],
            "industry": prof["industry"],
            "side": side,
            "quantity": qty,
            "avg_cost": round(avg_cost, 2),
            "current_price": curr_price,
            "market_value": round(market_val, 2),
            "cost_basis": round(cost_basis, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "day_pnl": round(day_pnl, 2),
            "recommendation": prof["recommendation"],
            "conviction": prof["conviction"],
            "target_price": prof["target_price"],
            "expected_return": prof["expected_return"],
            "beta": prof["beta"],
            "annualized_vol": prof["annualized_volatility"],
            "opened_at": str(pos.get("opened_at", ""))
        })

    nav = round(cash + total_market_value, 2)
    
    # Calculate weights summing to 100% including cash
    for p in positions:
        p["weight_pct"] = round((p["market_value"] / nav * 100.0), 2) if nav > 0 else 0.0

    cash_weight_pct = round((cash / nav * 100.0), 2) if nav > 0 else 100.0
    
    # Sector breakdown
    sector_weights = {}
    for p in positions:
        sec = p["sector"]
        sector_weights[sec] = round(sector_weights.get(sec, 0.0) + p["weight_pct"], 2)

    return {
        "nav": nav,
        "cash": round(cash, 2),
        "cash_weight_pct": cash_weight_pct,
        "total_market_value": round(total_market_value, 2),
        "total_cost_basis": round(total_cost_basis, 2),
        "total_unrealized_pnl": round(total_market_value - total_cost_basis, 2),
        "total_unrealized_pnl_pct": round(((total_market_value - total_cost_basis) / abs(total_cost_basis) * 100.0), 2) if abs(total_cost_basis) > 0 else 0.0,
        "total_day_pnl": round(total_day_pnl, 2),
        "gross_exposure": round(gross_market_value, 2),
        "net_exposure": round(total_market_value, 2),
        "gross_exposure_pct": round((gross_market_value / nav * 100.0), 2) if nav > 0 else 0.0,
        "net_exposure_pct": round((total_market_value / nav * 100.0), 2) if nav > 0 else 0.0,
        "positions_count": len(positions),
        "positions": positions,
        "sector_breakdown": sector_weights
    }

def calculate_portfolio_risk(positions: list[dict], cash: float, benchmark: str = "SPY") -> dict:
    """
    Computes portfolio-level volatility (annualized), Euler risk decomposition (RC_i),
    portfolio beta, VaR 95%, CVaR 97.5%, HHI, Effective Bets, and holdings correlation matrix.
    """
    if not positions:
        return {
            "portfolio_volatility": 0.0,
            "portfolio_beta": 0.0,
            "var_95_1d": 0.0,
            "cvar_975_1d": 0.0,
            "hhi": 0.0,
            "effective_bets": 0.0,
            "top5_concentration_pct": 0.0,
            "risk_contributions": [],
            "correlation_matrix": {"tickers": [], "matrix": []},
            "shrinkage_delta": 0.0
        }

    tickers = [p["ticker"] for p in positions]
    nav = cash + sum(p["market_value"] for p in positions)
    
    # Asset weights as fraction of NAV
    weights = np.array([p["market_value"] / nav for p in positions])
    
    # Multi-asset returns dataframe
    returns_df = get_multi_asset_returns(tickers)
    R = returns_df.values  # (252, n_assets)
    
    # Covariance with Ledoit-Wolf shrinkage (scaled identity target matching sklearn)
    cov_shrunk, delta, target_name = ledoit_wolf_shrinkage(R)
    
    # Portfolio variance and standard deviation (daily)
    port_daily_var = float(weights.T @ cov_shrunk @ weights)
    port_daily_sd = math.sqrt(max(1e-12, port_daily_var))
    
    # Annualized portfolio volatility
    port_ann_vol = round(float(port_daily_sd * math.sqrt(252)), 4)
    
    # Euler Marginal Contribution to Risk: MCR = (Cov @ w) / port_sd
    mcr = (cov_shrunk @ weights) / port_daily_sd
    
    # Position Risk Contribution: RC_i = w_i * MCR_i
    rc = weights * mcr
    
    # Percentage Risk Contribution: RC%_i = RC_i / port_daily_sd * 100
    rc_pct = (rc / port_daily_sd) * 100.0
    
    # Ensure numerical rounding sums cleanly
    rc_list = []
    for i, p in enumerate(positions):
        rc_list.append({
            "ticker": p["ticker"],
            "capital_weight_pct": round(weights[i] * 100.0, 2),
            "risk_contribution_pct": round(float(rc_pct[i]), 2),
            "marginal_risk": round(float(mcr[i] * math.sqrt(252)), 4),
            "sector": p.get("sector", "Other")
        })

    # Portfolio Beta vs benchmark
    betas = np.array([p.get("beta", 1.0) for p in positions])
    port_beta = round(float(np.sum(weights * betas)), 2)
    
    # Concentration metrics (strictly of invested capital)
    # HHI on invested assets normalized
    gross_mv = sum(abs(p["market_value"]) for p in positions)
    invested_w = np.array([abs(p["market_value"]) / gross_mv for p in positions]) if (positions and gross_mv > 0) else np.array([])
    hhi = round(float(np.sum(invested_w ** 2)), 4)
    effective_bets = round(float(1.0 / hhi), 1) if hhi > 0 else 0.0
    
    sorted_weights = sorted([abs(w) * 100.0 for w in weights], reverse=True)
    top5_weight = round(float(sum(sorted_weights[:5])), 2)
    
    # Parametric & Historical VaR/CVaR on the portfolio daily returns
    port_historical_returns = R @ weights
    var_95_param = round(float(-1.645 * port_daily_sd), 4)
    var_95_hist = round(float(np.percentile(port_historical_returns, 5)), 4)
    tail = port_historical_returns[port_historical_returns <= np.percentile(port_historical_returns, 2.5)]
    cvar_975 = round(float(np.mean(tail)), 4) if len(tail) else var_95_hist
    
    # Correlation matrix of holdings
    corr_df = returns_df.corr()
    matrix_data = []
    for t1 in tickers:
        row = []
        for t2 in tickers:
            row.append(round(float(corr_df.loc[t1, t2]), 3))
        matrix_data.append(row)

    return {
        "portfolio_volatility": port_ann_vol,
        "portfolio_beta": port_beta,
        "var_95_1d": var_95_hist,
        "var_95_parametric": var_95_param,
        "cvar_975_1d": cvar_975,
        "hhi": hhi,
        "effective_bets": effective_bets,
        "concentration_basis": "invested_capital",
        "hhi_label": "HHI (of invested capital)",
        "effective_bets_label": "Effective Bets (of invested capital)",
        "top5_concentration_pct": top5_weight,
        "shrinkage_delta": round(delta, 4),
        "shrinkage_target": target_name,
        "risk_contributions": rc_list,
        "correlation_matrix": {
            "tickers": tickers,
            "matrix": matrix_data
        }
    }

def calculate_position_sizing(
    ticker: str,
    nav: float,
    current_positions: list[dict] = None,
    method: str = "vol_target",
    daily_risk_budget: float = 0.0025,
    target_vol: float = 0.15,
    conviction_override: int = None,
    expected_return_override: float = None,
    current_price_override: float = None
) -> dict:
    """
    Computes suggested position size across 3 quantitative models:
    1. Volatility target (daily_risk_budget / daily vol, default 0.25% daily budget)
    2. Conviction-scaled risk budget
    3. Half-Kelly (capped)
    Applies single-name (8%), sector (30%), and liquidity (10% 20d ADV) caps.
    Returns selected_method and reports binding_constraint as one of:
      model:<name> | cap:single_name_8% | cap:sector_30% | cap:liquidity
    """
    prof = get_deterministic_mock_profile(ticker)
    curr_price = float(current_price_override) if (current_price_override and current_price_override > 0) else prof["current_price"]
    annual_vol = prof["annualized_volatility"]
    daily_vol = annual_vol / math.sqrt(252.0)
    conviction = int(conviction_override) if (conviction_override is not None and 1 <= int(conviction_override) <= 10) else prof["conviction"]
    expected_ret_pct = float(expected_return_override) if expected_return_override is not None else prof["expected_return"]
    adv_dollars = prof["adv_20d_dollars"]
    sector = prof["sector"]

    # If no explicit overrides were provided, check latest analysis_snapshots so sizing always matches the active report
    if conviction_override is None or expected_return_override is None:
        try:
            snap = query(
                "SELECT conviction, expected_return, price_at_ts FROM analysis_snapshots WHERE ticker = %s ORDER BY ts DESC LIMIT 1",
                [prof["ticker"]]
            )
            if snap.rows:
                row = snap.rows[0]
                if conviction_override is None and row.get("conviction") is not None:
                    conviction = int(row["conviction"])
                if expected_return_override is None and row.get("expected_return") is not None:
                    expected_ret_pct = float(row["expected_return"])
        except Exception:
            pass
    
    # 1. Volatility Target Model: daily_risk_budget / daily_vol
    # Default daily_risk_budget = 0.0025 (0.25% daily risk budget)
    safe_budget = float(daily_risk_budget) if daily_risk_budget and daily_risk_budget > 0 else 0.0025
    w_vol = safe_budget / max(0.001, daily_vol)
    
    # 2. Conviction-Scaled Risk Budget
    # f(conviction): <=4: 0, 5-6: 0.5, 7-8: 1.0, 9-10: 1.5
    if conviction <= 4:
        f_conv = 0.0
    elif conviction <= 6:
        f_conv = 0.5
    elif conviction <= 8:
        f_conv = 1.0
    else:
        f_conv = 1.5
    w_conv = (safe_budget * f_conv) / max(0.001, daily_vol)
    
    # 3. Half-Kelly: 0.5 * (mu - rf) / sigma^2
    rf = 0.045
    has_valid_expected_return = expected_ret_pct is not None
    mu = (expected_ret_pct / 100.0) if has_valid_expected_return else 0.0
    excess_ret = mu - rf
    w_kelly = max(0.0, 0.5 * (excess_ret / max(0.01, annual_vol ** 2))) if has_valid_expected_return else None
    
    # Resolve selected method
    norm_method = (method or "vol_target").lower().strip()
    if norm_method in ("conviction_scaled", "conviction"):
        selected_method = "conviction_scaled"
        raw_weight = w_conv
    elif norm_method in ("half_kelly", "kelly"):
        selected_method = "half_kelly"
        raw_weight = w_kelly
    else:
        selected_method = "vol_target"
        raw_weight = w_vol
    
    # Caps
    max_single_name = 0.08  # 8% max single name cap
    
    # Existing sector weight
    existing_sector_weight = 0.0
    if current_positions:
        for p in current_positions:
            if p.get("sector") == sector and p.get("ticker") != prof["ticker"]:
                existing_sector_weight += p.get("weight_pct", 0.0) / 100.0
    
    max_sector_avail = max(0.0, 0.30 - existing_sector_weight)
    
    # Liquidity cap: 10% of 20d ADV dollars
    adv_cap_weight = (adv_dollars * 0.10) / nav if nav > 0 else 0.08
    
    # Evaluate binding constraint strictly
    capped_weight = raw_weight
    binding_constraint = f"model:{selected_method}"
    
    if capped_weight > max_single_name:
        capped_weight = max_single_name
        binding_constraint = "cap:single_name_8%"
        
    if capped_weight > max_sector_avail:
        capped_weight = max_sector_avail
        binding_constraint = "cap:sector_30%"
        
    if capped_weight > adv_cap_weight:
        capped_weight = adv_cap_weight
        binding_constraint = "cap:liquidity"

    suggested_value = round(nav * capped_weight, 2)
    suggested_shares = int(suggested_value / curr_price) if curr_price > 0 else 0
    actual_suggested_val = round(suggested_shares * curr_price, 2)
    final_weight_pct = round((actual_suggested_val / nav) * 100.0, 2) if nav > 0 else 0.0

    # Holding context (for rebalancing / delta sizing)
    current_pos = next((p for p in current_positions if p.get("ticker") == prof["ticker"]), None) if current_positions else None
    current_qty = float(current_pos.get("quantity", 0)) if current_pos else 0.0
    current_weight_pct = float(current_pos.get("weight_pct", 0.0)) if current_pos else 0.0
    delta_shares = suggested_shares - int(current_qty)
    trade_action = "Add" if delta_shares > 0 else "Trim" if delta_shares < 0 else "Hold"
    
    position_context = {
        "is_held": current_pos is not None,
        "current_shares": int(current_qty),
        "current_weight_pct": round(current_weight_pct, 2),
        "target_weight_pct": final_weight_pct,
        "delta_shares": delta_shares,
        "trade_action": trade_action,
        "summary": f"Target {final_weight_pct}% · Current {round(current_weight_pct, 2)}% · {trade_action} {abs(delta_shares)} sh" if current_pos else f"New position target: Buy {suggested_shares} sh ({final_weight_pct}%)"
    }

    return {
        "ticker": prof["ticker"],
        "current_price": curr_price,
        "nav": nav,
        "conviction": conviction,
        "expected_return": expected_ret_pct,
        "selected_method": selected_method,
        "daily_risk_budget": safe_budget,
        "daily_risk_budget_pct": round(safe_budget * 100.0, 2),
        "suggested_weight_pct": final_weight_pct,
        "target_cap_weight_pct": round(capped_weight * 100.0, 2),
        "suggested_shares": suggested_shares,
        "suggested_dollars": actual_suggested_val,
        "target_cap_dollars": suggested_value,
        "binding_constraint": binding_constraint,
        "position_context": position_context,
        "models": {
            "vol_target": {
                "name": "Volatility Target",
                "raw_weight_pct": round(w_vol * 100.0, 2),
                "description": f"Positions sized to target {round(safe_budget * 100.0, 2)}% daily risk budget"
            },
            "conviction_scaled": {
                "name": "Conviction Scaled",
                "raw_weight_pct": round(w_conv * 100.0, 2),
                "description": f"Risk budget scaled by conviction ({conviction}/10, multiplier {f_conv}x)"
            },
            "half_kelly": {
                "name": "Half-Kelly (needs calibration)",
                "available": w_kelly is not None,
                "raw_weight_pct": round(w_kelly * 100.0, 2) if w_kelly is not None else None,
                "description": "0.5 × (expected return − risk-free) / variance (requires calibrated expected return)"
            }
        },
        "caps": {
            "max_single_name_pct": 8.0,
            "max_sector_pct": 30.0,
            "available_sector_capacity_pct": round(max_sector_avail * 100.0, 2),
            "adv_20d_dollars": adv_dollars,
            "max_liquidity_cap_dollars": round(adv_dollars * 0.10, 2)
        }
    }

def record_analysis_snapshot(ticker: str, analysis_result: dict) -> int:
    """
    Persists an immutable snapshot of an analysis run into analysis_snapshots.
    """
    clean_ticker = ticker.strip().upper()
    report = analysis_result.get("report", {})
    agents = analysis_result.get("agents", {})
    
    price = report.get("current_price", 0.0)
    rec = report.get("recommendation", "hold")
    conviction = int(report.get("conviction", 5))
    target = report.get("price_target")
    expected_ret = report.get("expected_return")
    horizon = int(report.get("horizon_days", 63))
    inval_price = report.get("invalidation_price")
    scenarios = json.dumps(report.get("scenarios", {}))
    metrics = json.dumps(report.get("_provenance", {}))
    outputs = json.dumps({
        "summary": report.get("summary"),
        "bull_case": report.get("bull_case"),
        "bear_case": report.get("bear_case")
    })
    
    sql = """
    INSERT INTO analysis_snapshots (
        ticker, price_at_ts, recommendation, conviction, target,
        expected_return, horizon_days, invalidation_price,
        scenarios_json, metrics_json, agent_outputs_json,
        model, mock_mode
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id;
    """
    res = query(sql, [
        clean_ticker, price, rec, conviction, target,
        expected_ret, horizon, inval_price,
        scenarios, metrics, outputs,
        "mistral-small-latest", True
    ])
    if res.rows:
        return res.rows[0]["id"]
    return None

def compute_snapshot_diff(latest: dict, previous: dict) -> dict:
    """
    Produces a structured diff between the current and prior analysis snapshot.
    """
    if not previous:
        return {
            "has_prior": False,
            "message": "First recorded analysis snapshot for this symbol."
        }

    conv_curr = latest.get("conviction")
    conv_prev = previous.get("conviction")
    conv_diff = (conv_curr - conv_prev) if (conv_curr is not None and conv_prev is not None) else 0

    target_curr = latest.get("target")
    target_prev = previous.get("target")
    target_diff = round(float(target_curr - target_prev), 2) if (target_curr is not None and target_prev is not None) else 0.0

    rec_curr = latest.get("recommendation", "").upper()
    rec_prev = previous.get("recommendation", "").upper()

    price_curr = latest.get("price_at_ts")
    price_prev = previous.get("price_at_ts")
    price_change = round(float(price_curr - price_prev), 2) if (price_curr and price_prev) else 0.0
    price_change_pct = round(price_change / float(price_prev) * 100.0, 2) if price_prev else 0.0

    return {
        "has_prior": True,
        "as_of_current": str(latest.get("ts", "")),
        "as_of_previous": str(previous.get("ts", "")),
        "conviction": {
            "previous": conv_prev,
            "current": conv_curr,
            "delta": conv_diff,
            "changed": conv_diff != 0
        },
        "target": {
            "previous": target_prev,
            "current": target_curr,
            "delta": target_diff,
            "changed": target_diff != 0
        },
        "recommendation": {
            "previous": rec_prev,
            "current": rec_curr,
            "changed": rec_curr != rec_prev
        },
        "price": {
            "previous": price_prev,
            "current": price_curr,
            "change": price_change,
            "change_pct": price_change_pct
        }
    }
