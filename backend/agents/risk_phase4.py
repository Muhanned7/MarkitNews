"""
Phase 4 & Phase 5 Risk Analyst Engine:
- RSK-012: Beta & Sector ETF Hedge Calculator + Drawdown Control Rules (R-P1-4, R-P1-5)
- RSK-013: AI Agent Model-Risk Monitor, Disagreement Index, Vol Bias & Kill-Switch (R-P2-1, R-P2-2, R-P2-4)
- RSK-014: Executive Morning Risk Tear Sheet & Export (R-P2-3, R-P2-5)

All numeric calculations are deterministic Python/NumPy computations over mock_market_data
and portfolio_engine; zero figures are invented by LLMs.
"""

import csv
import io
import json
import math
from datetime import datetime, timezone
import numpy as np

from agents.db import query
from agents.mock_market_data import (
    SECTOR_ETFS,
    get_deterministic_mock_profile,
    get_multi_asset_returns,
)
from agents.portfolio_engine import calculate_portfolio_holdings, calculate_portfolio_risk
from agents.risk_limits import compute_limit_metrics, evaluate_limits, breach_items
from agents.risk_models import (
    current_drawdown,
    proforma_series,
    var_report,
    backtest_series,
    risk_history,
    BACKTEST_WINDOW,
)
from agents.risk_phase3 import (
    BUILTIN_SCENARIOS,
    run_scenario,
    reverse_stress,
    liquidity_risk,
    risk_attribution,
)

ALL_AGENTS = [
    ("news", "News Intelligence Agent", "Ingests headlines & wire feeds"),
    ("sentiment", "Sentiment Analysis Agent", "Scores news & social polarity"),
    ("fundamentals", "Fundamentals Agent", "Evaluates balance sheet, FCF & multiples"),
    ("technical", "Technical Structure Agent", "Computes RSI, MACD, SMA/EMA trend"),
    ("equity", "Equity Research Agent", "Builds bull/bear cases & price targets"),
    ("risk", "Risk Specialist Agent", "Evaluates downside & volatility regimes"),
    ("portfolio_manager", "Lead Synthesizer (PM)", "Synthesizes final investment thesis"),
]


def _snapshot_metrics(raw_positions: list, cash: float, limits: list, benchmark: str = "SPY") -> dict:
    """Compute a complete before/after portfolio risk snapshot for hedge & de-risk comparisons."""
    holdings = calculate_portfolio_holdings(raw_positions, cash)
    positions = holdings["positions"]
    nav = holdings["nav"]
    risk = calculate_portfolio_risk(positions, cash, benchmark) if positions else {
        "portfolio_volatility": 0.0,
        "portfolio_beta": 0.0,
        "var_95_1d": 0.0,
        "cvar_975_1d": 0.0,
        "risk_contributions": [],
    }
    lim_metrics = compute_limit_metrics(raw_positions, cash, benchmark)
    eval_rows = evaluate_limits(limits, lim_metrics) if limits else []
    breaches = breach_items(eval_rows) if eval_rows else []
    exact_beta = lim_metrics["values"]["portfolio_beta"]

    return {
        "nav": round(nav, 2),
        "cash": round(cash, 2),
        "gross_exposure": holdings["gross_exposure"],
        "net_exposure": holdings["net_exposure"],
        "gross_exposure_pct": holdings["gross_exposure_pct"],
        "net_exposure_pct": holdings["net_exposure_pct"],
        "portfolio_beta": round(exact_beta, 4),
        "ex_ante_vol_pct": round(lim_metrics["values"]["ex_ante_vol_pct"], 2),
        "var95_1d_pct": round(lim_metrics["values"]["var95_1d_pct"], 2),
        "es975_1d_pct": round(lim_metrics["values"]["es975_1d_pct"], 2),
        "var95_1d_usd": round(lim_metrics["values"]["var95_1d_pct"] / 100.0 * nav, 2),
        "es975_1d_usd": round(lim_metrics["values"]["es975_1d_pct"] / 100.0 * nav, 2),
        "sector_breakdown": holdings["sector_breakdown"],
        "hard_breaches": sum(1 for b in breaches if b["severity"] == "hard"),
        "soft_breaches": sum(1 for b in breaches if b["severity"] == "soft"),
        "breaches": breaches,
    }


def _apply_trade_to_book(raw_positions: list, cash: float, trades: list[dict]) -> tuple[list, float]:
    """
    Applies one or more trades [{"ticker": ..., "qty": ..., "price": ...}] to a copy of raw_positions.
    Selling/shorting (qty < 0) adds -qty * price to cash and reduces/shorts position quantity,
    keeping NAV = cash + sum(market_value) strictly invariant.
    """
    book = {}
    for p in raw_positions:
        t = p["ticker"].strip().upper()
        book[t] = {
            "ticker": t,
            "quantity": float(p["quantity"]),
            "avg_cost": float(p["avg_cost"]),
            "side": p.get("side", "long"),
        }
    new_cash = float(cash)

    for tr in trades:
        t = tr["ticker"].strip().upper()
        qty = float(tr["qty"])
        if abs(qty) < 1e-9:
            continue
        prof = get_deterministic_mock_profile(t)
        price = float(tr.get("price") or prof["current_price"])
        new_cash -= qty * price  # qty < 0 (sell/short) increases cash by |qty| * price
        if t in book:
            new_qty = book[t]["quantity"] + qty
            if abs(new_qty) < 1e-6:
                del book[t]
            else:
                book[t]["quantity"] = round(new_qty, 4)
                book[t]["side"] = "short" if new_qty < 0 else "long"
        else:
            book[t] = {
                "ticker": t,
                "quantity": round(qty, 4),
                "avg_cost": price,
                "side": "short" if qty < 0 else "long",
            }
    return list(book.values()), round(new_cash, 2)


# ---------------------------------------------------------------------------
# RSK-012: Beta & Sector ETF Hedge Calculator + Drawdown Control Rules
# ---------------------------------------------------------------------------
def hedge_calculator(
    raw_positions: list,
    cash: float,
    limits: list,
    target_beta: float = 0.0,
    target_sector: str = None,
    target_sector_weight_pct: float = None,
    simulated_dd_pct: float = None,
    derisk_mode: str = "pro_rata",
    benchmark: str = "SPY",
) -> dict:
    """
    Computes:
    1. SPY Beta Hedge to reach target_beta (default 0.00 beta-neutral)
    2. Sector ETF Hedge (XLK, XLF, XLE, ...) & alternative Single-Name Trim for breached/concentrated sectors
    3. Drawdown Control Rules (Tier 1 at -5% DD alert, Tier 2 at -10% DD 25% gross exposure de-risking trade list)
    """
    before = _snapshot_metrics(raw_positions, cash, limits, benchmark)
    nav = before["nav"]
    cur_beta = before["portfolio_beta"]

    # 1. SPY Beta Hedge
    spy_prof = get_deterministic_mock_profile("SPY")
    spy_price = float(spy_prof["current_price"])
    spy_beta = float(spy_prof["beta"])  # 1.0
    # Notional_SPY = (target_beta - cur_beta) * NAV / spy_beta
    raw_spy_notional = ((target_beta - cur_beta) * nav) / spy_beta if nav > 0 else 0.0
    spy_shares = int(round(raw_spy_notional / spy_price)) if spy_price > 0 else 0
    actual_spy_notional = round(spy_shares * spy_price, 2)

    spy_trade = {
        "ticker": "SPY",
        "instrument_name": spy_prof["company_name"],
        "action": "SHORT" if spy_shares < 0 else ("BUY" if spy_shares > 0 else "NONE"),
        "qty": spy_shares,
        "price": spy_price,
        "notional_usd": actual_spy_notional,
        "pct_of_nav": round(actual_spy_notional / nav * 100.0, 2) if nav > 0 else 0.0,
    }
    post_spy_raw, post_spy_cash = _apply_trade_to_book(raw_positions, cash, [spy_trade])
    after_spy = _snapshot_metrics(post_spy_raw, post_spy_cash, limits, benchmark)

    beta_hedge_section = {
        "target_beta": round(target_beta, 4),
        "current_beta": round(cur_beta, 4),
        "theoretical_notional_usd": round(raw_spy_notional, 2),
        "trade": spy_trade,
        "what_if_payload": {"ticker": "SPY", "qty": spy_shares, "price": spy_price},
        "before": before,
        "after": after_spy,
        "beta_residual": round(abs(after_spy["portfolio_beta"] - target_beta), 4),
        "within_tolerance_002": abs(after_spy["portfolio_beta"] - target_beta) <= 0.02,
    }

    # 2. Sector ETF Hedges & Single-Name Trim Alternatives
    sec_limit_row = next((l for l in limits if l["metric"] == "sector_weight_pct"), None)
    sec_hard = float(sec_limit_row["hard_limit"]) if sec_limit_row and sec_limit_row.get("hard_limit") is not None else 30.0
    sec_soft = float(sec_limit_row["soft_limit"]) if sec_limit_row and sec_limit_row.get("soft_limit") is not None else 27.0

    holdings = calculate_portfolio_holdings(raw_positions, cash)
    positions = holdings["positions"]
    sector_plans = []

    for sec_name, cur_sec_weight in sorted(before["sector_breakdown"].items(), key=lambda x: x[1], reverse=True):
        etf_symbol = SECTOR_ETFS.get(sec_name, "SPY")
        etf_prof = get_deterministic_mock_profile(etf_symbol)
        etf_price = float(etf_prof["current_price"])

        # Determine target weight for this sector
        if target_sector and target_sector.lower() == sec_name.lower() and target_sector_weight_pct is not None:
            tgt_wt = float(target_sector_weight_pct)
        elif cur_sec_weight > sec_hard:
            # Default target brings breached sector safely inside soft limit (or hard_limit - 1.0%)
            tgt_wt = min(sec_soft, sec_hard - 0.5)
        elif cur_sec_weight > sec_soft:
            tgt_wt = sec_soft - 0.5
        else:
            tgt_wt = max(0.0, round(cur_sec_weight - 5.0, 2))

        excess_wt_pct = max(0.0, cur_sec_weight - tgt_wt)
        excess_notional_usd = (excess_wt_pct / 100.0) * nav

        # Use math.ceil on short ETF shares so rounding never leaves a breached sector above the target
        etf_short_shares = -int(math.ceil(excess_notional_usd / etf_price)) if (excess_notional_usd > 0 and etf_price > 0) else 0
        etf_notional = round(etf_short_shares * etf_price, 2)

        etf_trade = {
            "ticker": etf_symbol,
            "instrument_name": etf_prof["company_name"],
            "sector": sec_name,
            "action": "SHORT" if etf_short_shares < 0 else "NONE",
            "qty": etf_short_shares,
            "price": etf_price,
            "notional_usd": etf_notional,
            "pct_of_nav": round(etf_notional / nav * 100.0, 2) if nav > 0 else 0.0,
        }
        post_etf_raw, post_etf_cash = _apply_trade_to_book(raw_positions, cash, [etf_trade])
        after_etf = _snapshot_metrics(post_etf_raw, post_etf_cash, limits, benchmark)

        # Alternative: Single-Name Stock Trim (pro-rata across holdings in this sector)
        sec_positions = [p for p in positions if p["sector"] == sec_name and p["market_value"] > 0]
        sec_mv = sum(p["market_value"] for p in sec_positions)
        trim_trades = []
        for sp in sec_positions:
            share_of_sec = (sp["market_value"] / sec_mv) if sec_mv > 0 else 0.0
            trim_usd = excess_notional_usd * share_of_sec
            trim_qty = -int(math.ceil(trim_usd / sp["current_price"])) if sp["current_price"] > 0 else 0
            if trim_qty < 0:
                trim_trades.append({
                    "ticker": sp["ticker"],
                    "company_name": sp["company_name"],
                    "action": "SELL",
                    "qty": trim_qty,
                    "price": sp["current_price"],
                    "notional_usd": round(trim_qty * sp["current_price"], 2),
                    "pct_of_nav": round((trim_qty * sp["current_price"]) / nav * 100.0, 2) if nav > 0 else 0.0,
                })
        post_trim_raw, post_trim_cash = _apply_trade_to_book(raw_positions, cash, trim_trades)
        after_trim = _snapshot_metrics(post_trim_raw, post_trim_cash, limits, benchmark)

        sector_plans.append({
            "sector": sec_name,
            "current_weight_pct": round(cur_sec_weight, 2),
            "soft_limit_pct": sec_soft,
            "hard_limit_pct": sec_hard,
            "target_weight_pct": round(tgt_wt, 2),
            "status": "hard_breach" if cur_sec_weight > sec_hard else ("soft_breach" if cur_sec_weight > sec_soft else "ok"),
            "etf_hedge": {
                "trade": etf_trade,
                "what_if_payload": {"ticker": etf_symbol, "qty": etf_short_shares, "price": etf_price},
                "post_sector_weight_pct": after_etf["sector_breakdown"].get(sec_name, 0.0),
                "within_hard_limit": after_etf["sector_breakdown"].get(sec_name, 0.0) <= sec_hard,
                "after": after_etf,
            },
            "single_name_trim": {
                "trades": trim_trades,
                "post_sector_weight_pct": after_trim["sector_breakdown"].get(sec_name, 0.0),
                "within_hard_limit": after_trim["sector_breakdown"].get(sec_name, 0.0) <= sec_hard,
                "after": after_trim,
            },
        })

    # 3. Drawdown Control Rules (R-P1-4)
    if raw_positions:
        dd_frac, hwm, _ = current_drawdown(raw_positions, cash)
        actual_dd_pct = round(dd_frac * 100.0, 2)  # negative number when in drawdown, e.g. -6.09%
    else:
        actual_dd_pct = 0.0
        hwm = nav

    effective_dd_pct = round(float(simulated_dd_pct), 2) if simulated_dd_pct is not None else actual_dd_pct
    tier1_threshold = -5.0
    tier2_threshold = -10.0

    if effective_dd_pct <= tier2_threshold:
        dd_tier = 2
        dd_status = "TIER_2_DERISK_MANDATORY"
        dd_action_summary = (
            f"Portfolio drawdown ({effective_dd_pct:.2f}%) breached Tier-2 threshold ({tier2_threshold:.1f}%). "
            "Mandatory de-risking protocol triggered: cut gross exposure by 25%."
        )
    elif effective_dd_pct <= tier1_threshold:
        dd_tier = 1
        dd_status = "TIER_1_ALERT_WARNING"
        dd_action_summary = (
            f"Portfolio drawdown ({effective_dd_pct:.2f}%) breached Tier-1 alert threshold ({tier1_threshold:.1f}%). "
            "PM review & stop-loss tightening required; prepare 25% gross de-risking basket if drawdown reaches -10%."
        )
    else:
        dd_tier = 0
        dd_status = "NORMAL"
        dd_action_summary = f"Drawdown ({effective_dd_pct:.2f}%) is within Tier-1 threshold ({tier1_threshold:.1f}%)."

    # Compute the 25% gross exposure de-risking trade list (both pro-rata and top-RC)
    cut_fraction = 0.25
    target_gross_cut_usd = before["gross_exposure"] * cut_fraction
    risk_info = calculate_portfolio_risk(positions, cash, benchmark) if positions else {"risk_contributions": []}
    rc_by_ticker = {r["ticker"]: r["risk_contribution_pct"] for r in risk_info.get("risk_contributions", [])}

    derisk_trades = []
    if derisk_mode == "top_rc":
        # Sort positions by highest Euler risk contribution first
        sorted_pos = sorted(positions, key=lambda p: rc_by_ticker.get(p["ticker"], 0.0), reverse=True)
        remaining_cut = target_gross_cut_usd
        for p in sorted_pos:
            if remaining_cut <= 0 or p["market_value"] <= 0:
                continue
            cut_usd = min(p["market_value"] * 0.50, remaining_cut)  # cap single position cut at 50% so book stays diversified
            cut_qty = -round(cut_usd / p["current_price"], 2) if p["current_price"] > 0 else 0.0
            if abs(cut_qty) > 0:
                actual_usd = abs(cut_qty) * p["current_price"]
                remaining_cut -= actual_usd
                derisk_trades.append({
                    "ticker": p["ticker"],
                    "company_name": p["company_name"],
                    "sector": p["sector"],
                    "current_qty": p["quantity"],
                    "qty": cut_qty,
                    "price": p["current_price"],
                    "notional_usd": round(cut_qty * p["current_price"], 2),
                    "risk_contribution_pct": rc_by_ticker.get(p["ticker"], 0.0),
                    "rationale": "Top Euler Risk Contributor trim",
                })
    else:
        # Pro-rata 25% trim across all active positions
        for p in positions:
            if p["market_value"] <= 0:
                continue
            cut_qty = -round(p["quantity"] * cut_fraction, 2)
            if abs(cut_qty) > 0:
                derisk_trades.append({
                    "ticker": p["ticker"],
                    "company_name": p["company_name"],
                    "sector": p["sector"],
                    "current_qty": p["quantity"],
                    "qty": cut_qty,
                    "price": p["current_price"],
                    "notional_usd": round(cut_qty * p["current_price"], 2),
                    "risk_contribution_pct": rc_by_ticker.get(p["ticker"], 0.0),
                    "rationale": "Pro-rata 25% gross exposure reduction",
                })

    post_dd_raw, post_dd_cash = _apply_trade_to_book(raw_positions, cash, derisk_trades)
    after_dd = _snapshot_metrics(post_dd_raw, post_dd_cash, limits, benchmark)

    gross_cut_achieved_pct = (
        round((before["gross_exposure"] - after_dd["gross_exposure"]) / before["gross_exposure"] * 100.0, 2)
        if before["gross_exposure"] > 0 else 0.0
    )
    vol_reduction_pct = (
        round((before["ex_ante_vol_pct"] - after_dd["ex_ante_vol_pct"]) / before["ex_ante_vol_pct"] * 100.0, 2)
        if before["ex_ante_vol_pct"] > 0 else 0.0
    )

    drawdown_control = {
        "actual_drawdown_pct": actual_dd_pct,
        "simulated_drawdown_pct": round(float(simulated_dd_pct), 2) if simulated_dd_pct is not None else None,
        "effective_drawdown_pct": effective_dd_pct,
        "hwm_usd": round(float(hwm), 2),
        "tier": dd_tier,
        "status": dd_status,
        "action_summary": dd_action_summary,
        "rules": [
            {"tier": 1, "trigger_dd_pct": -5.0, "action": "Alert Risk Officer & PM; review stop-loss levels", "active": effective_dd_pct <= -5.0},
            {"tier": 2, "trigger_dd_pct": -10.0, "action": "Mandatory 25% gross exposure cut across book", "active": effective_dd_pct <= -10.0},
        ],
        "derisk_mode": derisk_mode,
        "target_gross_cut_pct": 25.0,
        "achieved_gross_cut_pct": gross_cut_achieved_pct,
        "vol_reduction_pct": vol_reduction_pct,
        "derisk_trades": derisk_trades,
        "before": before,
        "after": after_dd,
    }

    return {
        "portfolio_id": None,
        "nav": nav,
        "beta_hedge": beta_hedge_section,
        "sector_hedges": sector_plans,
        "drawdown_control": drawdown_control,
        "_provenance": {
            "source": "mock_engine + LedoitWolf_Shrunk_Covariance",
            "window": "252d",
            "method": "SPY beta hedge N_SPY = (beta_target - beta_p) * NAV; Sector ETF short via SPDR sector ETFs (XLK/XLF/XLE); "
                      "Drawdown Tier-1 (-5%) & Tier-2 (-10%) 25% gross reduction re-evaluated through full covariance engine",
        },
    }


# ---------------------------------------------------------------------------
# RSK-013: AI Agent Model-Risk Monitor & Kill-Switch (R-P2-1, R-P2-2, R-P2-4)
# ---------------------------------------------------------------------------
def _ensure_model_risk_seeded():
    """Ensure agent_model_risk_controls has rows for all 7 agents and agent_evaluations has baseline history."""
    for agent_name, _label, _desc in ALL_AGENTS:
        query(
            """INSERT INTO agent_model_risk_controls (agent_name, enabled, kill_switch, forced_degraded, min_quality_threshold, updated_by)
               VALUES (%s, TRUE, FALSE, FALSE, 0.70, 'system-default')
               ON CONFLICT (agent_name) DO NOTHING""",
            [agent_name],
        )

    # Check if agent_evaluations table exists and has rows for all 7 agents
    try:
        cnt_rows = query("SELECT agent_name, COUNT(*) AS n FROM agent_evaluations GROUP BY agent_name").rows
        counts = {r["agent_name"]: int(r["n"]) for r in cnt_rows}
    except Exception:
        query(
            """CREATE TABLE IF NOT EXISTS agent_evaluations (
                id SERIAL PRIMARY KEY,
                agent_name VARCHAR(50) NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                faithfulness_score NUMERIC(4, 2),
                consistency_score NUMERIC(4, 2),
                completeness_score NUMERIC(4, 2),
                overall_quality_score NUMERIC(4, 2),
                grade VARCHAR(10),
                guardrails_passed BOOLEAN DEFAULT TRUE,
                hallucinations_detected INTEGER DEFAULT 0,
                warnings JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        counts = {}

    seed_baselines = {
        "news": [(0.96, 1.00, 0.95, 0.97, "PASS", True, 0), (0.94, 1.00, 0.92, 0.95, "PASS", True, 0), (0.95, 1.00, 0.94, 0.96, "PASS", True, 0)],
        "sentiment": [(0.92, 0.95, 0.94, 0.94, "PASS", True, 0), (0.90, 0.92, 0.93, 0.92, "PASS", True, 0), (0.93, 0.95, 0.95, 0.94, "PASS", True, 0)],
        "fundamentals": [(0.98, 1.00, 0.96, 0.98, "PASS", True, 0), (0.97, 1.00, 0.95, 0.97, "PASS", True, 0), (0.99, 1.00, 0.97, 0.99, "PASS", True, 0)],
        "technical": [(0.97, 1.00, 0.95, 0.97, "PASS", True, 0), (0.96, 0.98, 0.94, 0.96, "PASS", True, 0), (0.98, 1.00, 0.96, 0.98, "PASS", True, 0)],
        "equity": [(0.91, 0.94, 0.92, 0.92, "PASS", True, 0), (0.89, 0.92, 0.90, 0.90, "PASS", True, 1), (0.93, 0.95, 0.94, 0.94, "PASS", True, 0)],
        "risk": [(0.97, 1.00, 0.96, 0.98, "PASS", True, 0), (0.96, 1.00, 0.95, 0.97, "PASS", True, 0), (0.98, 1.00, 0.97, 0.98, "PASS", True, 0)],
        "portfolio_manager": [(0.95, 0.98, 0.96, 0.96, "PASS", True, 0), (0.94, 0.96, 0.95, 0.95, "PASS", True, 0), (0.96, 0.98, 0.97, 0.97, "PASS", True, 0)],
    }
    tickers_cycle = ["AAPL", "MSFT", "NVDA"]
    for agent_name, samples in seed_baselines.items():
        if counts.get(agent_name, 0) < 3:
            for idx, (f_s, c_s, comp_s, ov_s, gr, gp, hal) in enumerate(samples):
                tkr = tickers_cycle[idx % len(tickers_cycle)]
                query(
                    """INSERT INTO agent_evaluations
                       (agent_name, ticker, faithfulness_score, consistency_score, completeness_score,
                        overall_quality_score, grade, guardrails_passed, hallucinations_detected, warnings)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '[]'::jsonb)""",
                    [agent_name, tkr, f_s, c_s, comp_s, ov_s, gr, gp, hal],
                )


def compute_disagreement_index(tickers: list[str] = None) -> list[dict]:
    """
    Computes cross-agent directional disagreement index for each ticker.
    Maps each specialist agent's signal onto [-1, +1] and computes dispersion (std dev).
    """
    if not tickers:
        tickers = ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]

    rec_map = {
        "strong_buy": 1.0,
        "buy": 0.5,
        "bullish": 0.6,
        "positive": 0.5,
        "hold": 0.0,
        "neutral": 0.0,
        "sell": -0.5,
        "bearish": -0.6,
        "negative": -0.5,
        "strong_sell": -1.0,
    }

    rows = []
    for tkr in tickers:
        prof = get_deterministic_mock_profile(tkr)
        # Derive deterministic agent-level stances from the profile's technical, fundamental, sentiment & risk metrics
        rsi = float(prof.get("rsi", 50.0))
        tech_trend = str(prof.get("trend", "bullish")).lower()
        tech_score = 0.65 if tech_trend == "bullish" and rsi < 70 else (-0.45 if rsi > 72 or tech_trend == "bearish" else 0.15)
        tech_label = "bullish" if tech_score > 0.2 else ("bearish" if tech_score < -0.2 else "neutral")

        pe = float(prof.get("pe_ratio", 25.0))
        fcf = float(prof.get("free_cashflow", 1e9))
        fund_score = 0.70 if (pe < 28 and fcf > 0) else (-0.35 if pe > 42 else 0.25)
        fund_label = "undervalued (buy)" if fund_score > 0.3 else ("stretched multiple (hold/trim)" if fund_score < 0 else "fair value (hold)")

        sent_label = str(prof.get("sentiment_label", "bullish")).lower()
        sent_score = float(prof.get("sentiment_score", 0.55))
        if sent_label in ("bearish", "negative"):
            sent_score = -abs(sent_score)

        eq_rec = str(prof.get("recommendation", "buy")).lower()
        eq_score = rec_map.get(eq_rec, 0.5)

        vol = float(prof.get("annualized_volatility", 0.25))
        beta = float(prof.get("beta", 1.0))
        risk_score = -0.55 if (vol > 0.35 or beta > 1.35) else (0.35 if vol < 0.22 else -0.15)
        risk_label = "elevated tail/beta caution" if risk_score < -0.2 else ("low-vol supportive" if risk_score > 0.1 else "moderate risk")

        stances = {
            "sentiment": {"stance": sent_label, "score": round(sent_score, 2)},
            "fundamentals": {"stance": fund_label, "score": round(fund_score, 2)},
            "technical": {"stance": f"{tech_label} (RSI {rsi:.1f})", "score": round(tech_score, 2)},
            "equity": {"stance": eq_rec, "score": round(eq_score, 2)},
            "risk": {"stance": risk_label, "score": round(risk_score, 2)},
        }
        scores = [v["score"] for v in stances.values()]
        mean_signal = float(np.mean(scores))
        std_signal = float(np.std(scores, ddof=0))
        # Disagreement index scaled 0..1 (std of signals in [-1, 1] has max 1.0)
        disagreement_idx = round(std_signal, 3)

        rows.append({
            "ticker": tkr,
            "company_name": prof["company_name"],
            "sector": prof["sector"],
            "disagreement_index": disagreement_idx,
            "consensus_mean": round(mean_signal, 3),
            "status": "high_conflict" if disagreement_idx >= 0.45 else ("moderate_conflict" if disagreement_idx >= 0.30 else "aligned"),
            "agent_stances": stances,
        })
    return sorted(rows, key=lambda r: r["disagreement_index"], reverse=True)


def ex_ante_ex_post_bias(raw_positions: list, cash: float) -> dict:
    """
    Computes the Ex-Ante vs Ex-Post Volatility Bias Statistic (R-P2-4):
      z_t = r_t / sigma_hat_{t-1}
      bias_stat = std(z_t) over the 252 out-of-sample days.
    Unbiased = 1.0; flagged if outside [0.80, 1.20].
    """
    if not raw_positions:
        return {
            "bias_statistic": 1.0,
            "status": "calibrated",
            "band_low": 0.80,
            "band_high": 1.20,
            "ex_ante_vol_ann_pct": 0.0,
            "ex_post_vol_ann_pct": 0.0,
            "ratio_ex_post_to_ex_ante": 1.0,
            "observations": 0,
            "series": [],
        }

    s = proforma_series(raw_positions, cash)
    returns = np.asarray(s["returns"], dtype=float)
    dates = s["dates"][1:]
    w = BACKTEST_WINDOW  # 252

    z_scores = []
    rolling_series = []
    for t in range(w, len(returns)):
        train = returns[t - w : t]
        sigma_hat = float(np.std(train, ddof=1))
        r_t = float(returns[t])
        if sigma_hat > 1e-9:
            z_scores.append(r_t / sigma_hat)
        # Also compute 21-day realized vol vs ex-ante vol every 5 days for charting
        if (t - w) % 5 == 0 or t == len(returns) - 1:
            realized_21d = float(np.std(returns[max(0, t - 20) : t + 1], ddof=1)) * math.sqrt(252) * 100.0
            ex_ante_ann = sigma_hat * math.sqrt(252) * 100.0
            rolling_series.append({
                "date": dates[t],
                "ex_ante_vol_pct": round(ex_ante_ann, 2),
                "realized_21d_vol_pct": round(realized_21d, 2),
            })

    z_arr = np.asarray(z_scores, dtype=float)
    bias_stat = round(float(np.std(z_arr, ddof=1)), 4) if len(z_arr) > 1 else 1.0
    oos_returns = returns[w:]
    ex_post_ann_pct = round(float(np.std(oos_returns, ddof=1) * math.sqrt(252) * 100.0), 2)
    latest_ex_ante_ann_pct = round(float(np.std(returns[-w:], ddof=1) * math.sqrt(252) * 100.0), 2)

    if bias_stat > 1.20:
        status = "under_predicting_risk"
    elif bias_stat < 0.80:
        status = "over_predicting_risk"
    else:
        status = "calibrated"

    return {
        "bias_statistic": bias_stat,
        "status": status,
        "within_band": 0.80 <= bias_stat <= 1.20,
        "band_low": 0.80,
        "band_high": 1.20,
        "ex_ante_vol_ann_pct": latest_ex_ante_ann_pct,
        "ex_post_vol_ann_pct": ex_post_ann_pct,
        "ratio_ex_post_to_ex_ante": round(ex_post_ann_pct / latest_ex_ante_ann_pct, 3) if latest_ex_ante_ann_pct > 0 else 1.0,
        "mean_z": round(float(np.mean(z_arr)), 4) if len(z_arr) else 0.0,
        "observations": len(z_arr),
        "series": rolling_series,
    }


def model_risk_dashboard(raw_positions: list = None, cash: float = 0.0) -> dict:
    """
    Aggregates per-agent quality scores, rolling trend, guardrail rejection rate,
    numeric mismatch / hallucination count, kill-switch & degradation state,
    cross-agent disagreement index, and ex-ante vs ex-post vol bias statistic.
    """
    _ensure_model_risk_seeded()

    controls_rows = query("SELECT * FROM agent_model_risk_controls ORDER BY agent_name").rows
    controls_by_agent = {r["agent_name"]: dict(r) for r in controls_rows}

    eval_rows = query(
        """SELECT id, agent_name, ticker, faithfulness_score, consistency_score, completeness_score,
                  overall_quality_score, grade, guardrails_passed, hallucinations_detected, warnings, created_at
           FROM agent_evaluations
           ORDER BY id DESC
           LIMIT 250"""
    ).rows

    by_agent_evals = {a[0]: [] for a in ALL_AGENTS}
    for r in eval_rows:
        ag = r["agent_name"]
        if ag in by_agent_evals:
            by_agent_evals[ag].append(dict(r))

    agents_list = []
    degraded_or_killed = []

    for agent_name, label, description in ALL_AGENTS:
        ctrl = controls_by_agent.get(agent_name, {
            "enabled": True,
            "kill_switch": False,
            "forced_degraded": False,
            "min_quality_threshold": 0.70,
            "reason": None,
        })
        evals = by_agent_evals.get(agent_name, [])
        latest = evals[0] if evals else {}
        threshold = float(ctrl.get("min_quality_threshold") or 0.70)
        forced_degraded = bool(ctrl.get("forced_degraded", False))

        # If forced_degraded is active and a recent evaluation was below threshold, surface that degraded evaluation
        if forced_degraded:
            low_eval = next((x for x in evals if float(x.get("overall_quality_score") or 1.0) < threshold), latest)
            latest = low_eval or latest

        latest_quality = float(latest.get("overall_quality_score") or 0.95)
        latest_faith = float(latest.get("faithfulness_score") or 0.95)
        latest_cons = float(latest.get("consistency_score") or 0.95)
        latest_comp = float(latest.get("completeness_score") or 0.95)
        latest_grade = str(latest.get("grade") or "PASS")

        total_runs = len(evals)
        avg_quality = round(float(np.mean([float(x.get("overall_quality_score") or 0.95) for x in evals])), 3) if evals else 0.95
        guardrail_rejections = sum(1 for x in evals if not x.get("guardrails_passed", True))
        rejection_rate_pct = round(guardrail_rejections / total_runs * 100.0, 1) if total_runs > 0 else 0.0
        numeric_mismatches = sum(int(x.get("hallucinations_detected") or 0) for x in evals)

        kill_switch = bool(ctrl.get("kill_switch", False)) or not bool(ctrl.get("enabled", True))
        quality_breach = latest_quality < threshold or latest_grade == "FAIL"

        if kill_switch:
            status = "killed"
            status_reason = ctrl.get("reason") or "Manual kill-switch engaged by Risk Officer"
        elif forced_degraded or quality_breach:
            status = "degraded"
            status_reason = (
                ctrl.get("reason")
                if forced_degraded and ctrl.get("reason")
                else f"Quality score ({latest_quality:.2f}) fell below minimum threshold ({threshold:.2f})"
            )
        else:
            status = "healthy"
            status_reason = "Passing all semantic & numeric guardrails"

        if status in ("killed", "degraded"):
            degraded_or_killed.append({
                "agent_name": agent_name,
                "label": label,
                "status": status,
                "latest_quality_score": round(latest_quality, 2),
                "threshold": round(threshold, 2),
                "reason": status_reason,
            })

        history_spark = [
            {
                "id": x["id"],
                "ticker": x["ticker"],
                "overall_quality_score": float(x.get("overall_quality_score") or 0.0),
                "faithfulness_score": float(x.get("faithfulness_score") or 0.0),
                "grade": x.get("grade") or "PASS",
                "hallucinations_detected": int(x.get("hallucinations_detected") or 0),
                "created_at": str(x.get("created_at", "")),
            }
            for x in reversed(evals[:10])
        ]

        agents_list.append({
            "agent_name": agent_name,
            "label": label,
            "description": description,
            "status": status,
            "status_reason": status_reason,
            "enabled": bool(ctrl.get("enabled", True)),
            "kill_switch": bool(ctrl.get("kill_switch", False)),
            "forced_degraded": forced_degraded,
            "min_quality_threshold": round(threshold, 2),
            "latest_quality_score": round(latest_quality, 2),
            "latest_faithfulness_score": round(latest_faith, 2),
            "latest_consistency_score": round(latest_cons, 2),
            "latest_completeness_score": round(latest_comp, 2),
            "latest_grade": latest_grade,
            "avg_quality_score": round(avg_quality, 2),
            "total_runs": total_runs,
            "guardrail_rejection_rate_pct": rejection_rate_pct,
            "numeric_mismatches_count": numeric_mismatches,
            "history": history_spark,
            "updated_at": str(ctrl.get("updated_at", "")),
        })

    tickers = [p["ticker"].strip().upper() for p in (raw_positions or [])] or ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]
    disagreement = compute_disagreement_index(tickers)
    vol_bias = ex_ante_ex_post_bias(raw_positions or [], cash)

    audit_rows = query(
        "SELECT id, category, target, action, details, actor, created_at FROM risk_audit_log ORDER BY id DESC LIMIT 30"
    ).rows
    audit_log = [
        {
            **dict(r),
            "details": json.loads(r["details"]) if isinstance(r.get("details"), str) else r.get("details"),
            "created_at": str(r["created_at"]),
        }
        for r in audit_rows
    ]

    banner = None
    if degraded_or_killed:
        names = ", ".join(f"{d['label']} ({d['status'].upper()}: {d['latest_quality_score']:.2f})" for d in degraded_or_killed)
        banner = (
            f"MODEL RISK ALERT: {len(degraded_or_killed)} agent(s) excluded from synthesis [{names}]. "
            "Downstream recommendations operate in degraded mode with reduced conviction cap."
        )

    return {
        "summary": {
            "total_agents": len(agents_list),
            "healthy_count": sum(1 for a in agents_list if a["status"] == "healthy"),
            "degraded_count": sum(1 for a in agents_list if a["status"] == "degraded"),
            "killed_count": sum(1 for a in agents_list if a["status"] == "killed"),
            "active_banner": banner,
        },
        "agents": agents_list,
        "degraded_agents": degraded_or_killed,
        "disagreement_index": disagreement,
        "volatility_bias": vol_bias,
        "audit_log": audit_log,
        "_provenance": {
            "source": "agent_evaluations + agent_model_risk_controls + proforma_series_504d",
            "method": "Agent degraded when overall_quality_score < min_quality_threshold (0.70) or kill_switch=True; "
                      "Disagreement Index = std(directional_stances in [-1, 1]); Vol Bias = std(r_t / sigma_hat_{t-1})",
        },
    }


def set_agent_control(
    agent_name: str,
    kill_switch: bool = None,
    forced_degraded: bool = None,
    enabled: bool = None,
    min_quality_threshold: float = None,
    reason: str = None,
    actor: str = "risk_officer",
) -> dict:
    """Updates kill-switch, degradation flag, or quality threshold for an agent and logs to risk_audit_log."""
    _ensure_model_risk_seeded()
    valid_names = {a[0] for a in ALL_AGENTS}
    if agent_name not in valid_names:
        raise ValueError(f"Unknown agent '{agent_name}'. Valid agents: {sorted(valid_names)}")

    cur = query("SELECT * FROM agent_model_risk_controls WHERE agent_name = %s", [agent_name]).rows[0]
    new_enabled = cur["enabled"] if enabled is None else bool(enabled)
    new_kill = cur["kill_switch"] if kill_switch is None else bool(kill_switch)
    new_deg = cur["forced_degraded"] if forced_degraded is None else bool(forced_degraded)
    new_thresh = float(cur["min_quality_threshold"]) if min_quality_threshold is None else float(min_quality_threshold)
    new_reason = reason if reason is not None else cur["reason"]

    query(
        """UPDATE agent_model_risk_controls
           SET enabled = %s, kill_switch = %s, forced_degraded = %s, min_quality_threshold = %s,
               reason = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
           WHERE agent_name = %s""",
        [new_enabled, new_kill, new_deg, new_thresh, new_reason, actor, agent_name],
    )

    action = "KILL_SWITCH_ON" if new_kill else ("FORCE_DEGRADED" if new_deg else "RESTORE_HEALTHY")
    details = {
        "enabled": new_enabled,
        "kill_switch": new_kill,
        "forced_degraded": new_deg,
        "min_quality_threshold": new_thresh,
        "reason": new_reason,
    }
    query(
        """INSERT INTO risk_audit_log (category, target, action, details, actor)
           VALUES ('model_risk', %s, %s, %s::jsonb, %s)""",
        [agent_name, action, json.dumps(details), actor],
    )
    return details


def simulate_agent_degradation(
    agent_name: str,
    simulated_quality_score: float = 0.52,
    ticker: str = "AAPL",
    restore: bool = False,
    actor: str = "risk_officer",
) -> dict:
    """
    Inserts a synthetic evaluation record (either degraded < 0.70 or restored >= 0.95)
    into agent_evaluations and updates agent_model_risk_controls + risk_audit_log so
    testers can deterministically verify automatic degradation and restoration.
    """
    _ensure_model_risk_seeded()
    valid_names = {a[0] for a in ALL_AGENTS}
    if agent_name not in valid_names:
        raise ValueError(f"Unknown agent '{agent_name}'. Valid agents: {sorted(valid_names)}")

    if restore:
        score = 0.96
        grade = "PASS"
        guardrails = True
        hallucinations = 0
        warnings = []
        set_agent_control(agent_name, kill_switch=False, forced_degraded=False, enabled=True,
                          reason="Restored to healthy after model-risk test", actor=actor)
        action = "RESTORE_EVALUATION"
    else:
        score = round(float(simulated_quality_score), 2)
        grade = "FAIL" if score < 0.70 else "WARN"
        guardrails = score >= 0.70
        hallucinations = 2 if score < 0.70 else 0
        warnings = [f"Simulated model degradation: quality score {score:.2f} below 0.70 threshold"]
        query(
            """UPDATE agent_model_risk_controls
               SET forced_degraded = %s, reason = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
               WHERE agent_name = %s""",
            [score < 0.70, warnings[0], actor, agent_name],
        )
        action = "SIMULATE_DEGRADATION"

    query(
        """INSERT INTO agent_evaluations
           (agent_name, ticker, faithfulness_score, consistency_score, completeness_score,
            overall_quality_score, grade, guardrails_passed, hallucinations_detected, warnings)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        [agent_name, ticker.upper(), score, score, score, score, grade, guardrails, hallucinations, json.dumps(warnings)],
    )
    query(
        """INSERT INTO risk_audit_log (category, target, action, details, actor)
           VALUES ('model_risk', %s, %s, %s::jsonb, %s)""",
        [agent_name, action, json.dumps({"ticker": ticker.upper(), "simulated_quality_score": score, "grade": grade}), actor],
    )
    return {"agent_name": agent_name, "simulated_quality_score": score, "grade": grade, "restored": restore}


def get_degraded_agents_for_synthesis() -> dict:
    """
    Lightweight helper called by POST /analyse/{ticker} before synthesizing the final report.
    Returns any killed or degraded agents and the model_risk_banner string.
    """
    try:
        dash = model_risk_dashboard()
        return {
            "degraded_agents": dash["degraded_agents"],
            "model_risk_banner": dash["summary"]["active_banner"],
        }
    except Exception:
        return {"degraded_agents": [], "model_risk_banner": None}


# ---------------------------------------------------------------------------
# RSK-014: Executive Morning Risk Tear Sheet & Export (R-P2-3, R-P2-5)
# ---------------------------------------------------------------------------
def morning_tear_sheet(portfolio_id: int, portfolio: dict, raw_positions: list, limits: list) -> dict:
    """
    Builds the single-page Executive Morning Risk Tear Sheet combining:
    - Risk Health Score (0-100) with explicit itemized deductions
    - NAV, exposures, DoD changes vs yesterday
    - Open hard/soft breaches & top 5 closest-to-breach limits
    - VaR / ES (95% & 99%, 1d & 10d) + 5d VaR trend + Kupiec backtest traffic light
    - Top 5 worst stress scenarios
    - Liquidity horizon summary & LVaR
    - Top 3 Euler risk contributors
    - Actionable SPY & Sector ETF hedge summary
    - AI Model-Risk health summary
    """
    cash = float(portfolio["cash"])
    benchmark = portfolio.get("benchmark") or "SPY"
    holdings = calculate_portfolio_holdings(raw_positions, cash)
    positions = holdings["positions"]
    nav = holdings["nav"]

    # 1. Limits & Breaches
    lim_metrics = compute_limit_metrics(raw_positions, cash, benchmark)
    eval_rows = evaluate_limits(limits, lim_metrics)
    active_breaches = breach_items(eval_rows)
    closest_limits = sorted(
        [r for r in eval_rows if r.get("utilisation_pct") is not None],
        key=lambda r: float(r["utilisation_pct"]),
        reverse=True,
    )[:5]

    # 2. Historical Risk Series (for DoD changes & 5d VaR trend)
    hist = risk_history(raw_positions, cash)
    hist_rows = hist.get("rows", [])
    today_row = hist_rows[-1] if hist_rows else {}
    yest_row = hist_rows[-2] if len(hist_rows) >= 2 else today_row

    dod = {
        "as_of_today": today_row.get("date"),
        "as_of_yesterday": yest_row.get("date"),
        "nav_today": round(float(today_row.get("nav", nav)), 2),
        "nav_yesterday": round(float(yest_row.get("nav", nav)), 2),
        "nav_dod_usd": round(float(today_row.get("nav", nav)) - float(yest_row.get("nav", nav)), 2),
        "nav_dod_pct": round(
            (float(today_row.get("nav", nav)) - float(yest_row.get("nav", nav))) / float(yest_row.get("nav", nav)) * 100.0, 2
        ) if float(yest_row.get("nav", nav)) > 0 else 0.0,
        "vol_exante_today_pct": round(float(today_row.get("vol_exante", 0.0)) * 100.0, 2),
        "vol_exante_dod_bps": round((float(today_row.get("vol_exante", 0.0)) - float(yest_row.get("vol_exante", 0.0))) * 10000.0, 1),
        "var95_today_pct": round(float(today_row.get("var95", 0.0)) * 100.0, 2),
        "var95_dod_bps": round((float(today_row.get("var95", 0.0)) - float(yest_row.get("var95", 0.0))) * 10000.0, 1),
        "drawdown_today_pct": round(float(today_row.get("drawdown", 0.0)) * 100.0, 2),
        "hwm_usd": round(float(today_row.get("hwm", nav)), 2),
    }

    var_5d_trend = [
        {
            "date": r["date"],
            "nav": r["nav"],
            "var95_pct": round(float(r["var95"]) * 100.0, 2),
            "es975_pct": round(float(r["es975"]) * 100.0, 2),
            "vol_exante_pct": round(float(r["vol_exante"]) * 100.0, 2),
            "drawdown_pct": round(float(r["drawdown"]) * 100.0, 2),
        }
        for r in hist_rows[-5:]
    ]

    # 3. VaR / ES Table (95% & 99%, 1d & 10d) + Kupiec Backtest Traffic Light
    def _fmt_var_methods(rep: dict) -> dict:
        pm = rep.get("portfolio", {}).get("methods", {})
        return {
            m: {
                "var_pct": round(float(v.get("var", 0.0)) * 100.0, 2),
                "es_pct": round(float(v.get("es", 0.0)) * 100.0, 2),
                "var_usd": round(float(v.get("var_usd", 0.0)), 2),
                "es_usd": round(float(v.get("es_usd", 0.0)), 2),
            }
            for m, v in pm.items()
        }

    var95_1d = _fmt_var_methods(var_report(raw_positions, cash, 0.95, 1))
    var99_1d = _fmt_var_methods(var_report(raw_positions, cash, 0.99, 1))
    var99_10d = _fmt_var_methods(var_report(raw_positions, cash, 0.99, 10))

    s_pro = proforma_series(raw_positions, cash)
    bt99 = backtest_series(s_pro["returns"], s_pro["dates"][1:], 0.99) if raw_positions else {}
    param_bt = bt99.get("parametric", {"exceptions": 0, "zone": "green", "kupiec_p": 1.0})

    # 4. Top 5 Worst Stress Scenarios
    hwm_val = dod["hwm_usd"]
    stress_results = [run_scenario(raw_positions, cash, sc, limits, hwm_val) for sc in BUILTIN_SCENARIOS]
    top5_stress = sorted(stress_results, key=lambda r: float(r.get("pnl_usd", 0.0)))[:5]
    rev_stress = reverse_stress(raw_positions, cash, 10.0, hwm_val, 12.0) if raw_positions else None

    # 5. Liquidity Summary & LVaR
    liq = liquidity_risk(raw_positions, cash, 0.20, impact_coeff=1.0)
    ladder_by_day = {l["days"]: l["cum_pct_nav"] for l in liq.get("ladder", [])}
    max_dtl = next((l.get("max_days_to_liquidate", 0.0) for l in liq.get("ladder", []) if l.get("days") == "all"), 0.0)
    illiquid_cnt = sum(1 for p in liq.get("positions", []) if p.get("flag_over_10pct_adv") or float(p.get("days_to_liquidate", 0.0)) > 5.0)
    lvar99 = liq.get("lvar", {}).get("parametric_99") or liq.get("lvar", {}).get("historical_99") or {}
    lvar_usd = float(lvar99.get("lvar_usd", 0.0))
    lvar_pct_nav = float(lvar99.get("lvar_pct", 0.0))
    base_var_usd = float(lvar99.get("var_usd", 0.0))
    lvar_ratio = round(lvar_usd / base_var_usd, 3) if base_var_usd > 0 else 1.0

    # 6. Risk Attribution (Top 3 Euler Risk Contributors)
    attr = risk_attribution(raw_positions, cash, 0.99)
    top3_contributors = sorted(
        attr.get("positions", []),
        key=lambda p: float(p.get("pct_contribution", 0.0)),
        reverse=True,
    )[:3]

    # 7. Hedge Recommendations
    hedges = hedge_calculator(raw_positions, cash, limits)

    # 8. AI Model-Risk Summary
    model_risk = model_risk_dashboard(raw_positions, cash)

    # 9. Transparent Risk Health Score (0-100)
    deductions = []
    score = 100

    hard_cnt = sum(1 for b in active_breaches if b["severity"] == "hard")
    soft_cnt = sum(1 for b in active_breaches if b["severity"] == "soft")
    if hard_cnt > 0:
        pts = min(45, hard_cnt * 15)
        score -= pts
        deductions.append({"category": "Hard Limit Breaches", "points": -pts, "reason": f"{hard_cnt} active hard breach(es) (-15 pts each)"})
    if soft_cnt > 0:
        pts = min(15, soft_cnt * 5)
        score -= pts
        deductions.append({"category": "Soft Limit Warnings", "points": -pts, "reason": f"{soft_cnt} active soft breach(es) (-5 pts each)"})

    bt_zone = param_bt.get("zone", "green")
    if bt_zone == "red":
        score -= 25
        deductions.append({"category": "VaR Backtest Zone", "points": -25, "reason": f"Basel RED zone ({param_bt.get('exceptions')} exceptions in 252d)"})
    elif bt_zone == "amber":
        score -= 10
        deductions.append({"category": "VaR Backtest Zone", "points": -10, "reason": f"Basel AMBER zone ({param_bt.get('exceptions')} exceptions in 252d)"})

    dd_mag = abs(dod["drawdown_today_pct"])
    if dd_mag >= 1.0:
        pts = min(15, int(round(dd_mag)))
        score -= pts
        deductions.append({"category": "Drawdown from HWM", "points": -pts, "reason": f"Current drawdown {dod['drawdown_today_pct']:.2f}% from HWM (-1 pt per 1%)"})

    if lvar_ratio > 1.25:
        score -= 10
        deductions.append({"category": "Liquidity Tail Markup", "points": -10, "reason": f"LVaR/VaR ratio {lvar_ratio:.2f}x > 1.25x"})

    deg_cnt = model_risk["summary"]["degraded_count"] + model_risk["summary"]["killed_count"]
    if deg_cnt > 0:
        pts = min(15, deg_cnt * 5)
        score -= pts
        deductions.append({"category": "AI Model Risk", "points": -pts, "reason": f"{deg_cnt} degraded/killed AI agent(s) (-5 pts each)"})

    score = max(0, min(100, score))
    health_grade = "A (Strong)" if score >= 85 else ("B (Acceptable)" if score >= 70 else ("C (Elevated Risk)" if score >= 55 else "D (Critical Action Required)"))

    eval_by_metric = {r["metric"]: r for r in eval_rows}
    enriched_breaches = [
        {
            **b,
            "label": eval_by_metric.get(b["metric"], {}).get("label", b["metric"]),
            "utilisation_pct": eval_by_metric.get(b["metric"], {}).get("utilisation_pct", 100.0),
        }
        for b in active_breaches
    ]

    return {
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolio["name"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "health_score": {
            "score": score,
            "max_score": 100,
            "grade": health_grade,
            "deductions": deductions,
            "formula": "100 - 15*(hard_breaches) - 5*(soft_breaches) - backtest_penalty(0/10/25) - round(|DD%|) - 5*(degraded_agents)",
        },
        "overview": {
            "nav": nav,
            "cash": round(cash, 2),
            "cash_weight_pct": holdings["cash_weight_pct"],
            "gross_exposure_pct": holdings["gross_exposure_pct"],
            "net_exposure_pct": holdings["net_exposure_pct"],
            "portfolio_beta": round(lim_metrics["values"]["portfolio_beta"], 2),
            "ex_ante_vol_pct": round(lim_metrics["values"]["ex_ante_vol_pct"], 2),
            "positions_count": holdings["positions_count"],
        },
        "day_over_day": dod,
        "breaches": {
            "hard_count": hard_cnt,
            "soft_count": soft_cnt,
            "active_items": enriched_breaches,
            "top5_utilisation": [
                {
                    "metric": r["metric"],
                    "label": r["label"],
                    "value": r["value"],
                    "hard_limit": r["hard_limit"],
                    "utilisation_pct": r["utilisation_pct"],
                    "status": r["status"],
                    "worst_entity": r["breaching"][0]["scope"] if r.get("breaching") else "Portfolio",
                }
                for r in closest_limits
            ],
        },
        "var_es_summary": {
            "var95_1d": var95_1d,
            "var99_1d": var99_1d,
            "var99_10d": var99_10d,
            "trend_5d": var_5d_trend,
            "backtest_99": {
                "parametric": bt99.get("parametric"),
                "historical": bt99.get("historical"),
                "cornish_fisher": bt99.get("cornish_fisher"),
            },
        },
        "top5_stress_scenarios": [
            {
                "key": s.get("key"),
                "name": s["name"],
                "kind": s["kind"],
                "pnl_usd": s["pnl_usd"],
                "pnl_pct": s["pnl_pct"],
                "worst_position": s["positions"][0]["ticker"] if s.get("positions") else None,
                "new_breaches_count": len(s.get("breaches_after", [])),
            }
            for s in top5_stress
        ],
        "reverse_stress": rev_stress,
        "liquidity_summary": {
            "pct_nav_liquid_1d": round(float(ladder_by_day.get(1, 100.0)), 2),
            "pct_nav_liquid_5d": round(float(ladder_by_day.get(5, 100.0)), 2),
            "max_days_to_liquidate": round(float(max_dtl), 4),
            "illiquid_positions_count": illiquid_cnt,
            "lvar_99_1d_usd": round(lvar_usd, 2),
            "lvar_99_1d_pct_nav": round(lvar_pct_nav, 2),
            "lvar_to_var_ratio": lvar_ratio,
        },
        "top3_risk_contributors": top3_contributors,
        "hedge_summary": {
            "spy_beta_neutral": hedges["beta_hedge"]["trade"],
            "post_spy_beta": hedges["beta_hedge"]["after"]["portfolio_beta"],
            "sector_hedges": [
                {
                    "sector": sh["sector"],
                    "status": sh["status"],
                    "current_weight_pct": sh["current_weight_pct"],
                    "hard_limit_pct": sh["hard_limit_pct"],
                    "etf_trade": sh["etf_hedge"]["trade"],
                    "post_sector_weight_pct": sh["etf_hedge"]["post_sector_weight_pct"],
                }
                for sh in hedges["sector_hedges"]
                if sh["status"] != "ok"
            ],
            "drawdown_status": hedges["drawdown_control"]["status"],
        },
        "model_risk_summary": {
            "healthy_count": model_risk["summary"]["healthy_count"],
            "degraded_count": model_risk["summary"]["degraded_count"],
            "killed_count": model_risk["summary"]["killed_count"],
            "active_banner": model_risk["summary"]["active_banner"],
            "vol_bias_statistic": model_risk["volatility_bias"]["bias_statistic"],
            "vol_bias_status": model_risk["volatility_bias"]["status"],
            "highest_disagreement": model_risk["disagreement_index"][0] if model_risk["disagreement_index"] else None,
        },
        "_provenance": {
            "basis": "pro-forma current holdings, 252d estimation window",
            "source": "MarketPulse Quantitative Risk Engine (RSK-001..RSK-014)",
        },
    }


def tear_sheet_csv(sheet: dict) -> str:
    """Serializes the Morning Risk Tear Sheet into a clean, multi-section institutional CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["MARKETPULSE EXECUTIVE MORNING RISK TEAR SHEET"])
    w.writerow(["Portfolio ID", sheet["portfolio_id"], "Portfolio Name", sheet["portfolio_name"], "Generated At", sheet["generated_at"]])
    w.writerow(["Risk Health Score", f"{sheet['health_score']['score']}/100", "Grade", sheet["health_score"]["grade"]])
    w.writerow([])

    w.writerow(["SECTION 1: PORTFOLIO OVERVIEW & DAY-OVER-DAY"])
    ov = sheet["overview"]
    dod = sheet["day_over_day"]
    w.writerow(["Metric", "Current Value", "DoD Change / Note"])
    w.writerow(["NAV (USD)", f"${ov['nav']:,.2f}", f"${dod['nav_dod_usd']:+,.2f} ({dod['nav_dod_pct']:+.2f}%)"])
    w.writerow(["Cash (USD)", f"${ov['cash']:,.2f}", f"{ov['cash_weight_pct']:.2f}% of NAV"])
    w.writerow(["Gross Exposure (%)", f"{ov['gross_exposure_pct']:.2f}%", f"Net Exposure: {ov['net_exposure_pct']:.2f}%"])
    w.writerow(["Portfolio Beta (vs SPY)", f"{ov['portfolio_beta']:.2f}", "Unitless"])
    w.writerow(["Ex-Ante Volatility (Ann.)", f"{ov['ex_ante_vol_pct']:.2f}%", f"{dod['vol_exante_dod_bps']:+.1f} bps DoD"])
    w.writerow(["Drawdown from 252d HWM", f"{dod['drawdown_today_pct']:.2f}%", f"HWM: ${dod['hwm_usd']:,.2f}"])
    w.writerow([])

    w.writerow(["SECTION 2: HEALTH SCORE DEDUCTIONS"])
    w.writerow(["Category", "Points", "Reason"])
    for d in sheet["health_score"]["deductions"]:
        w.writerow([d["category"], d["points"], d["reason"]])
    if not sheet["health_score"]["deductions"]:
        w.writerow(["None", 0, "All risk checks green"])
    w.writerow([])

    w.writerow(["SECTION 3: ACTIVE LIMIT BREACHES & TOP UTILISATION"])
    w.writerow(["Metric", "Scope", "Current Value", "Limit", "Utilisation %", "Status"])
    for b in sheet["breaches"]["active_items"]:
        w.writerow([b["label"], b["scope"] or "Portfolio", b["value"], b["limit_value"], f"{b['utilisation_pct']:.1f}%", b["severity"].upper()])
    for u in sheet["breaches"]["top5_utilisation"]:
        w.writerow([u["label"], u.get("worst_entity") or "Portfolio", u["value"], u["hard_limit"], f"{u['utilisation_pct']:.1f}%", u["status"]])
    w.writerow([])

    w.writerow(["SECTION 4: VaR & EXPECTED SHORTFALL SUMMARY"])
    w.writerow(["Horizon / Confidence", "Method", "VaR (% NAV)", "VaR (USD)", "ES (% NAV)", "ES (USD)"])
    for label, key in [("95% 1-Day", "var95_1d"), ("99% 1-Day", "var99_1d"), ("99% 10-Day", "var99_10d")]:
        for m, vals in sheet["var_es_summary"][key].items():
            w.writerow([label, m, f"{vals['var_pct']:.2f}%", f"${vals['var_usd']:,.2f}", f"{vals['es_pct']:.2f}%", f"${vals['es_usd']:,.2f}"])
    w.writerow([])

    w.writerow(["SECTION 5: TOP 5 WORST STRESS SCENARIOS"])
    w.writerow(["Scenario", "Kind", "P&L (USD)", "P&L (% NAV)", "Worst Position", "Breaches After Shock"])
    for s in sheet["top5_stress_scenarios"]:
        w.writerow([s["name"], s["kind"], f"${s['pnl_usd']:,.2f}", f"{s['pnl_pct']:.2f}%", s["worst_position"], s["new_breaches_count"]])
    w.writerow([])

    w.writerow(["SECTION 6: TOP 3 EULER RISK CONTRIBUTORS"])
    w.writerow(["Ticker", "Sector", "Weight (% NAV)", "VaR Share (%)", "Component VaR 99% (USD)"])
    for c in sheet["top3_risk_contributors"]:
        w.writerow([c["ticker"], c["sector"], f"{c['weight_pct']:.2f}%", f"{c['pct_contribution']:.2f}%", f"${c['component_var_usd']:,.2f}"])
    w.writerow([])

    w.writerow(["SECTION 7: RECOMMENDED HEDGES & AI MODEL RISK"])
    spy_h = sheet["hedge_summary"]["spy_beta_neutral"]
    w.writerow(["Beta-Neutral Hedge", f"{spy_h['action']} {spy_h['qty']} SPY @ ${spy_h['price']}", f"Notional ${spy_h['notional_usd']:,.2f}", f"Post-Hedge Beta: {sheet['hedge_summary']['post_spy_beta']}"])
    for sh in sheet["hedge_summary"]["sector_hedges"]:
        tr = sh["etf_trade"]
        w.writerow([f"Sector Hedge ({sh['sector']})", f"{tr['action']} {tr['qty']} {tr['ticker']} @ ${tr['price']}", f"Notional ${tr['notional_usd']:,.2f}", f"Post-Hedge Sector Wt: {sh['post_sector_weight_pct']:.2f}%"])
    mr = sheet["model_risk_summary"]
    w.writerow(["AI Model Risk", f"Healthy: {mr['healthy_count']}, Degraded: {mr['degraded_count']}, Killed: {mr['killed_count']}", f"Vol Bias Stat: {mr['vol_bias_statistic']} ({mr['vol_bias_status']})", mr["active_banner"] or "All agents nominal"])

    return buf.getvalue()


def tear_sheet_html(sheet: dict) -> str:
    """Renders a print-ready institutional HTML document for the Morning Risk Tear Sheet."""
    ov = sheet["overview"]
    dod = sheet["day_over_day"]
    hs = sheet["health_score"]
    liq = sheet["liquidity_summary"]
    mr = sheet["model_risk_summary"]

    deduction_rows = "".join(
        f"<tr><td>{d['category']}</td><td style='color:#dc2626;font-weight:700'>{d['points']}</td><td>{d['reason']}</td></tr>"
        for d in hs["deductions"]
    ) or "<tr><td colspan='3'>No deductions — all risk checks nominal</td></tr>"

    stress_rows = "".join(
        f"<tr><td>{s['name']}</td><td>{s['kind']}</td><td style='color:#dc2626;font-weight:600'>${s['pnl_usd']:,.2f}</td>"
        f"<td>{s['pnl_pct']:.2f}%</td><td>{s['worst_position']}</td><td>{s['new_breaches_count']}</td></tr>"
        for s in sheet["top5_stress_scenarios"]
    )

    rc_rows = "".join(
        f"<tr><td><strong>{c['ticker']}</strong></td><td>{c['sector']}</td><td>{c['weight_pct']:.2f}%</td>"
        f"<td>{c['pct_contribution']:.2f}%</td><td>${c['component_var_usd']:,.2f}</td></tr>"
        for c in sheet["top3_risk_contributors"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Morning Risk Tear Sheet — {sheet['portfolio_name']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #111827; margin: 24px; font-size: 12px; }}
  h1 {{ font-size: 18px; margin: 0 0 4px 0; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: #374151; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-top: 16px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #111827; padding-bottom: 10px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-top: 12px; }}
  .kpi {{ border: 1px solid #d1d5db; border-radius: 4px; padding: 8px; background: #f9fafb; }}
  .kpi-label {{ font-size: 10px; color: #6b7280; text-transform: uppercase; }}
  .kpi-val {{ font-size: 15px; font-weight: 700; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left; font-size: 11px; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  @media print {{ .no-print {{ display: none; }} body {{ margin: 10px; }} }}
</style>
</head>
<body>
  <div class="no-print" style="margin-bottom:12px;text-align:right;">
    <button onclick="window.print()" style="padding:6px 12px;background:#111827;color:#fff;border:none;border-radius:4px;cursor:pointer;">Print / Save as PDF</button>
  </div>
  <div class="header">
    <div>
      <h1>EXECUTIVE MORNING RISK TEAR SHEET — {sheet['portfolio_name']} (ID #{sheet['portfolio_id']})</h1>
      <div style="color:#4b5563;">As of {sheet['generated_at']} | Basis: {sheet['_provenance']['basis']}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:11px;color:#6b7280;">RISK HEALTH SCORE</div>
      <div style="font-size:22px;font-weight:800;">{hs['score']} / 100 <span style="font-size:13px;font-weight:600;">({hs['grade']})</span></div>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-label">NAV</div><div class="kpi-val">${ov['nav']:,.2f}</div><div>DoD: {dod['nav_dod_pct']:+.2f}%</div></div>
    <div class="kpi"><div class="kpi-label">Gross / Net</div><div class="kpi-val">{ov['gross_exposure_pct']:.1f}% / {ov['net_exposure_pct']:.1f}%</div><div>Cash: {ov['cash_weight_pct']:.1f}%</div></div>
    <div class="kpi"><div class="kpi-label">Portfolio Beta</div><div class="kpi-val">{ov['portfolio_beta']:.2f}</div><div>vs SPY</div></div>
    <div class="kpi"><div class="kpi-label">Ex-Ante Vol</div><div class="kpi-val">{ov['ex_ante_vol_pct']:.2f}%</div><div>DoD: {dod['vol_exante_dod_bps']:+.1f} bps</div></div>
    <div class="kpi"><div class="kpi-label">Drawdown (252d)</div><div class="kpi-val">{dod['drawdown_today_pct']:.2f}%</div><div>HWM: ${dod['hwm_usd']:,.0f}</div></div>
    <div class="kpi"><div class="kpi-label">5d Liquid NAV</div><div class="kpi-val">{liq['pct_nav_liquid_5d']:.1f}%</div><div>LVaR/VaR: {liq['lvar_to_var_ratio']:.2f}x</div></div>
  </div>

  <h2>1. Risk Health Score Breakdown</h2>
  <table><thead><tr><th>Category</th><th>Points</th><th>Detail</th></tr></thead><tbody>{deduction_rows}</tbody></table>

  <h2>2. Top 5 Stress Scenarios</h2>
  <table><thead><tr><th>Scenario</th><th>Kind</th><th>Stress P&amp;L ($)</th><th>Stress P&amp;L (% NAV)</th><th>Worst Name</th><th>New Breaches</th></tr></thead><tbody>{stress_rows}</tbody></table>

  <h2>3. Top 3 Euler Risk Contributors</h2>
  <table><thead><tr><th>Ticker</th><th>Sector</th><th>Capital Weight</th><th>Vol Risk Share</th><th>Component VaR 99% ($)</th></tr></thead><tbody>{rc_rows}</tbody></table>

  <h2>4. AI Model-Risk Governance Status</h2>
  <p>Healthy Agents: <strong>{mr['healthy_count']}</strong> | Degraded: <strong>{mr['degraded_count']}</strong> | Killed: <strong>{mr['killed_count']}</strong> | Ex-Ante/Ex-Post Vol Bias: <strong>{mr['vol_bias_statistic']} ({mr['vol_bias_status']})</strong></p>
</body>
</html>"""
