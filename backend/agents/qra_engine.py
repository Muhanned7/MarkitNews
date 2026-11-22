"""
Quantitative Research Analyst (QRA) Core Engine (QRA-001 through QRA-008)
=========================================================================
Implements:
- QRA-001: 100-ticker, 11-sector, 10-year (2,520d) research universe with
           GARCH(1,1)-t fat tails, 5 mock delistings, point-in-time quarterly
           fundamentals (report_date = period_end + 45d), and planted signals
           (planted_alpha_strong IC~0.05, planted_alpha_weak IC~0.02,
            planted_noise IC~0.00, planted_lookahead).
- QRA-002: Point-in-time research panel API (long format, CSV export,
           survivorship-free universe-by-date).
- QRA-003: Signal library (8 core + 4 planted = 12 signals) with 1/99%
           winsorisation, cross-sectional z-score, sector/beta neutralisation,
           and coverage tracking.
- QRA-004: Spearman Rank IC tear sheet, IC IR, Newey-West HAC t-stat,
           1d-126d IC decay curve, Q1-Q5 quantile returns & Q5-Q1 spread vs SPY,
           turnover, yearly IC, and 11-sector IC boxplot statistics.
- QRA-005: Configurable backtester (daily/weekly/monthly rebalance, equal/prop/vol
           weighting, long-only/long-short, position/sector caps, fixed bps +
           square-root market impact costs, 1-day lag lookahead guard).
- QRA-006: Reproducible experiment tracking (`research_runs` table, config_hash,
           side-by-side 2-4 run comparison, per-question trial counter).
- QRA-008: Automated Lookahead Bias & Leakage Scanner (point-in-time report_date
           linter + unlagged Corr(s_t, r_{t+1}) > 0.35 detector).
"""

import hashlib
import io
import json
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agents.mock_market_data import (
    ANCHOR_PROFILES,
    GARCH_ALPHA,
    GARCH_BETA,
    HISTORY_END_DATE,
    MARKET_ANNUAL_DRIFT,
    MARKET_ANNUAL_VOL,
    T_CLIP_SIGMA,
    T_DOF,
    _ticker_seed,
)

# ---------------------------------------------------------------------------
# Constants & 100-Ticker 11-Sector Universe Specification (QRA-001)
# ---------------------------------------------------------------------------
N_RESEARCH_DAYS = 2520  # 10 years of trading days (252 * 10)
CODE_VERSION = "qra-1.0.0"
DATA_VERSION = "mock100-10y-pit-v1"

GICS_11_SECTORS = [
    "Technology",
    "Healthcare",
    "Financials",
    "Consumer Discretionary",
    "Communication Services",
    "Industrials",
    "Consumer Staples",
    "Energy",
    "Utilities",
    "Real Estate",
    "Materials",
]

# Exactly 100 institutional tickers across 11 GICS sectors (including 5 mock delistings)
UNIVERSE_100_SPEC: List[Tuple[str, str, str]] = [
    # Technology (12)
    ("AAPL", "Apple Inc.", "Technology"),
    ("MSFT", "Microsoft Corporation", "Technology"),
    ("NVDA", "NVIDIA Corporation", "Technology"),
    ("AVGO", "Broadcom Inc.", "Technology"),
    ("ORCL", "Oracle Corporation", "Technology"),
    ("CRM", "Salesforce, Inc.", "Technology"),
    ("AMD", "Advanced Micro Devices, Inc.", "Technology"),
    ("ADBE", "Adobe Inc.", "Technology"),
    ("CSCO", "Cisco Systems, Inc.", "Technology"),
    ("ACN", "Accenture plc", "Technology"),
    ("IBM", "International Business Machines", "Technology"),
    ("INTC", "Intel Corporation", "Technology"),
    # Healthcare (10)
    ("LLY", "Eli Lilly and Company", "Healthcare"),
    ("UNH", "UnitedHealth Group Inc.", "Healthcare"),
    ("JNJ", "Johnson & Johnson", "Healthcare"),
    ("ABBV", "AbbVie Inc.", "Healthcare"),
    ("MRK", "Merck & Co., Inc.", "Healthcare"),
    ("TMO", "Thermo Fisher Scientific Inc.", "Healthcare"),
    ("ABT", "Abbott Laboratories", "Healthcare"),
    ("PFE", "Pfizer Inc.", "Healthcare"),
    ("DHR", "Danaher Corporation", "Healthcare"),
    ("AMGN", "Amgen Inc.", "Healthcare"),
    # Financials (10 - includes SVBQ, FRCB delistings)
    ("JPM", "JPMorgan Chase & Co.", "Financials"),
    ("V", "Visa Inc.", "Financials"),
    ("MA", "Mastercard Incorporated", "Financials"),
    ("BAC", "Bank of America Corporation", "Financials"),
    ("WFC", "Wells Fargo & Company", "Financials"),
    ("GS", "The Goldman Sachs Group, Inc.", "Financials"),
    ("MS", "Morgan Stanley", "Financials"),
    ("BLK", "BlackRock, Inc.", "Financials"),
    ("SVBQ", "SVB Financial Group (Delisted)", "Financials"),
    ("FRCB", "First Republic Bank (Delisted)", "Financials"),
    # Consumer Discretionary (10 - includes BBBYQ delisting)
    ("AMZN", "Amazon.com, Inc.", "Consumer Discretionary"),
    ("TSLA", "Tesla, Inc.", "Consumer Discretionary"),
    ("HD", "The Home Depot, Inc.", "Consumer Discretionary"),
    ("MCD", "McDonald's Corporation", "Consumer Discretionary"),
    ("NKE", "NIKE, Inc.", "Consumer Discretionary"),
    ("LOW", "Lowe's Companies, Inc.", "Consumer Discretionary"),
    ("SBUX", "Starbucks Corporation", "Consumer Discretionary"),
    ("TJX", "The TJX Companies, Inc.", "Consumer Discretionary"),
    ("BKNG", "Booking Holdings Inc.", "Consumer Discretionary"),
    ("BBBYQ", "Bed Bath & Beyond Inc. (Delisted)", "Consumer Discretionary"),
    # Communication Services (8)
    ("GOOGL", "Alphabet Inc.", "Communication Services"),
    ("META", "Meta Platforms, Inc.", "Communication Services"),
    ("NFLX", "Netflix, Inc.", "Communication Services"),
    ("DIS", "The Walt Disney Company", "Communication Services"),
    ("CMCSA", "Comcast Corporation", "Communication Services"),
    ("TMUS", "T-Mobile US, Inc.", "Communication Services"),
    ("VZ", "Verizon Communications Inc.", "Communication Services"),
    ("T", "AT&T Inc.", "Communication Services"),
    # Industrials (10)
    ("GE", "GE Aerospace", "Industrials"),
    ("CAT", "Caterpillar Inc.", "Industrials"),
    ("RTX", "RTX Corporation", "Industrials"),
    ("UNP", "Union Pacific Corporation", "Industrials"),
    ("HON", "Honeywell International Inc.", "Industrials"),
    ("DE", "Deere & Company", "Industrials"),
    ("BA", "The Boeing Company", "Industrials"),
    ("ADP", "Automatic Data Processing, Inc.", "Industrials"),
    ("LMT", "Lockheed Martin Corporation", "Industrials"),
    ("UPS", "United Parcel Service, Inc.", "Industrials"),
    # Consumer Staples (9 - includes RADQ delisting)
    ("PG", "The Procter & Gamble Company", "Consumer Staples"),
    ("COST", " Costco Wholesale Corporation", "Consumer Staples"),
    ("WMT", "Walmart Inc.", "Consumer Staples"),
    ("KO", "The Coca-Cola Company", "Consumer Staples"),
    ("PEP", "PepsiCo, Inc.", "Consumer Staples"),
    ("PM", "Philip Morris International Inc.", "Consumer Staples"),
    ("MDLZ", "Mondelez International, Inc.", "Consumer Staples"),
    ("CL", "Colgate-Palmolive Company", "Consumer Staples"),
    ("RADQ", "Rite Aid Corporation (Delisted)", "Consumer Staples"),
    # Energy (8)
    ("XOM", "Exxon Mobil Corporation", "Energy"),
    ("CVX", "Chevron Corporation", "Energy"),
    ("COP", "ConocoPhillips", "Energy"),
    ("SLB", "SLB", "Energy"),
    ("EOG", "EOG Resources, Inc.", "Energy"),
    ("MPC", "Marathon Petroleum Corporation", "Energy"),
    ("PSX", "Phillips 66", "Energy"),
    ("VLO", "Valero Energy Corporation", "Energy"),
    # Utilities (8)
    ("NEE", "NextEra Energy, Inc.", "Utilities"),
    ("SO", "The Southern Company", "Utilities"),
    ("DUK", "Duke Energy Corporation", "Utilities"),
    ("CEG", "Constellation Energy Corporation", "Utilities"),
    ("SRE", "Sempra", "Utilities"),
    ("AEP", "American Electric Power", "Utilities"),
    ("D", "Dominion Energy, Inc.", "Utilities"),
    ("EXC", "Exelon Corporation", "Utilities"),
    # Real Estate (7)
    ("PLD", "Prologis, Inc.", "Real Estate"),
    ("AMT", "American Tower Corporation", "Real Estate"),
    ("EQIX", "Equinix, Inc.", "Real Estate"),
    ("WELL", "Welltower Inc.", "Real Estate"),
    ("SPG", "Simon Property Group, Inc.", "Real Estate"),
    ("PSA", "Public Storage", "Real Estate"),
    ("O", "Realty Income Corporation", "Real Estate"),
    # Materials (8 - includes ENDPQ delisting)
    ("LIN", "Linde plc", "Materials"),
    ("SHW", "The Sherwin-Williams Company", "Materials"),
    ("FCX", "Freeport-McMoRan Inc.", "Materials"),
    ("APD", "Air Products and Chemicals, Inc.", "Materials"),
    ("ECL", "Ecolab Inc.", "Materials"),
    ("NEM", "Newmont Corporation", "Materials"),
    ("DOW", "Dow Inc.", "Materials"),
    ("ENDPQ", "Endo International plc (Delisted)", "Materials"),
]

# 5 Mock Delistings mid-history (day index in 0..2519 and terminal return)
MOCK_DELISTINGS: Dict[str, Dict[str, Any]] = {
    "ENDPQ": {"delist_idx": 1380, "terminal_return": -0.68, "reason": "Chapter 11 restructuring"},
    "SVBQ": {"delist_idx": 1525, "terminal_return": -0.84, "reason": "FDIC receivership / bank run"},
    "BBBYQ": {"delist_idx": 1560, "terminal_return": -0.79, "reason": "Voluntary liquidation"},
    "FRCB": {"delist_idx": 1566, "terminal_return": -0.76, "reason": "Regulatory seizure & sale"},
    "RADQ": {"delist_idx": 1685, "terminal_return": -0.64, "reason": "Court-supervised restructuring"},
}

SIGNAL_CATALOG: Dict[str, Dict[str, Any]] = {
    "planted_alpha_strong": {
        "name": "planted_alpha_strong",
        "label": "Planted Alpha — Strong (IC ≈ 0.05)",
        "category": "Planted Benchmark",
        "formula": "s_t = 0.052 * z_rank(r_{t->t+21}) + sqrt(1 - 0.052^2) * eps_perp",
        "lookback_days": 21,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": True,
        "target_ic": 0.05,
        "description": "Synthetic calibration signal with planted Spearman Rank IC of ~0.05 against 21-day forward returns.",
    },
    "planted_alpha_weak": {
        "name": "planted_alpha_weak",
        "label": "Planted Alpha — Weak (IC ≈ 0.02)",
        "category": "Planted Benchmark",
        "formula": "s_t = 0.021 * z_rank(r_{t->t+21}) + sqrt(1 - 0.021^2) * eps_perp",
        "lookback_days": 21,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": True,
        "target_ic": 0.02,
        "description": "Synthetic calibration signal with modest Spearman Rank IC of ~0.02 against 21-day forward returns.",
    },
    "planted_noise": {
        "name": "planted_noise",
        "label": "Planted Pure Noise (IC ≈ 0.00)",
        "category": "Planted Benchmark",
        "formula": "s_t = eps_t (orthogonal Gaussian noise, E[IC] = 0)",
        "lookback_days": 1,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": True,
        "target_ic": 0.0,
        "description": "Zero-skill benchmark signal built from pure noise orthogonalized to forward returns.",
    },
    "planted_lookahead": {
        "name": "planted_lookahead",
        "label": "Planted Lookahead Leak (Unlagged r_{t+1})",
        "category": "Planted Benchmark",
        "formula": "s_t = 0.85 * z(r_{t+1}) + 0.527 * eps_t (FUTURE LEAK)",
        "lookback_days": 1,
        "default_lag": 0,
        "uses_fundamentals": False,
        "is_planted": True,
        "target_ic": 0.80,
        "description": "Intentional lookahead-contaminated signal built with tomorrow's return to test leakage guards.",
    },
    "momentum_12_1": {
        "name": "momentum_12_1",
        "label": "Momentum (12-1 Month)",
        "category": "Price / Technical",
        "formula": "(P_{t-21} / P_{t-252}) - 1",
        "lookback_days": 252,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "Classic intermediate-horizon cross-sectional price momentum skipping the most recent 21-day reversal month.",
    },
    "reversal_21d": {
        "name": "reversal_21d",
        "label": "Short-Term Reversal (21d)",
        "category": "Price / Technical",
        "formula": "-1 * ((P_t / P_{t-21}) - 1)",
        "lookback_days": 21,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "1-month mean-reversion signal capturing liquidity provision and overreaction correction.",
    },
    "low_vol_63d": {
        "name": "low_vol_63d",
        "label": "Low Volatility (-σ 63d)",
        "category": "Risk / Defensive",
        "formula": "-1 * std(r_{t-62..t}) * sqrt(252)",
        "lookback_days": 63,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "Betting-against-beta / low realized 63-day volatility anomaly.",
    },
    "value_composite": {
        "name": "value_composite",
        "label": "Value Composite (E/P + FCF Yield, PIT)",
        "category": "Fundamental (Point-in-Time)",
        "formula": "0.5 * z_sector(E/P_pit) + 0.5 * z_sector(FCF_Yield_pit)",
        "lookback_days": 63,
        "default_lag": 1,
        "uses_fundamentals": True,
        "is_planted": False,
        "description": "Sector-relative point-in-time fundamental value composite respecting quarterly report_date.",
    },
    "quality_composite": {
        "name": "quality_composite",
        "label": "Quality Composite (ROE − Accruals, PIT)",
        "category": "Fundamental (Point-in-Time)",
        "formula": "z(ROE_pit) - z(Accruals_pit)",
        "lookback_days": 63,
        "default_lag": 1,
        "uses_fundamentals": True,
        "is_planted": False,
        "description": "Point-in-time profitability minus accounting accruals from quarterly filings.",
    },
    "agent_conviction": {
        "name": "agent_conviction",
        "label": "AI Agent Signed Conviction",
        "category": "AI / Multi-Agent",
        "formula": "sign(rec) * conviction_score (from PIT snapshots)",
        "lookback_days": 21,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "Signed multi-agent synthesizer conviction (+c for Buy, -c for Sell) from point-in-time snapshots.",
    },
    "sentiment_score": {
        "name": "sentiment_score",
        "label": "AI News & Social Sentiment",
        "category": "AI / Multi-Agent",
        "formula": "ema_5d(sentiment_agent_score)",
        "lookback_days": 10,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "Point-in-time NLP sentiment polarity score produced by the Sentiment Specialist Agent.",
    },
    "contradiction_flag": {
        "name": "contradiction_flag",
        "label": "Contradiction Radar Alignment",
        "category": "AI / Multi-Agent",
        "formula": "+1 if agents aligned bullish, -1 if critical contradiction present",
        "lookback_days": 5,
        "default_lag": 1,
        "uses_fundamentals": False,
        "is_planted": False,
        "description": "Penalizes names where technicals and fundamentals exhibit critical cross-agent contradiction.",
    },
}

_RESEARCH_UNIVERSE_CACHE: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Fast Vectorized 10-Year Universe & Point-in-Time Data Generator (QRA-001)
# ---------------------------------------------------------------------------
def _rank_zscore_row(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional rank-transformed z-score for a 1D array with NaNs."""
    out = np.full_like(arr, np.nan, dtype=float)
    valid = ~np.isnan(arr)
    n = int(valid.sum())
    if n < 3:
        return out
    vals = arr[valid]
    order = np.argsort(np.argsort(vals)).astype(float)
    mean = (n - 1.0) / 2.0
    std = math.sqrt((n * n - 1.0) / 12.0) + 1e-12
    out[valid] = (order - mean) / std
    return out


def _zscore_row(arr: np.ndarray) -> np.ndarray:
    """Cross-sectional standard z-score for a 1D array with NaNs."""
    out = np.full_like(arr, np.nan, dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < 3:
        return out
    vals = arr[valid]
    mu = float(np.mean(vals))
    sd = float(np.std(vals, ddof=1))
    if sd < 1e-12:
        out[valid] = 0.0
    else:
        out[valid] = (vals - mu) / sd
    return out


def get_research_universe() -> Dict[str, Any]:
    """
    Builds and caches the 100-ticker, 11-sector, 2,520-day research dataset.
    Includes daily prices, returns, market caps, point-in-time quarterly fundamentals
    (with report_date = period_end + 45 calendar days), delisting masks, and raw signals.
    """
    global _RESEARCH_UNIVERSE_CACHE
    if _RESEARCH_UNIVERSE_CACHE is not None:
        return _RESEARCH_UNIVERSE_CACHE

    T = N_RESEARCH_DAYS
    N = len(UNIVERSE_100_SPEC)
    dates_dt = pd.bdate_range(end=HISTORY_END_DATE, periods=T)
    dates = [d.strftime("%Y-%m-%d") for d in dates_dt]
    years = np.array([d.year for d in dates_dt], dtype=int)

    tickers = [item[0] for item in UNIVERSE_100_SPEC]
    names = [item[1] for item in UNIVERSE_100_SPEC]
    sectors = [item[2] for item in UNIVERSE_100_SPEC]
    sector_ids = np.array([GICS_11_SECTORS.index(s) for s in sectors], dtype=int)

    # Per-ticker static parameters
    betas = np.empty(N, dtype=float)
    annual_vols = np.empty(N, dtype=float)
    base_prices = np.empty(N, dtype=float)
    base_pes = np.empty(N, dtype=float)
    base_roes = np.empty(N, dtype=float)
    base_fcf_yields = np.empty(N, dtype=float)
    base_mcaps = np.empty(N, dtype=float)  # in $ millions
    adv_dollars = np.empty(N, dtype=float)
    seeds = np.empty(N, dtype=int)

    for i, (sym, _, sec) in enumerate(UNIVERSE_100_SPEC):
        sd = _ticker_seed(sym)
        seeds[i] = sd
        if sym in ANCHOR_PROFILES:
            anc = ANCHOR_PROFILES[sym]
            betas[i] = anc["beta"]
            annual_vols[i] = anc["base_vol"]
            base_prices[i] = anc["base_price"]
            base_pes[i] = anc["pe"]
            base_roes[i] = min(0.65, anc["roe"])
            base_fcf_yields[i] = 0.035 + (sd % 30) / 1000.0
            base_mcaps[i] = 150_000.0 + (sd % 900_000)
            adv_dollars[i] = anc["adv_shares"] * anc["base_price"]
        else:
            betas[i] = round(0.60 + ((sd >> 5) % 135) / 100.0, 2)
            annual_vols[i] = round(0.17 + ((sd >> 2) % 34) / 100.0, 3)
            base_prices[i] = round(40.0 + (sd % 260) + ((sd >> 4) % 100) / 100.0, 2)
            base_pes[i] = round(12.0 + ((sd >> 3) % 360) / 10.0, 1)
            base_roes[i] = round(0.08 + ((sd >> 6) % 32) / 100.0, 3)
            base_fcf_yields[i] = round(0.02 + ((sd >> 7) % 55) / 1000.0, 4)
            base_mcaps[i] = round(8_000.0 + (sd % 240_000), 1)
            adv_shares = int(2_500_000 + (sd % 28_000_000))
            adv_dollars[i] = round(adv_shares * base_prices[i], 2)

    # 1. Generate 10-year GARCH(1,1)-t Market (SPY) Return Series
    mkt_rng = np.random.RandomState(42)
    var_m = (MARKET_ANNUAL_VOL / math.sqrt(252.0)) ** 2
    omega_m = var_m * (1.0 - GARCH_ALPHA - GARCH_BETA)
    z_m = np.clip(
        mkt_rng.standard_t(T_DOF, T) / math.sqrt(T_DOF / (T_DOF - 2.0)),
        -T_CLIP_SIGMA,
        T_CLIP_SIGMA,
    )
    mkt_returns = np.empty(T, dtype=float)
    s2_m = var_m
    prev_m = 0.0
    drift_m = MARKET_ANNUAL_DRIFT / 252.0

    # Inject stress windows across the 10-year history (including the recent 504d windows)
    stress_mult = np.ones(T, dtype=float)
    stress_drift = np.full(T, drift_m, dtype=float)
    ten_yr_stress = [
        (420, 15, -0.18),   # 2018 Q4 vol spike
        (760, 22, -0.28),   # 2020 COVID crash
        (1320, 18, -0.16),  # 2022 Rate shock
        (T - 504 + 120, 5, -0.12),   # RSK-001 Liquidity shock (5d)
        (T - 504 + 360, 20, -0.20),  # RSK-001 Drawdown (20d)
    ]
    for st_idx, length, tot_ret in ten_yr_stress:
        if 0 <= st_idx and st_idx + length <= T:
            stress_mult[st_idx : st_idx + length] = 2.8
            stress_drift[st_idx : st_idx + length] = math.log1p(tot_ret) / length

    for t in range(T):
        if t > 0:
            s2_m = omega_m + GARCH_ALPHA * (prev_m * prev_m) + GARCH_BETA * s2_m
        base_shock = math.sqrt(s2_m) * z_m[t]
        mkt_returns[t] = stress_drift[t] + stress_mult[t] * base_shock
        prev_m = base_shock

    # 2. Sector factor returns (11 sectors) + Idiosyncratic GARCH(1,1)-t returns (vectorized across N=100)
    sec_rng = np.random.RandomState(101)
    sec_shocks = sec_rng.normal(0.0, 0.0045, size=(T, len(GICS_11_SECTORS)))

    idio_rng = np.random.RandomState(2026)
    idio_annual_vols = np.sqrt(np.maximum(0.015, annual_vols ** 2 - (betas * MARKET_ANNUAL_VOL) ** 2))
    var_u = (idio_annual_vols / math.sqrt(252.0)) ** 2
    omega_u = var_u * (1.0 - GARCH_ALPHA - GARCH_BETA)

    z_idio = idio_rng.standard_t(T_DOF, size=(T, N)) / math.sqrt(T_DOF / (T_DOF - 2.0))
    z_idio = np.clip(z_idio, -T_CLIP_SIGMA, T_CLIP_SIGMA)

    idio_returns = np.empty((T, N), dtype=float)
    s2_vec = var_u.copy()
    prev_vec = np.zeros(N, dtype=float)
    for t in range(T):
        if t > 0:
            s2_vec = omega_u + GARCH_ALPHA * (prev_vec * prev_vec) + GARCH_BETA * s2_vec
        shock_vec = np.sqrt(s2_vec) * z_idio[t]
        idio_returns[t] = shock_vec
        prev_vec = shock_vec

    # 3. Point-in-Time Quarterly Fundamentals & Fundamental Return Drift
    # Generate quarterly periods (every 63 trading days, starting 126d before t=0)
    quarter_Ends_idx = list(range(-126, T, 63))
    n_quarters = len(quarter_Ends_idx)
    f_rng = np.random.RandomState(707)

    # Quarterly tables: shape (n_quarters, N)
    q_period_end_str: List[str] = []
    q_report_date_str: List[str] = []
    q_report_idx = np.empty(n_quarters, dtype=int)

    for q_i, q_idx in enumerate(quarter_Ends_idx):
        if q_idx < 0:
            p_dt = dates_dt[0] - timedelta(days=int(abs(q_idx) * 365 / 252))
        else:
            p_dt = dates_dt[min(q_idx, T - 1)]
        # Report date is strictly 45 calendar days after period_end
        r_dt = p_dt + timedelta(days=45)
        r_str = r_dt.strftime("%Y-%m-%d")
        q_period_end_str.append(p_dt.strftime("%Y-%m-%d"))
        q_report_date_str.append(r_str)
        q_report_idx[q_i] = int(np.searchsorted(dates, r_str, side="left"))

    q_pe = np.empty((n_quarters, N), dtype=float)
    q_ep = np.empty((n_quarters, N), dtype=float)
    q_fcf_yield = np.empty((n_quarters, N), dtype=float)
    q_roe = np.empty((n_quarters, N), dtype=float)
    q_accruals = np.empty((n_quarters, N), dtype=float)

    for q_i in range(n_quarters):
        pe_mult = np.exp(f_rng.normal(0.0, 0.12, size=N))
        q_pe[q_i] = np.clip(base_pes * pe_mult, 6.0, 95.0)
        q_ep[q_i] = 1.0 / q_pe[q_i]
        q_fcf_yield[q_i] = np.clip(base_fcf_yields + f_rng.normal(0.0, 0.012, size=N), -0.02, 0.14)
        q_roe[q_i] = np.clip(base_roes + f_rng.normal(0.0, 0.04, size=N), -0.15, 0.85)
        q_accruals[q_i] = np.clip(f_rng.normal(0.02, 0.035, size=N), -0.10, 0.15)

    # Map point-in-time fundamentals to each daily index t:
    # At day t, the latest available fundamental is the highest q_i where q_report_date_str[q_i] <= dates[t]
    pit_q_idx = np.zeros(T, dtype=int)
    for t in range(T):
        d_str = dates[t]
        avail = [q_i for q_i, r_str in enumerate(q_report_date_str) if r_str <= d_str]
        pit_q_idx[t] = int(avail[-1]) if avail else 0

    pit_pe = q_pe[pit_q_idx]              # (T, N)
    pit_ep = q_ep[pit_q_idx]              # (T, N)
    pit_fcf_yield = q_fcf_yield[pit_q_idx]  # (T, N)
    pit_roe = q_roe[pit_q_idx]            # (T, N)
    pit_accruals = q_accruals[pit_q_idx]  # (T, N)
    pit_period_end = [q_period_end_str[idx] for idx in pit_q_idx]
    pit_report_date = [q_report_date_str[idx] for idx in pit_q_idx]

    # Add small realistic style premia to daily returns (value + quality + low-vol + momentum drift)
    style_drift = (
        0.00012 * ((pit_ep - np.mean(pit_ep, axis=1, keepdims=True)) / (np.std(pit_ep, axis=1, keepdims=True) + 1e-9))
        + 0.00010 * ((pit_roe - pit_accruals) - np.mean(pit_roe - pit_accruals, axis=1, keepdims=True))
    )
    returns_mat = (
        mkt_returns[:, None] * betas[None, :]
        + sec_shocks[:, sector_ids]
        + idio_returns
        + style_drift
    )

    # 4. Apply 5 Mock Delistings (QRA-001)
    active_mask = np.ones((T, N), dtype=bool)
    delisting_meta: Dict[str, Dict[str, Any]] = {}
    for sym, d_info in MOCK_DELISTINGS.items():
        if sym in tickers:
            col = tickers.index(sym)
            d_idx = d_info["delist_idx"]
            returns_mat[d_idx, col] = d_info["terminal_return"]
            if d_idx + 1 < T:
                returns_mat[d_idx + 1 :, col] = np.nan
                active_mask[d_idx + 1 :, col] = False
            delisting_meta[sym] = {
                "ticker": sym,
                "sector": sectors[col],
                "delist_index": d_idx,
                "delisted_date": dates[d_idx],
                "terminal_return": d_info["terminal_return"],
                "reason": d_info["reason"],
            }

    # 5. Construct Daily Close Price Matrix (T, N) and SPY Close Series
    prices_mat = np.full((T, N), np.nan, dtype=float)
    for col in range(N):
        valid_len = int(active_mask[:, col].sum())
        r_slice = returns_mat[:valid_len, col]
        cum_path = np.cumprod(1.0 + r_slice)
        if valid_len == T:
            scale = base_prices[col] / cum_path[-1]
        else:
            scale = base_prices[col] / cum_path[0]
        prices_mat[:valid_len, col] = np.round(cum_path * scale, 4)

    spy_cum = np.cumprod(1.0 + mkt_returns)
    spy_prices = np.round(spy_cum * (582.50 / spy_cum[-1]), 4)

    # Dynamic Market Cap Matrix ($M) proportional to price movement
    mcap_mat = np.where(active_mask, base_mcaps[None, :] * (prices_mat / base_prices[None, :]), np.nan)

    # 6. Precompute Forward Return Matrices for Horizons h in {1, 5, 21, 63, 126}
    # fwd_returns[h][t, i] = return from close_t to close_{t+h} = (P_{t+h} / P_t) - 1
    # Note: if a stock delists between t+1 and t+h, compound its realized returns up to delisting!
    log_1p_r = np.where(active_mask, np.log1p(np.clip(returns_mat, -0.99, 10.0)), 0.0)
    cum_log_r = np.vstack([np.zeros((1, N)), np.cumsum(log_1p_r, axis=0)])

    fwd_returns: Dict[int, np.ndarray] = {}
    for h in (1, 5, 21, 63, 126):
        fwd = np.full((T, N), np.nan, dtype=float)
        # Only stocks active at date t can be entered at close_t
        log_sum = cum_log_r[h:T] - cum_log_r[: T - h]
        fwd[: T - h] = np.expm1(log_sum)
        fwd[~active_mask] = np.nan
        fwd_returns[h] = fwd

    # 7. Construct the 4 Planted Benchmark Signals (QRA-001)
    # Construction: s_t = rho * u_t + sqrt(1 - rho^2) * eps_perp_t
    # where u_t is the cross-sectional rank-zscore of 21d forward returns on day t,
    # and eps_perp_t is cross-sectionally orthogonalized to u_t.
    # To make planted_alpha_strong and planted_alpha_weak work smoothly across all horizons
    # and under 1-day lag in backtests, u_t blends 21d forward return rank with 5d/63d continuity.
    p_rng = np.random.RandomState(314159)
    sig_strong = np.full((T, N), np.nan, dtype=float)
    sig_weak = np.full((T, N), np.nan, dtype=float)
    sig_noise = np.full((T, N), np.nan, dtype=float)
    sig_lookahead = np.full((T, N), np.nan, dtype=float)

    fwd21 = fwd_returns[21]
    fwd1 = fwd_returns[1]

    rho_strong = 0.0522  # Calibrated so Spearman Rank IC on 21d is ~0.0500
    rho_weak = 0.0209    # Calibrated so Spearman Rank IC on 21d is ~0.0200
    rho_look = 0.8500    # Unlagged tomorrow return correlation ~0.85 (> 0.35 threshold)

    for t in range(T):
        valid = active_mask[t] & ~np.isnan(fwd21[t])
        n_v = int(valid.sum())
        if n_v >= 10:
            u = _rank_zscore_row(fwd21[t])[valid]
            u = (u - np.mean(u)) / (np.std(u, ddof=1) + 1e-12)

            # Raw Gaussian draws
            e1 = p_rng.normal(0.0, 1.0, size=n_v)
            e2 = p_rng.normal(0.0, 1.0, size=n_v)
            e3 = p_rng.normal(0.0, 1.0, size=n_v)

            # Orthogonalize each noise vector to u so sample correlation on date t is exact
            for e_vec in (e1, e2, e3):
                e_vec -= np.mean(e_vec)
                proj = np.dot(e_vec, u) / (np.dot(u, u) + 1e-12)
                e_vec -= proj * u
                e_vec /= (np.std(e_vec, ddof=1) + 1e-12)

            sig_strong[t, valid] = rho_strong * u + math.sqrt(1.0 - rho_strong ** 2) * e1
            sig_weak[t, valid] = rho_weak * u + math.sqrt(1.0 - rho_weak ** 2) * e2
            sig_noise[t, valid] = e3
        else:
            valid_act = active_mask[t]
            n_act = int(valid_act.sum())
            if n_act >= 3:
                sig_strong[t, valid_act] = p_rng.normal(0.0, 1.0, size=n_act)
                sig_weak[t, valid_act] = p_rng.normal(0.0, 1.0, size=n_act)
                sig_noise[t, valid_act] = p_rng.normal(0.0, 1.0, size=n_act)

        # Lookahead signal uses tomorrow's 1-day return r_{t+1} directly at time t
        valid_1 = active_mask[t] & ~np.isnan(fwd1[t])
        n_v1 = int(valid_1.sum())
        if n_v1 >= 5:
            u1 = _zscore_row(fwd1[t])[valid_1]
            e_look = p_rng.normal(0.0, 1.0, size=n_v1)
            e_look = (e_look - np.mean(e_look)) / (np.std(e_look, ddof=1) + 1e-12)
            sig_lookahead[t, valid_1] = rho_look * u1 + math.sqrt(1.0 - rho_look ** 2) * e_look
        elif int(active_mask[t].sum()) >= 3:
            sig_lookahead[t, active_mask[t]] = 0.0

    # 8. Precompute the 8 Empirical / AI Library Signals (QRA-003)
    # 8a. Momentum 12-1: return from t-252 to t-21
    sig_mom = np.full((T, N), np.nan, dtype=float)
    for t in range(252, T):
        sig_mom[t] = (prices_mat[t - 21] / prices_mat[t - 252]) - 1.0
    sig_mom[~active_mask] = np.nan

    # 8b. Short-term Reversal 21d: -(P_t / P_{t-21} - 1)
    sig_rev = np.full((T, N), np.nan, dtype=float)
    for t in range(21, T):
        sig_rev[t] = -1.0 * ((prices_mat[t] / prices_mat[t - 21]) - 1.0)
    sig_rev[~active_mask] = np.nan

    # 8c. Low Volatility 63d: -std(r_{t-62..t}) * sqrt(252)
    sig_lowvol = np.full((T, N), np.nan, dtype=float)
    r_df = pd.DataFrame(returns_mat)
    rolling_vol_63 = r_df.rolling(window=63, min_periods=21).std().to_numpy() * math.sqrt(252.0)
    sig_lowvol = -1.0 * rolling_vol_63
    sig_lowvol[~active_mask] = np.nan

    # 8d. Value Composite (sector-relative z(E/P_pit) + z(FCF_Yield_pit))
    sig_value = np.full((T, N), np.nan, dtype=float)
    for t in range(T):
        ep_row = np.where(active_mask[t], pit_ep[t], np.nan)
        fcf_row = np.where(active_mask[t], pit_fcf_yield[t], np.nan)
        val_row = np.full(N, np.nan, dtype=float)
        for s_id in range(len(GICS_11_SECTORS)):
            sec_m = (sector_ids == s_id) & active_mask[t]
            if sec_m.sum() >= 2:
                z_ep = (ep_row[sec_m] - np.mean(ep_row[sec_m])) / (np.std(ep_row[sec_m]) + 1e-9)
                z_fcf = (fcf_row[sec_m] - np.mean(fcf_row[sec_m])) / (np.std(fcf_row[sec_m]) + 1e-9)
                val_row[sec_m] = 0.5 * z_ep + 0.5 * z_fcf
        sig_value[t] = val_row

    # 8e. Quality Composite: z(ROE_pit) - z(Accruals_pit)
    sig_quality = np.full((T, N), np.nan, dtype=float)
    for t in range(T):
        roe_z = _zscore_row(np.where(active_mask[t], pit_roe[t], np.nan))
        acc_z = _zscore_row(np.where(active_mask[t], pit_accruals[t], np.nan))
        sig_quality[t] = roe_z - acc_z

    # 8f. AI Agent Conviction, Sentiment Score, and Contradiction Flag (from simulated PIT snapshots)
    ai_rng = np.random.RandomState(9090)
    sig_conviction = np.full((T, N), np.nan, dtype=float)
    sig_sentiment = np.full((T, N), np.nan, dtype=float)
    sig_contradiction = np.full((T, N), np.nan, dtype=float)

    # AI conviction has genuine weak-to-moderate predictive power (~0.028 IC) + fundamental & momentum grounding
    for t in range(T):
        valid = active_mask[t] & ~np.isnan(fwd21[t])
        u = _rank_zscore_row(fwd21[t]) if valid.sum() >= 10 else np.zeros(N)
        u = np.nan_to_num(u, nan=0.0)
        q_part = np.nan_to_num(sig_quality[t], nan=0.0)
        v_part = np.nan_to_num(sig_value[t], nan=0.0)
        m_part = np.nan_to_num(_zscore_row(sig_mom[t]), nan=0.0)

        noise_c = ai_rng.normal(0.0, 1.0, size=N)
        noise_s = ai_rng.normal(0.0, 1.0, size=N)
        noise_k = ai_rng.normal(0.0, 1.0, size=N)

        raw_conv = 0.028 * u + 0.25 * q_part + 0.20 * v_part + 0.20 * m_part + 0.88 * noise_c
        # Map to discrete signed conviction in [-10, +10]
        scaled_conv = np.clip(np.round(raw_conv * 3.2), -10.0, 10.0)
        sig_conviction[t] = np.where(active_mask[t], scaled_conv, np.nan)

        raw_sent = 0.018 * u + 0.15 * m_part + 0.95 * noise_s
        sig_sentiment[t] = np.where(active_mask[t], np.clip(raw_sent, -3.0, 3.0), np.nan)

        # Contradiction flag: -1 when technical momentum and fundamental value strongly diverge, +1 when aligned
        divergence = np.abs(m_part - v_part)
        flag = np.where(divergence > 1.65, -1.0, np.where(divergence < 0.55, 1.0, 0.0)) + 0.15 * noise_k
        sig_contradiction[t] = np.where(active_mask[t], flag, np.nan)

    raw_signals = {
        "planted_alpha_strong": sig_strong,
        "planted_alpha_weak": sig_weak,
        "planted_noise": sig_noise,
        "planted_lookahead": sig_lookahead,
        "momentum_12_1": sig_mom,
        "reversal_21d": sig_rev,
        "low_vol_63d": sig_lowvol,
        "value_composite": sig_value,
        "quality_composite": sig_quality,
        "agent_conviction": sig_conviction,
        "sentiment_score": sig_sentiment,
        "contradiction_flag": sig_contradiction,
    }

    _RESEARCH_UNIVERSE_CACHE = {
        "dates": dates,
        "dates_dt": dates_dt,
        "years": years,
        "tickers": tickers,
        "names": names,
        "sectors": sectors,
        "sector_ids": sector_ids,
        "betas": betas,
        "annual_vols": annual_vols,
        "base_prices": base_prices,
        "adv_dollars": adv_dollars,
        "mkt_returns": mkt_returns,
        "spy_prices": spy_prices,
        "returns_mat": returns_mat,
        "prices_mat": prices_mat,
        "mcap_mat": mcap_mat,
        "active_mask": active_mask,
        "delistings": delisting_meta,
        "pit_pe": pit_pe,
        "pit_ep": pit_ep,
        "pit_fcf_yield": pit_fcf_yield,
        "pit_roe": pit_roe,
        "pit_accruals": pit_accruals,
        "pit_period_end": pit_period_end,
        "pit_report_date": pit_report_date,
        "q_period_end_str": q_period_end_str,
        "q_report_date_str": q_report_date_str,
        "q_report_idx": q_report_idx,
        "fwd_returns": fwd_returns,
        "raw_signals": raw_signals,
    }
    return _RESEARCH_UNIVERSE_CACHE


# ---------------------------------------------------------------------------
# QRA-002: Research Panel API & Survivorship-Free Universe by Date
# ---------------------------------------------------------------------------
def get_universe_as_of(as_of_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns active universe members on `as_of_date`, including stocks that
    later delisted (preventing survivorship bias) and excluding stocks already
    delisted prior to `as_of_date`.
    """
    u = get_research_universe()
    dates = u["dates"]
    target_date = as_of_date or dates[-1]

    # Locate the latest trading day <= target_date
    idx = int(np.searchsorted(dates, target_date, side="right")) - 1
    if idx < 0:
        idx = 0
    resolved_date = dates[idx]

    members = []
    excluded_already_delisted = []
    active_later_delisted = []
    sector_counts: Dict[str, int] = {s: 0 for s in GICS_11_SECTORS}

    for col, sym in enumerate(u["tickers"]):
        is_active = bool(u["active_mask"][idx, col])
        delist_info = u["delistings"].get(sym)
        if is_active:
            sec = u["sectors"][col]
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            entry = {
                "ticker": sym,
                "name": u["names"][col],
                "sector": sec,
                "close": round(float(u["prices_mat"][idx, col]), 2),
                "mcap_m": round(float(u["mcap_mat"][idx, col]), 1),
                "beta": float(u["betas"][col]),
                "later_delisted": delist_info is not None,
                "delisted_date": delist_info["delisted_date"] if delist_info else None,
            }
            members.append(entry)
            if delist_info is not None:
                active_later_delisted.append(entry)
        else:
            if delist_info is not None:
                excluded_already_delisted.append(delist_info)

    return {
        "requested_date": target_date,
        "as_of_date": resolved_date,
        "day_index": idx,
        "active_count": len(members),
        "total_universe_size": len(u["tickers"]),
        "active_later_delisted_count": len(active_later_delisted),
        "already_delisted_count": len(excluded_already_delisted),
        "sector_counts": sector_counts,
        "members": members,
        "active_later_delisted": active_later_delisted,
        "already_delisted": excluded_already_delisted,
        "all_mock_delistings": list(u["delistings"].values()),
        "_provenance": {
            "source": "qra_mock100_engine",
            "data_version": DATA_VERSION,
            "as_of": resolved_date,
            "survivorship_free": True,
        },
    }


def get_research_panel(
    fields: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    as_of_date: Optional[str] = None,
    tickers_filter: Optional[List[str]] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """
    Returns long-format point-in-time research panel rows:
      (date, ticker, field, value, period_end, report_date)
    Guarantees that NO fundamental value is ever returned with report_date > date.
    """
    u = get_research_universe()
    dates = u["dates"]
    req_fields = fields or ["close", "ret_1d", "mcap", "sector", "pe", "roe", "fcf_yield"]
    valid_fields = {"close", "ret_1d", "mcap", "sector", "pe", "ep", "fcf_yield", "roe", "accruals", "beta"}
    req_fields = [f.strip().lower() for f in req_fields if f.strip().lower() in valid_fields]
    if not req_fields:
        req_fields = ["close", "ret_1d", "mcap", "pe"]

    if as_of_date:
        idx = max(0, int(np.searchsorted(dates, as_of_date, side="right")) - 1)
        t_indices = [idx]
    else:
        s_idx = int(np.searchsorted(dates, start_date, side="left")) if start_date else max(0, len(dates) - 5)
        e_idx = int(np.searchsorted(dates, end_date, side="right")) - 1 if end_date else len(dates) - 1
        s_idx = max(0, min(s_idx, len(dates) - 1))
        e_idx = max(s_idx, min(e_idx, len(dates) - 1))
        t_indices = list(range(s_idx, e_idx + 1))

    if tickers_filter:
        wanted = {t.strip().upper() for t in tickers_filter if t.strip()}
        col_indices = [i for i, sym in enumerate(u["tickers"]) if sym in wanted]
    else:
        col_indices = list(range(len(u["tickers"])))

    fundamental_fields = {"pe", "ep", "fcf_yield", "roe", "accruals"}
    rows = []
    pit_violations = 0

    for t in t_indices:
        d_str = dates[t]
        p_end = u["pit_period_end"][t]
        r_date = u["pit_report_date"][t]
        if r_date > d_str:
            pit_violations += 1
            continue

        for col in col_indices:
            if not u["active_mask"][t, col]:
                continue
            sym = u["tickers"][col]
            for fld in req_fields:
                if fld == "close":
                    val: Any = round(float(u["prices_mat"][t, col]), 4)
                elif fld == "ret_1d":
                    val = round(float(u["returns_mat"][t, col]), 6)
                elif fld == "mcap":
                    val = round(float(u["mcap_mat"][t, col]), 2)
                elif fld == "sector":
                    val = u["sectors"][col]
                elif fld == "beta":
                    val = float(u["betas"][col])
                elif fld == "pe":
                    val = round(float(u["pit_pe"][t, col]), 2)
                elif fld == "ep":
                    val = round(float(u["pit_ep"][t, col]), 5)
                elif fld == "fcf_yield":
                    val = round(float(u["pit_fcf_yield"][t, col]), 5)
                elif fld == "roe":
                    val = round(float(u["pit_roe"][t, col]), 4)
                elif fld == "accruals":
                    val = round(float(u["pit_accruals"][t, col]), 4)
                else:
                    continue

                is_fund = fld in fundamental_fields
                rows.append({
                    "date": d_str,
                    "ticker": sym,
                    "field": fld,
                    "value": val,
                    "period_end": p_end if is_fund else None,
                    "report_date": r_date if is_fund else None,
                })
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    return {
        "universe": "mock100",
        "format": "long",
        "fields": req_fields,
        "row_count": len(rows),
        "pit_verified": pit_violations == 0,
        "pit_violations": pit_violations,
        "rows": rows,
        "_provenance": {
            "source": "qra_mock100_engine",
            "data_version": DATA_VERSION,
            "point_in_time_rule": "report_date <= date strictly enforced (45d filing lag)",
        },
    }


def get_research_panel_csv(
    fields: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    as_of_date: Optional[str] = None,
    tickers_filter: Optional[List[str]] = None,
    limit: int = 10000,
) -> str:
    """Serializes the long-format point-in-time research panel to CSV."""
    panel = get_research_panel(
        fields=fields,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
        tickers_filter=tickers_filter,
        limit=limit,
    )
    buf = io.StringIO()
    buf.write("date,ticker,field,value,period_end,report_date\n")
    for r in panel["rows"]:
        p_end = r["period_end"] or ""
        r_dt = r["report_date"] or ""
        buf.write(f"{r['date']},{r['ticker']},{r['field']},{r['value']},{p_end},{r_dt}\n")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# QRA-003: Signal Standardisation Pipeline (Winsorise, Neutralise, Z-Score)
# ---------------------------------------------------------------------------
def process_signal_matrix(
    raw_mat: np.ndarray,
    winsorize: bool = True,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    zscore: bool = True,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Processes a (T, N) raw signal matrix cross-sectionally per date:
      1. Winsorise at 1st and 99th percentiles.
      2. Optional sector-neutral (demean within each of the 11 sectors) and/or
         beta-neutral (OLS residual against stock beta).
      3. Cross-sectional z-score (mean = 0.0, sample std = 1.0 per date).
    Returns (processed_matrix, diagnostics_dict).
    """
    u = get_research_universe()
    T, N = raw_mat.shape
    sector_ids = u["sector_ids"]
    betas = u["betas"]
    active_mask = u["active_mask"]

    out = np.full((T, N), np.nan, dtype=float)
    daily_means = []
    daily_stds = []
    daily_cov = []
    sec_corrs_accum = np.zeros(len(GICS_11_SECTORS), dtype=float)
    sec_corr_days = 0

    for t in range(T):
        row = raw_mat[t].copy()
        valid = active_mask[t] & ~np.isnan(row)
        n_valid = int(valid.sum())
        n_active = int(active_mask[t].sum())
        daily_cov.append(n_valid / max(1, n_active))

        if n_valid < 5:
            continue

        vals = row[valid]

        # Step 1: Winsorise 1% / 99%
        if winsorize:
            p01, p99 = np.percentile(vals, [1.0, 99.0])
            vals = np.clip(vals, p01, p99)
            row[valid] = vals

        # Step 2a: Sector Neutralisation (demean within each GICS sector)
        if sector_neutral:
            for s_id in range(len(GICS_11_SECTORS)):
                s_mask = valid & (sector_ids == s_id)
                if s_mask.sum() >= 1:
                    row[s_mask] -= float(np.mean(row[s_mask]))

        # Step 2b: Beta Neutralisation (OLS residual against beta; if also sector_neutral, include sector dummies)
        if beta_neutral:
            y = row[valid]
            b_v = betas[valid]
            if sector_neutral:
                # Jointly residualise against sector dummies + beta so both remain orthogonal
                X_cols = [b_v]
                for s_id in range(len(GICS_11_SECTORS)):
                    X_cols.append((sector_ids[valid] == s_id).astype(float))
                X = np.column_stack(X_cols)
            else:
                X = np.column_stack([np.ones(n_valid), b_v])
            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            row[valid] = y - X @ coef

        # Step 3: Cross-sectional z-score (mean = 0, sample std = 1)
        if zscore:
            v_now = row[valid]
            mu = float(np.mean(v_now))
            sd = float(np.std(v_now, ddof=1))
            if sd > 1e-12:
                row[valid] = (v_now - mu) / sd
            else:
                row[valid] = 0.0

        out[t, valid] = row[valid]
        v_final = out[t, valid]
        daily_means.append(float(np.mean(v_final)))
        daily_stds.append(float(np.std(v_final, ddof=1)))

        # Measure correlation with the 11 sector dummy variables on recent 252d
        if t >= T - 252:
            for s_id in range(len(GICS_11_SECTORS)):
                dummy = (sector_ids[valid] == s_id).astype(float)
                if np.std(dummy) > 1e-9 and np.std(v_final) > 1e-9:
                    c = float(np.corrcoef(v_final, dummy)[0, 1])
                    sec_corrs_accum[s_id] += c
            sec_corr_days += 1

    avg_sec_corrs = {
        GICS_11_SECTORS[s_id]: round(float(sec_corrs_accum[s_id] / max(1, sec_corr_days)), 6)
        for s_id in range(len(GICS_11_SECTORS))
    }
    max_abs_sec_corr = round(max(abs(v) for v in avg_sec_corrs.values()), 6) if avg_sec_corrs else 0.0

    # Beta correlation on trailing 252d
    beta_corrs = []
    for t in range(max(0, T - 252), T):
        v_m = ~np.isnan(out[t])
        if v_m.sum() >= 5 and np.std(out[t, v_m]) > 1e-9:
            beta_corrs.append(float(np.corrcoef(out[t, v_m], betas[v_m])[0, 1]))

    diagnostics = {
        "winsorized_1_99": winsorize,
        "sector_neutral": sector_neutral,
        "beta_neutral": beta_neutral,
        "zscored": zscore,
        "mean_cross_sectional_mean": round(float(np.mean(daily_means)), 6) if daily_means else 0.0,
        "mean_cross_sectional_sd": round(float(np.mean(daily_stds)), 6) if daily_stds else 1.0,
        "mean_coverage_pct": round(float(np.mean(daily_cov)) * 100.0, 2) if daily_cov else 0.0,
        "latest_coverage_pct": round(float(daily_cov[-1]) * 100.0, 2) if daily_cov else 0.0,
        "sector_dummy_correlations": avg_sec_corrs,
        "max_abs_sector_dummy_corr": max_abs_sec_corr,
        "mean_beta_corr": round(float(np.mean(beta_corrs)), 6) if beta_corrs else 0.0,
    }
    return out, diagnostics


_STD_SIGNAL_CACHE: Dict[Tuple[str, bool, bool, bool, bool], Tuple[np.ndarray, Dict[str, Any]]] = {}


def get_standardized_signal(
    signal_name: str,
    winsorize: bool = True,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    zscore: bool = True,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Fetches a named signal from the library and runs (and caches) the standardisation pipeline."""
    u = get_research_universe()
    clean_name = signal_name.strip().lower()
    if clean_name not in u["raw_signals"]:
        raise ValueError(f"Unknown signal '{signal_name}'. Valid signals: {list(SIGNAL_CATALOG.keys())}")
    cache_key = (clean_name, bool(winsorize), bool(sector_neutral), bool(beta_neutral), bool(zscore))
    if cache_key not in _STD_SIGNAL_CACHE:
        raw_mat = u["raw_signals"][clean_name]
        _STD_SIGNAL_CACHE[cache_key] = process_signal_matrix(
            raw_mat,
            winsorize=winsorize,
            sector_neutral=sector_neutral,
            beta_neutral=beta_neutral,
            zscore=zscore,
        )
    return _STD_SIGNAL_CACHE[cache_key]


def get_signal_details(
    signal_name: str,
    as_of_date: Optional[str] = None,
    winsorize: bool = True,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    zscore: bool = True,
) -> Dict[str, Any]:
    """Returns metadata, standardisation diagnostics, and cross-sectional snapshot for a signal."""
    u = get_research_universe()
    clean_name = signal_name.strip().lower()
    if clean_name not in SIGNAL_CATALOG:
        raise ValueError(f"Unknown signal '{signal_name}'")

    mat, diag = get_standardized_signal(
        clean_name,
        winsorize=winsorize,
        sector_neutral=sector_neutral,
        beta_neutral=beta_neutral,
        zscore=zscore,
    )
    dates = u["dates"]
    idx = max(0, int(np.searchsorted(dates, as_of_date, side="right")) - 1) if as_of_date else len(dates) - 22
    idx = min(idx, len(dates) - 1)

    cross_section = []
    for col, sym in enumerate(u["tickers"]):
        val = mat[idx, col]
        if not np.isnan(val):
            cross_section.append({
                "ticker": sym,
                "name": u["names"][col],
                "sector": u["sectors"][col],
                "beta": float(u["betas"][col]),
                "z_score": round(float(val), 4),
                "raw_score": round(float(u["raw_signals"][clean_name][idx, col]), 4),
            })
    cross_section.sort(key=lambda x: x["z_score"], reverse=True)

    return {
        "signal": SIGNAL_CATALOG[clean_name],
        "as_of_date": dates[idx],
        "diagnostics": diag,
        "top_10": cross_section[:10],
        "bottom_10": cross_section[-10:],
        "cross_section_count": len(cross_section),
        "_provenance": {
            "source": "qra_signal_engine",
            "data_version": DATA_VERSION,
            "as_of": dates[idx],
        },
    }


# ---------------------------------------------------------------------------
# QRA-008: Automated Lookahead Bias & Leakage Scanner
# ---------------------------------------------------------------------------
def scan_signal_leakage(
    signal_name: str,
    sig_mat: Optional[np.ndarray] = None,
    lag: int = 1,
    simulate_bad_report_date: bool = False,
) -> Dict[str, Any]:
    """
    Automated linter running on signal formulas and backtest configurations:
      1. Audits point-in-time fundamental dates (`report_date > as_of_date`).
      2. Computes unlagged next-day correlation Corr(s_t, r_{t+1}); flags if |Corr| > 0.35.
      3. Checks lag=0 backtest configuration vs lag=1.
    """
    u = get_research_universe()
    clean_name = signal_name.strip().lower()
    if sig_mat is None:
        sig_mat, _ = get_standardized_signal(clean_name)

    T, _ = sig_mat.shape
    fwd1 = u["fwd_returns"][1]

    # 1. Compute daily unlagged correlation Corr(s_t, r_{t+1}) and lagged Corr(s_{t-1}, r_{t+1})
    unlagged_corrs = []
    lagged_corrs = []
    for t in range(1, T - 1):
        s_t = sig_mat[t]
        s_prev = sig_mat[t - 1]
        r_next = fwd1[t]
        m0 = ~np.isnan(s_t) & ~np.isnan(r_next)
        if m0.sum() >= 10 and np.std(s_t[m0]) > 1e-9 and np.std(r_next[m0]) > 1e-9:
            unlagged_corrs.append(float(np.corrcoef(s_t[m0], r_next[m0])[0, 1]))
        m1 = ~np.isnan(s_prev) & ~np.isnan(r_next)
        if m1.sum() >= 10 and np.std(s_prev[m1]) > 1e-9 and np.std(r_next[m1]) > 1e-9:
            lagged_corrs.append(float(np.corrcoef(s_prev[m1], r_next[m1])[0, 1]))

    mean_unlagged_corr = float(np.mean(unlagged_corrs)) if unlagged_corrs else 0.0
    mean_lagged_corr = float(np.mean(lagged_corrs)) if lagged_corrs else 0.0

    # 2. Point-in-time fundamental report_date audit
    pit_violations = 0
    for t, d_str in enumerate(u["dates"]):
        if u["pit_report_date"][t] > d_str:
            pit_violations += 1
    if simulate_bad_report_date:
        pit_violations += 12

    corr_threshold = 0.35
    corr_breach = abs(mean_unlagged_corr) > corr_threshold
    pit_breach = pit_violations > 0
    lag_warning = lag == 0

    warnings = []
    if corr_breach:
        warnings.append(
            f"CRITICAL LOOKAHEAD LEAK: Unlagged Corr(s_t, r_{{t+1}}) = {mean_unlagged_corr:.4f} exceeds threshold {corr_threshold:.2f}. Signal embeds future return information."
        )
    if pit_breach:
        warnings.append(
            f"POINT-IN-TIME VIOLATION: Found {pit_violations} fundamental record(s) with report_date > as_of_date."
        )
    if lag_warning:
        warnings.append(
            "EXECUTION LAG WARNING: Signal lag is set to 0 days (same-close execution). Institutional default requires lag >= 1 day."
        )

    passed = not (corr_breach or pit_breach)
    badge = "POINT_IN_TIME_VERIFIED" if (passed and not lag_warning) else "LEAKAGE_WARNING"
    badge_label = "Point-in-Time Verified ✓" if badge == "POINT_IN_TIME_VERIFIED" else "Leakage Warning ⚠"

    return {
        "signal_name": clean_name,
        "passed": passed,
        "badge": badge,
        "badge_label": badge_label,
        "severity": "critical" if not passed else ("warning" if lag_warning else "ok"),
        "unlagged_corr_s_t_r_t1": round(mean_unlagged_corr, 4),
        "lagged_corr_s_t_minus_1_r_t1": round(mean_lagged_corr, 4),
        "corr_threshold": corr_threshold,
        "corr_breach": corr_breach,
        "pit_report_date_violations": pit_violations,
        "pit_breach": pit_breach,
        "execution_lag_days": lag,
        "lag_warning": lag_warning,
        "warnings": warnings,
        "_provenance": {
            "source": "qra_leakage_scanner",
            "rule": "|Corr(s_t, r_{t+1})| <= 0.35 and report_date <= as_of_date",
        },
    }


# ---------------------------------------------------------------------------
# QRA-004: Spearman Rank IC Tear Sheet & Newey-West HAC Statistics
# ---------------------------------------------------------------------------
def _spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    """Fast Spearman rank correlation on paired 1D arrays without NaNs."""
    n = len(x)
    if n < 5:
        return np.nan
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    mx = (n - 1.0) / 2.0
    dx = rx - mx
    dy = ry - mx
    denom = math.sqrt(float(np.dot(dx, dx) * np.dot(dy, dy)))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(dx, dy) / denom)


def compute_newey_west_tstat(series: np.ndarray, max_lag: int) -> Tuple[float, float]:
    """
    Computes Newey-West HAC standard error and t-statistic for the sample mean
    of `series` with Bartlett kernel up to `max_lag`.
    Returns (t_stat, nw_std_err).
    """
    clean = series[~np.isnan(series)]
    n = len(clean)
    if n < 10:
        return 0.0, 0.0
    mu = float(np.mean(clean))
    demeaned = clean - mu
    gamma_0 = float(np.dot(demeaned, demeaned) / n)
    nw_var = gamma_0
    L = max(1, min(int(max_lag), n // 4))
    for j in range(1, L + 1):
        weight = 1.0 - (j / (L + 1.0))
        gamma_j = float(np.dot(demeaned[j:], demeaned[:-j]) / n)
        nw_var += 2.0 * weight * gamma_j
    nw_var = max(nw_var, 1e-12)
    se_mean = math.sqrt(nw_var / n)
    t_stat = mu / (se_mean + 1e-12)
    return float(t_stat), float(se_mean)


def compute_ic_tear_sheet(
    signal_name: str = "planted_alpha_strong",
    horizon: int = 21,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    custom_signal_mat: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Computes full QRA-004 & QRA-007 IC Tear Sheet:
      - Daily Spearman Rank IC series, Mean IC, IC SD, Annualized IC IR, Newey-West HAC t-stat
      - Rolling 63d Rank IC with +/- 2 sigma bands
      - IC Decay across horizons (1, 5, 21, 63, 126d) + half-life
      - Quintile returns (Q1..Q5 annualized return) + monotonicity check + Q5-Q1 cumulative spread vs SPY
      - Signal rank autocorrelation & quintile turnover
      - IC by Year (10 years) and IC by Sector (11-sector boxplot statistics)
      - Embedded QRA-008 Leakage Scan
    """
    u = get_research_universe()
    if horizon not in (1, 5, 21, 63, 126):
        horizon = 21

    if custom_signal_mat is not None:
        sig_mat, std_diag = process_signal_matrix(
            custom_signal_mat,
            winsorize=True,
            sector_neutral=sector_neutral,
            beta_neutral=beta_neutral,
            zscore=True,
        )
        clean_name = signal_name
    else:
        clean_name = signal_name.strip().lower()
        sig_mat, std_diag = get_standardized_signal(
            clean_name,
            winsorize=True,
            sector_neutral=sector_neutral,
            beta_neutral=beta_neutral,
            zscore=True,
        )

    dates = u["dates"]
    T, N = sig_mat.shape
    s_idx = int(np.searchsorted(dates, start_date, side="left")) if start_date else 252
    e_idx = int(np.searchsorted(dates, end_date, side="right")) - 1 if end_date else T - 127
    s_idx = max(0, min(s_idx, T - horizon - 2))
    e_idx = max(s_idx + 20, min(e_idx, T - horizon - 1))

    fwd_h = u["fwd_returns"][horizon]
    fwd_1 = u["fwd_returns"][1]
    sector_ids = u["sector_ids"]

    eval_indices = list(range(s_idx, e_idx + 1))
    n_eval = len(eval_indices)

    ic_series = np.full(n_eval, np.nan, dtype=float)
    eval_dates = [dates[t] for t in eval_indices]
    eval_years = [int(u["years"][t]) for t in eval_indices]

    # Daily 1-day returns of Q1..Q5 portfolios (rebalanced every `horizon` days or daily overlapped)
    q_daily_rets = np.zeros((n_eval, 5), dtype=float)
    q_fwd_rets = [[] for _ in range(5)]
    rank_autocorrs = []
    q5_turnovers = []
    prev_q5_set = None

    # Sector-level IC lists for 11-sector boxplot
    sector_ic_lists: Dict[str, List[float]] = {s: [] for s in GICS_11_SECTORS}

    for k, t in enumerate(eval_indices):
        s_row = sig_mat[t]
        r_row = fwd_h[t]
        r1_row = fwd_1[t]
        valid = ~np.isnan(s_row) & ~np.isnan(r_row)
        if valid.sum() < 10:
            continue

        ic_val = _spearman_corr(s_row[valid], r_row[valid])
        ic_series[k] = ic_val

        # Quintile assignment (Q1 = lowest 20%, Q5 = highest 20%)
        s_v = s_row[valid]
        r_v = r_row[valid]
        r1_v = np.nan_to_num(r1_row[valid], nan=0.0)
        v_cols = np.where(valid)[0]

        edges = np.percentile(s_v, [20.0, 40.0, 60.0, 80.0])
        q_bins = np.digitize(s_v, edges)  # 0..4 corresponding to Q1..Q5
        for q in range(5):
            qm = q_bins == q
            if qm.sum() > 0:
                q_fwd_rets[q].append(float(np.mean(r_v[qm])))
                q_daily_rets[k, q] = float(np.mean(r1_v[qm]))

        # Turnover & Rank Autocorrelation
        q5_current = set(v_cols[q_bins == 4].tolist())
        if prev_q5_set is not None and len(q5_current) > 0:
            overlap = len(q5_current.intersection(prev_q5_set))
            q5_turnovers.append(1.0 - (overlap / max(1, len(q5_current))))
        prev_q5_set = q5_current

        if t > 0:
            s_prev = sig_mat[t - 1]
            m_auto = ~np.isnan(s_row) & ~np.isnan(s_prev)
            if m_auto.sum() >= 10:
                rank_autocorrs.append(_spearman_corr(s_row[m_auto], s_prev[m_auto]))

        # Per-sector IC (sampled every 3rd day for speed while keeping ~750 observations per sector)
        if k % 3 == 0:
            for s_id, sec_name in enumerate(GICS_11_SECTORS):
                sm = valid & (sector_ids == s_id)
                if sm.sum() >= 5:
                    sec_ic = _spearman_corr(s_row[sm], r_row[sm])
                    if not np.isnan(sec_ic):
                        sector_ic_lists[sec_name].append(sec_ic)

    valid_ics = ic_series[~np.isnan(ic_series)]
    mean_ic = float(np.mean(valid_ics)) if len(valid_ics) else 0.0
    sd_ic = float(np.std(valid_ics, ddof=1)) if len(valid_ics) > 1 else 0.01
    ic_ir = (mean_ic / (sd_ic + 1e-12)) * math.sqrt(252.0 / horizon)
    nw_t_stat, nw_se = compute_newey_west_tstat(ic_series, max_lag=horizon)
    hit_rate = float(np.mean(valid_ics > 0.0)) if len(valid_ics) else 0.0

    # Quintile return summary (annualized from non-overlapping / horizon-scaled forward returns)
    ann_factor = 252.0 / horizon
    quintile_summary = []
    q_ann_means = []
    for q in range(5):
        arr_q = np.array(q_fwd_rets[q], dtype=float)
        mean_h = float(np.mean(arr_q)) if len(arr_q) else 0.0
        ann_ret = mean_h * ann_factor
        q_ann_means.append(ann_ret)
        quintile_summary.append({
            "quintile": f"Q{q + 1}",
            "mean_period_return_pct": round(mean_h * 100.0, 4),
            "annualized_return_pct": round(ann_ret * 100.0, 2),
        })

    is_strictly_monotonic = all(q_ann_means[i] < q_ann_means[i + 1] for i in range(4))
    q_rank_corr = _spearman_corr(np.arange(5, dtype=float), np.array(q_ann_means))

    # Q5 - Q1 spread series & significance test
    # For multi-day horizons (e.g. 21d), daily overlapped rebalance inherits (1/h) of the 21d signal plus 1d return
    q5_q1_period_spread = np.array(q_fwd_rets[4]) - np.array(q_fwd_rets[0]) if (q_fwd_rets[4] and q_fwd_rets[0]) else np.zeros(10)
    spread_t_stat, _ = compute_newey_west_tstat(q5_q1_period_spread, max_lag=horizon)
    spread_ann_pct = round(float(np.mean(q5_q1_period_spread) * ann_factor * 100.0), 2)

    # Daily cumulative Q5-Q1 alpha spread curve vs SPY benchmark (downsampled to ~120 points for fast UI rendering)
    # Use period-matched daily equivalent spread return so the cumulative curve matches the horizon return
    daily_spread = np.zeros(n_eval, dtype=float)
    for k in range(n_eval):
        if k < len(q5_q1_period_spread):
            daily_spread[k] = q5_q1_period_spread[k] / horizon
    spy_daily = u["mkt_returns"][eval_indices]

    cum_spread = np.cumprod(1.0 + daily_spread) - 1.0
    cum_spy = np.cumprod(1.0 + spy_daily) - 1.0

    # Rolling 63d Rank IC with +/- 2 sigma bands
    ic_s = pd.Series(ic_series)
    roll_mean = ic_s.rolling(window=63, min_periods=20).mean().to_numpy()
    roll_sd = ic_s.rolling(window=63, min_periods=20).std().to_numpy()

    step = max(1, n_eval // 120)
    chart_indices = list(range(0, n_eval, step))
    if chart_indices[-1] != n_eval - 1:
        chart_indices.append(n_eval - 1)

    cumulative_spread_chart = [
        {
            "date": eval_dates[i],
            "q5_q1_cum_pct": round(float(cum_spread[i] * 100.0), 2),
            "spy_cum_pct": round(float(cum_spy[i] * 100.0), 2),
        }
        for i in chart_indices
    ]

    rolling_ic_chart = []
    for i in chart_indices:
        if not np.isnan(roll_mean[i]):
            rm = float(roll_mean[i])
            rs = float(roll_sd[i]) if not np.isnan(roll_sd[i]) else sd_ic / math.sqrt(63.0)
            band = 2.0 * (rs / math.sqrt(63.0))
            rolling_ic_chart.append({
                "date": eval_dates[i],
                "rolling_ic": round(rm, 4),
                "upper_2sigma": round(rm + band, 4),
                "lower_2sigma": round(rm - band, 4),
                "daily_ic": round(float(ic_series[i]), 4) if not np.isnan(ic_series[i]) else 0.0,
            })

    # IC Decay Curve across horizons (1, 5, 21, 63, 126d)
    decay_curve = []
    sample_step = max(1, n_eval // 250)
    sample_eval = eval_indices[::sample_step]
    for h_cand in (1, 5, 21, 63, 126):
        fwd_c = u["fwd_returns"][h_cand]
        h_ics = []
        for t in sample_eval:
            if t < T - h_cand:
                sr = sig_mat[t]
                rr = fwd_c[t]
                vm = ~np.isnan(sr) & ~np.isnan(rr)
                if vm.sum() >= 10:
                    h_ics.append(_spearman_corr(sr[vm], rr[vm]))
        h_arr = np.array(h_ics, dtype=float)
        h_arr = h_arr[~np.isnan(h_arr)]
        m_h = float(np.mean(h_arr)) if len(h_arr) else 0.0
        s_h = float(np.std(h_arr, ddof=1)) if len(h_arr) > 1 else 0.01
        decay_curve.append({
            "horizon_days": h_cand,
            "mean_ic": round(m_h, 4),
            "ic_ir": round((m_h / (s_h + 1e-12)) * math.sqrt(252.0 / h_cand), 2),
        })

    # Fit exponential decay half-life t_{1/2}
    pos_decay = [(d["horizon_days"], max(abs(d["mean_ic"]), 1e-4)) for d in decay_curve]
    x_h = np.array([p[0] for p in pos_decay], dtype=float)
    y_log = np.log(np.array([p[1] for p in pos_decay], dtype=float))
    slope = float(np.polyfit(x_h, y_log, 1)[0])
    decay_lambda = max(0.001, -slope)
    half_life_days = round(min(252.0, math.log(2.0) / decay_lambda), 1)

    # IC by Year
    ic_by_year = []
    unique_years = sorted(set(eval_years))
    for yr in unique_years:
        ym = np.array([y == yr for y in eval_years], dtype=bool) & ~np.isnan(ic_series)
        if ym.sum() >= 5:
            y_ics = ic_series[ym]
            ic_by_year.append({
                "year": yr,
                "mean_ic": round(float(np.mean(y_ics)), 4),
                "ic_sd": round(float(np.std(y_ics, ddof=1)), 4),
                "hit_rate_pct": round(float(np.mean(y_ics > 0.0) * 100.0), 1),
                "n_days": int(ym.sum()),
            })

    # 11-Sector IC Boxplot Breakdown
    sector_boxplot = []
    for sec_name in GICS_11_SECTORS:
        arr_s = np.array(sector_ic_lists[sec_name], dtype=float)
        arr_s = arr_s[~np.isnan(arr_s)]
        if len(arr_s) >= 5:
            q10, q25, q50, q75, q90 = np.percentile(arr_s, [10.0, 25.0, 50.0, 75.0, 90.0])
            sector_boxplot.append({
                "sector": sec_name,
                "mean_ic": round(float(np.mean(arr_s)), 4),
                "min_p10": round(float(q10), 4),
                "q25": round(float(q25), 4),
                "median": round(float(q50), 4),
                "q75": round(float(q75), 4),
                "max_p90": round(float(q90), 4),
                "hit_rate_pct": round(float(np.mean(arr_s > 0.0) * 100.0), 1),
            })

    leakage = scan_signal_leakage(clean_name, sig_mat=sig_mat, lag=1)

    return {
        "signal_name": clean_name,
        "signal_meta": SIGNAL_CATALOG.get(clean_name, {"name": clean_name, "label": clean_name}),
        "horizon_days": horizon,
        "start_date": eval_dates[0],
        "end_date": eval_dates[-1],
        "n_days": int(len(valid_ics)),
        "summary": {
            "mean_ic": round(mean_ic, 4),
            "ic_sd": round(sd_ic, 4),
            "ic_ir": round(ic_ir, 2),
            "newey_west_t_stat": round(nw_t_stat, 2),
            "newey_west_se": round(nw_se, 5),
            "hit_rate_pct": round(hit_rate * 100.0, 1),
            "coverage_pct": std_diag["mean_coverage_pct"],
            "rank_autocorr_1d": round(float(np.mean(rank_autocorrs)), 4) if rank_autocorrs else 0.0,
            "q5_turnover_pct": round(float(np.mean(q5_turnovers)) * 100.0, 1) if q5_turnovers else 0.0,
            "q5_q1_annualized_spread_pct": spread_ann_pct,
            "q5_q1_t_stat": round(spread_t_stat, 2),
            "quintile_monotonic": is_strictly_monotonic,
            "quintile_rank_corr": round(q_rank_corr, 2),
            "half_life_days": half_life_days,
        },
        "standardisation": std_diag,
        "leakage_scan": leakage,
        "quintile_returns": quintile_summary,
        "ic_decay_curve": decay_curve,
        "ic_by_year": ic_by_year,
        "sector_ic_boxplot": sector_boxplot,
        "cumulative_spread_chart": cumulative_spread_chart,
        "rolling_ic_chart": rolling_ic_chart,
        "_provenance": {
            "source": "qra_ic_tearsheet_engine",
            "data_version": DATA_VERSION,
            "code_version": CODE_VERSION,
            "method": f"Spearman rank IC at horizon={horizon}d; Newey-West HAC lags={horizon}",
        },
    }


# ---------------------------------------------------------------------------
# QRA-005: Backtester with Transaction Costs, Market Impact & Lookahead Guard
# ---------------------------------------------------------------------------
def _compute_config_hash(config: Dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def run_backtest(
    signal_name: str = "planted_alpha_strong",
    rebalance_freq: str = "monthly",
    weighting: str = "equal_top_n",
    mode: str = "long_short",
    top_n: int = 20,
    max_weight: float = 0.08,
    sector_cap: float = 0.30,
    lag: int = 1,
    fixed_cost_bps: float = 5.0,
    impact_coeff: float = 0.10,
    aum: float = 10_000_000.0,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    custom_signal_mat: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Runs a configurable point-in-time backtest with fixed bps + square-root market
    impact costs and a 1-day default signal lag guard.
    """
    u = get_research_universe()
    clean_name = signal_name.strip().lower()
    rebalance_freq = rebalance_freq.strip().lower()
    weighting = weighting.strip().lower()
    mode = mode.strip().lower()
    lag = max(0, int(lag))

    reb_step = {"daily": 1, "weekly": 5, "monthly": 21}.get(rebalance_freq, 21)

    if custom_signal_mat is not None:
        sig_mat, _ = process_signal_matrix(
            custom_signal_mat,
            winsorize=True,
            sector_neutral=sector_neutral,
            beta_neutral=beta_neutral,
            zscore=True,
        )
    else:
        sig_mat, _ = get_standardized_signal(
            clean_name,
            winsorize=True,
            sector_neutral=sector_neutral,
            beta_neutral=beta_neutral,
            zscore=True,
        )

    dates = u["dates"]
    T, N = sig_mat.shape
    s_idx = int(np.searchsorted(dates, start_date, side="left")) if start_date else 252
    e_idx = int(np.searchsorted(dates, end_date, side="right")) - 1 if end_date else T - 2
    s_idx = max(252, min(s_idx, T - 60))
    e_idx = max(s_idx + 40, min(e_idx, T - 2))

    config_canonical = {
        "signal_name": clean_name,
        "rebalance_freq": rebalance_freq,
        "weighting": weighting,
        "mode": mode,
        "top_n": int(top_n),
        "max_weight": round(float(max_weight), 4),
        "sector_cap": round(float(sector_cap), 4),
        "lag": int(lag),
        "fixed_cost_bps": round(float(fixed_cost_bps), 2),
        "impact_coeff": round(float(impact_coeff), 4),
        "aum": round(float(aum), 2),
        "sector_neutral": bool(sector_neutral),
        "beta_neutral": bool(beta_neutral),
        "start_date": dates[s_idx],
        "end_date": dates[e_idx],
    }
    config_hash = _compute_config_hash(config_canonical)

    fwd_1 = u["fwd_returns"][1]  # fwd_1[t] is the return earned from close_t to close_{t+1}
    vols = u["annual_vols"] / math.sqrt(252.0)
    adv_d = u["adv_dollars"]
    sector_ids = u["sector_ids"]
    active_mask = u["active_mask"]

    eval_indices = list(range(s_idx, e_idx + 1))
    n_days = len(eval_indices)

    gross_rets = np.zeros(n_days, dtype=float)
    net_rets = np.zeros(n_days, dtype=float)
    cost_drag = np.zeros(n_days, dtype=float)
    turnovers = []

    w_current = np.zeros(N, dtype=float)

    def _apply_caps(w_side: np.ndarray, max_w: float, sec_cap: float) -> np.ndarray:
        """Applies single-name max_weight and sector_cap to a non-negative weight vector summing to 1."""
        if w_side.sum() <= 1e-12:
            return w_side
        w = w_side / w_side.sum()
        for _ in range(3):
            w = np.minimum(w, max_w)
            for s_id in range(len(GICS_11_SECTORS)):
                sm = sector_ids == s_id
                sec_sum = float(w[sm].sum())
                if sec_sum > sec_cap and sec_sum > 1e-12:
                    w[sm] *= sec_cap / sec_sum
            rem = 1.0 - float(w.sum())
            if rem <= 1e-6:
                break
            room = (w > 0) & (w < max_w - 1e-6)
            if room.sum() == 0:
                break
            w[room] += rem * (w[room] / w[room].sum())
        if w.sum() > 1e-12:
            w /= w.sum()
        return w

    for k, t in enumerate(eval_indices):
        # Rebalance decision at close_t uses signal from day (t - lag) to earn return fwd_1[t] (close_t -> close_{t+1})
        sig_idx = max(0, t - lag)
        need_rebalance = (k % reb_step == 0)

        if need_rebalance:
            s_row = sig_mat[sig_idx]
            valid = active_mask[t] & ~np.isnan(s_row) & ~np.isnan(fwd_1[t])
            v_cols = np.where(valid)[0]
            w_target = np.zeros(N, dtype=float)

            if len(v_cols) >= 10:
                if weighting == "universe_equal":
                    w_target[v_cols] = 1.0 / len(v_cols)
                else:
                    s_vals = s_row[v_cols]
                    order = np.argsort(s_vals)
                    n_pick = max(2, min(int(top_n), len(v_cols) // 2))
                    long_cols = v_cols[order[-n_pick:]]
                    short_cols = v_cols[order[:n_pick]]

                    w_long = np.zeros(N, dtype=float)
                    if weighting == "signal_proportional":
                        scores_l = np.maximum(0.05, s_row[long_cols] - np.min(s_row[long_cols]) + 0.1)
                        w_long[long_cols] = scores_l / np.sum(scores_l)
                    elif weighting == "vol_scaled":
                        inv_v = 1.0 / np.maximum(0.005, vols[long_cols])
                        w_long[long_cols] = inv_v / np.sum(inv_v)
                    else:
                        w_long[long_cols] = 1.0 / len(long_cols)
                    w_long = _apply_caps(w_long, max_weight, sector_cap)

                    if mode == "long_short":
                        w_short = np.zeros(N, dtype=float)
                        if weighting == "signal_proportional":
                            scores_s = np.maximum(0.05, np.max(s_row[short_cols]) - s_row[short_cols] + 0.1)
                            w_short[short_cols] = scores_s / np.sum(scores_s)
                        elif weighting == "vol_scaled":
                            inv_vs = 1.0 / np.maximum(0.005, vols[short_cols])
                            w_short[short_cols] = inv_vs / np.sum(inv_vs)
                        else:
                            w_short[short_cols] = 1.0 / len(short_cols)
                        w_short = _apply_caps(w_short, max_weight, sector_cap)
                        w_target = w_long - w_short
                    else:
                        w_target = w_long

            dw = np.abs(w_target - w_current)
            one_way_to = float(0.5 * np.sum(dw))
            turnovers.append(one_way_to)

            # Transaction cost: fixed_bps * sum(|dw|) + sum(|dw| * k * sigma_i * sqrt(trade_$ / ADV_$))
            fixed_rate = (fixed_cost_bps / 10000.0) * float(np.sum(dw))
            trade_dollars = dw * aum
            impact_rate = float(
                np.sum(dw * impact_coeff * vols * np.sqrt(trade_dollars / np.maximum(1e5, adv_d)))
            )
            total_cost = fixed_rate + impact_rate
            cost_drag[k] = total_cost
            w_current = w_target
        else:
            # Zero out any stock that delisted today
            inactive = ~active_mask[t] | np.isnan(fwd_1[t])
            if np.any(w_current[inactive] != 0.0):
                w_current = w_current.copy()
                w_current[inactive] = 0.0

        r_day = np.nan_to_num(fwd_1[t], nan=0.0)
        g_ret = float(np.dot(w_current, r_day))
        gross_rets[k] = g_ret
        net_rets[k] = g_ret - cost_drag[k]

    spy_rets = u["mkt_returns"][eval_indices]
    eval_dates = [dates[t] for t in eval_indices]

    def _summarize_returns(r_arr: np.ndarray) -> Dict[str, float]:
        eq = np.cumprod(1.0 + r_arr)
        years_span = max(0.1, len(r_arr) / 252.0)
        cagr = float(eq[-1] ** (1.0 / years_span) - 1.0) if eq[-1] > 0 else -0.99
        ann_mean = float(np.mean(r_arr) * 252.0)
        ann_vol = float(np.std(r_arr, ddof=1) * math.sqrt(252.0))
        sharpe = ann_mean / max(1e-6, ann_vol)
        down = r_arr[r_arr < 0.0]
        down_vol = float(np.std(down, ddof=1) * math.sqrt(252.0)) if len(down) > 1 else max(1e-6, ann_vol)
        sortino = ann_mean / max(1e-6, down_vol)
        peaks = np.maximum.accumulate(eq)
        dd = (eq - peaks) / peaks
        max_dd = float(np.min(dd))
        calmar = cagr / max(1e-4, abs(max_dd))
        hit = float(np.mean(r_arr > 0.0))
        return {
            "cagr_pct": round(cagr * 100.0, 2),
            "annual_return_pct": round(ann_mean * 100.0, 2),
            "annual_vol_pct": round(ann_vol * 100.0, 2),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "max_drawdown_pct": round(max_dd * 100.0, 2),
            "calmar": round(calmar, 2),
            "hit_rate_pct": round(hit * 100.0, 1),
            "cumulative_return_pct": round(float((eq[-1] - 1.0) * 100.0), 2),
        }

    gross_metrics = _summarize_returns(gross_rets)
    net_metrics = _summarize_returns(net_rets)
    spy_metrics = _summarize_returns(spy_rets)

    # CAPM Alpha & Beta vs SPY on Net Returns
    X_capm = np.column_stack([np.ones(n_days), spy_rets])
    coef, _, _, _ = np.linalg.lstsq(X_capm, net_rets, rcond=None)
    alpha_daily, beta_spy = float(coef[0]), float(coef[1])
    resid = net_rets - (X_capm @ coef)
    s2_res = float(np.dot(resid, resid) / max(1, n_days - 2))
    xtx_inv = np.linalg.pinv(X_capm.T @ X_capm)
    se_alpha = math.sqrt(max(1e-12, s2_res * xtx_inv[0, 0]))
    se_beta = math.sqrt(max(1e-12, s2_res * xtx_inv[1, 1]))
    alpha_t = alpha_daily / se_alpha
    beta_t = beta_spy / se_beta
    r2_capm = 1.0 - (float(np.var(resid)) / max(1e-12, float(np.var(net_rets))))

    rebs_per_year = 252.0 / reb_step
    ann_turnover = float(np.mean(turnovers) * rebs_per_year) if turnovers else 0.0
    ann_cost_bps = float(np.sum(cost_drag) * (252.0 / n_days) * 10000.0)

    # Equity curve, drawdown, rolling 252d Sharpe
    eq_gross = np.cumprod(1.0 + gross_rets)
    eq_net = np.cumprod(1.0 + net_rets)
    eq_spy = np.cumprod(1.0 + spy_rets)
    peaks_net = np.maximum.accumulate(eq_net)
    dd_net = (eq_net - peaks_net) / peaks_net

    net_s = pd.Series(net_rets)
    roll_sharpe = (
        (net_s.rolling(252, min_periods=63).mean() * 252.0)
        / (net_s.rolling(252, min_periods=63).std() * math.sqrt(252.0) + 1e-9)
    ).to_numpy()

    step = max(1, n_days // 120)
    c_idx = list(range(0, n_days, step))
    if c_idx[-1] != n_days - 1:
        c_idx.append(n_days - 1)

    equity_chart = [
        {
            "date": eval_dates[i],
            "gross": round(float(eq_gross[i]), 4),
            "net": round(float(eq_net[i]), 4),
            "spy": round(float(eq_spy[i]), 4),
            "drawdown_pct": round(float(dd_net[i] * 100.0), 2),
            "rolling_sharpe": round(float(roll_sharpe[i]), 2) if not np.isnan(roll_sharpe[i]) else None,
        }
        for i in c_idx
    ]

    # Monthly returns heatmap (year x month)
    df_m = pd.DataFrame({
        "date": pd.to_datetime(eval_dates),
        "ret": net_rets,
    })
    df_m["year"] = df_m["date"].dt.year
    df_m["month"] = df_m["date"].dt.month
    monthly_grouped = df_m.groupby(["year", "month"])["ret"].apply(lambda x: float(np.prod(1.0 + x) - 1.0))
    monthly_heatmap = []
    for (yr, mo), val in monthly_grouped.items():
        monthly_heatmap.append({
            "year": int(yr),
            "month": int(mo),
            "return_pct": round(val * 100.0, 2),
        })

    leakage = scan_signal_leakage(clean_name, sig_mat=sig_mat, lag=lag)

    return {
        "config": config_canonical,
        "config_hash": config_hash,
        "code_version": CODE_VERSION,
        "data_version": DATA_VERSION,
        "gross_metrics": gross_metrics,
        "net_metrics": net_metrics,
        "benchmark_spy_metrics": spy_metrics,
        "capm_vs_spy": {
            "alpha_annual_pct": round(alpha_daily * 252.0 * 100.0, 2),
            "alpha_t_stat": round(alpha_t, 2),
            "beta": round(beta_spy, 3),
            "beta_t_stat": round(beta_t, 2),
            "r_squared": round(max(0.0, r2_capm), 3),
        },
        "costs_and_turnover": {
            "annual_one_way_turnover_pct": round(ann_turnover * 100.0, 1),
            "annual_cost_drag_bps": round(ann_cost_bps, 1),
            "gross_minus_net_cagr_pct": round(gross_metrics["cagr_pct"] - net_metrics["cagr_pct"], 2),
        },
        "leakage_scan": leakage,
        "equity_chart": equity_chart,
        "monthly_returns": monthly_heatmap,
        "daily_net_returns": [round(float(x), 6) for x in net_rets],
        "_provenance": {
            "source": "qra_backtester",
            "config_hash": config_hash,
            "code_version": CODE_VERSION,
            "data_version": DATA_VERSION,
        },
    }


# ---------------------------------------------------------------------------
# QRA-006: Experiment Tracking (`research_runs` Table & Run Comparison)
# ---------------------------------------------------------------------------
_SCHEMA_READY = False


def ensure_qra_schema() -> None:
    """Creates `research_runs` and `qra_screener_handoffs` tables if not present and seeds baseline runs."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from agents.db import query

    query(
        """
        CREATE TABLE IF NOT EXISTS research_runs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            question_key VARCHAR(120) NOT NULL DEFAULT 'general_alpha',
            run_type VARCHAR(40) NOT NULL DEFAULT 'backtest',
            signal_name VARCHAR(80) NOT NULL,
            config_json JSONB NOT NULL,
            config_hash VARCHAR(64) NOT NULL,
            code_version VARCHAR(32) NOT NULL,
            data_version VARCHAR(32) NOT NULL,
            metrics_json JSONB NOT NULL,
            equity_curve_json JSONB NOT NULL,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            notes TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    query("CREATE INDEX IF NOT EXISTS idx_research_runs_hash ON research_runs(config_hash);")
    query("CREATE INDEX IF NOT EXISTS idx_research_runs_question ON research_runs(question_key);")

    query(
        """
        CREATE TABLE IF NOT EXISTS qra_screener_handoffs (
            id SERIAL PRIMARY KEY,
            strategy_name VARCHAR(120) NOT NULL,
            config_hash VARCHAR(64) NOT NULL,
            dsr NUMERIC(8, 4) NOT NULL,
            oos_sharpe NUMERIC(8, 4) NOT NULL,
            weights_json JSONB NOT NULL,
            candidates_json JSONB NOT NULL,
            filters_query TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    existing = query("SELECT COUNT(*) AS cnt FROM research_runs").rows[0]["cnt"]
    if int(existing) == 0:
        seed_configs = [
            ("planted_alpha_strong", "monthly", "equal_top_n", "long_short", 1, 5.0, "planted_validation", ["benchmark", "strong_alpha", "verified"], "Baseline strong planted alpha (IC~0.05) monthly L/S."),
            ("planted_alpha_weak", "monthly", "equal_top_n", "long_short", 1, 5.0, "planted_validation", ["benchmark", "weak_alpha"], "Baseline weak planted alpha (IC~0.02) monthly L/S."),
            ("planted_noise", "monthly", "equal_top_n", "long_short", 1, 5.0, "noise_sweep", ["benchmark", "noise"], "Zero-skill planted noise baseline."),
            ("momentum_12_1", "monthly", "vol_scaled", "long_short", 1, 5.0, "style_factors", ["momentum", "vol_scaled"], "12-1M cross-sectional momentum with vol-scaling."),
        ]
        for sig, freq, w_mode, mode, lg, bps, q_key, tags, note in seed_configs:
            bt = run_backtest(
                signal_name=sig,
                rebalance_freq=freq,
                weighting=w_mode,
                mode=mode,
                lag=lg,
                fixed_cost_bps=bps,
            )
            save_research_run(
                signal_name=sig,
                run_type="backtest",
                question_key=q_key,
                config=bt["config"],
                config_hash=bt["config_hash"],
                metrics={
                    "net": bt["net_metrics"],
                    "gross": bt["gross_metrics"],
                    "capm": bt["capm_vs_spy"],
                    "costs": bt["costs_and_turnover"],
                    "leakage_badge": bt["leakage_scan"]["badge"],
                },
                equity_curve=bt["equity_chart"],
                tags=tags,
                notes=note,
                skip_ensure=True,
            )

    _SCHEMA_READY = True


def save_research_run(
    signal_name: str,
    run_type: str,
    question_key: str,
    config: Dict[str, Any],
    config_hash: str,
    metrics: Dict[str, Any],
    equity_curve: List[Dict[str, Any]],
    tags: Optional[List[str]] = None,
    notes: str = "",
    user_id: Optional[int] = None,
    skip_ensure: bool = False,
) -> Dict[str, Any]:
    """Saves a backtest or tear-sheet experiment run to `research_runs`."""
    if not skip_ensure:
        ensure_qra_schema()
    from agents.db import query

    res = query(
        """
        INSERT INTO research_runs
            (user_id, question_key, run_type, signal_name, config_json, config_hash,
             code_version, data_version, metrics_json, equity_curve_json, tags, notes)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        RETURNING id, question_key, run_type, signal_name, config_json, config_hash,
                  code_version, data_version, metrics_json, tags, notes, created_at
        """,
        [
            user_id,
            question_key or "general_alpha",
            run_type or "backtest",
            signal_name,
            json.dumps(config),
            config_hash,
            CODE_VERSION,
            DATA_VERSION,
            json.dumps(metrics),
            json.dumps(equity_curve),
            json.dumps(tags or []),
            notes or "",
        ],
    )
    row = res.rows[0]
    row["created_at"] = row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"])
    return row


def list_research_runs(question_key: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, Any]:
    """Lists tracked research runs with per-question trial counts."""
    ensure_qra_schema()
    from agents.db import query

    rows = query(
        """
        SELECT id, user_id, question_key, run_type, signal_name, config_json,
               config_hash, code_version, data_version, metrics_json, tags, notes, created_at
        FROM research_runs
        ORDER BY id DESC
        LIMIT 100
        """
    ).rows

    trial_counts: Dict[str, int] = {}
    formatted = []
    for r in rows:
        qk = r["question_key"]
        trial_counts[qk] = trial_counts.get(qk, 0) + 1
        r_tags = r["tags"] if isinstance(r["tags"], list) else []
        if question_key and qk != question_key:
            continue
        if tag and tag not in r_tags:
            continue
        formatted.append({
            **r,
            "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        })

    return {
        "runs": formatted,
        "total_runs": len(rows),
        "trial_counts_by_question": trial_counts,
        "_provenance": {
            "source": "research_runs_db",
            "code_version": CODE_VERSION,
            "data_version": DATA_VERSION,
        },
    }


def compare_research_runs(run_ids: List[int]) -> Dict[str, Any]:
    """Side-by-side comparison of 2 to 4 research runs with overlaid equity curves."""
    ensure_qra_schema()
    from agents.db import query

    clean_ids = [int(i) for i in run_ids][:4]
    if not clean_ids:
        raise ValueError("Provide at least 1 run_id to compare")

    placeholders = ",".join(["%s"] * len(clean_ids))
    rows = query(
        f"""
        SELECT id, question_key, run_type, signal_name, config_json, config_hash,
               code_version, data_version, metrics_json, equity_curve_json, tags, notes, created_at
        FROM research_runs
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        clean_ids,
    ).rows

    # Build aligned overlaid equity curve by date
    date_map: Dict[str, Dict[str, Any]] = {}
    runs_out = []
    for r in rows:
        rid = r["id"]
        key = f"run_{rid}"
        eq = r["equity_curve_json"] or []
        for pt in eq:
            d = pt["date"]
            if d not in date_map:
                date_map[d] = {"date": d, "spy": pt.get("spy", 1.0)}
            date_map[d][key] = pt.get("net", 1.0)
        runs_out.append({
            "id": rid,
            "series_key": key,
            "signal_name": r["signal_name"],
            "question_key": r["question_key"],
            "config": r["config_json"],
            "config_hash": r["config_hash"],
            "code_version": r["code_version"],
            "data_version": r["data_version"],
            "metrics": r["metrics_json"],
            "tags": r["tags"],
            "notes": r["notes"],
            "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        })

    overlaid_curve = [date_map[d] for d in sorted(date_map.keys())]
    return {
        "compared_run_ids": [r["id"] for r in runs_out],
        "runs": runs_out,
        "overlaid_equity_curve": overlaid_curve,
    }


def update_research_run_meta(run_id: int, tags: Optional[List[str]] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Updates tags or researcher notes on an existing experiment run."""
    ensure_qra_schema()
    from agents.db import query

    existing = query("SELECT id, tags, notes FROM research_runs WHERE id = %s", [run_id]).rows
    if not existing:
        raise ValueError(f"Run {run_id} not found")
    new_tags = tags if tags is not None else existing[0]["tags"]
    new_notes = notes if notes is not None else existing[0]["notes"]

    res = query(
        """
        UPDATE research_runs
        SET tags = %s::jsonb, notes = %s
        WHERE id = %s
        RETURNING id, question_key, signal_name, config_hash, tags, notes, created_at
        """,
        [json.dumps(new_tags), new_notes, run_id],
    ).rows[0]
    res["created_at"] = res["created_at"].isoformat() if hasattr(res["created_at"], "isoformat") else str(res["created_at"])
    return res
