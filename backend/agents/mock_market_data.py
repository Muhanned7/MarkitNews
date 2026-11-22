"""
Deterministic Seeded Per-Ticker Mock Market Data Generator
Provides realistic, internally consistent single-stock & multi-asset market data
for quantitative portfolio analysis when MOCK_MODE is True.
"""

import hashlib
import math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Anchor profiles for major benchmark tickers
ANCHOR_PROFILES = {
    "AAPL": {
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "base_price": 228.50,
        "base_vol": 0.225,
        "beta": 1.12,
        "pe": 32.4,
        "fwd_pe": 28.5,
        "roe": 1.45,
        "pm": 0.264,
        "fcf": 108_000_000_000,
        "adv_shares": 48_500_000,
        "rec": "buy",
        "conviction": 8,
    },
    "MSFT": {
        "company_name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "base_price": 428.15,
        "base_vol": 0.235,
        "beta": 1.18,
        "pe": 35.8,
        "fwd_pe": 31.2,
        "roe": 0.38,
        "pm": 0.355,
        "fcf": 74_000_000_000,
        "adv_shares": 21_200_000,
        "rec": "buy",
        "conviction": 8,
    },
    "NVDA": {
        "company_name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "base_price": 134.80,
        "base_vol": 0.465,
        "beta": 1.94,
        "pe": 48.2,
        "fwd_pe": 36.5,
        "roe": 0.92,
        "pm": 0.550,
        "fcf": 52_000_000_000,
        "adv_shares": 52_000_000,
        "rec": "buy",
        "conviction": 9,
    },
    "TSLA": {
        "company_name": "Tesla, Inc.",
        "sector": "Consumer Discretionary",
        "industry": "Auto Manufacturers",
        "base_price": 244.50,
        "base_vol": 0.540,
        "beta": 2.15,
        "pe": 68.5,
        "fwd_pe": 55.0,
        "roe": 0.18,
        "pm": 0.142,
        "fcf": 8_500_000_000,
        "adv_shares": 72_000_000,
        "rec": "hold",
        "conviction": 5,
    },
    "JPM": {
        "company_name": "JPMorgan Chase & Co.",
        "sector": "Financials",
        "industry": "Banks - Diversified",
        "base_price": 218.40,
        "base_vol": 0.185,
        "beta": 0.88,
        "pe": 12.6,
        "fwd_pe": 11.4,
        "roe": 0.17,
        "pm": 0.320,
        "fcf": 35_000_000_000,
        "adv_shares": 9_400_000,
        "rec": "buy",
        "conviction": 7,
    },
    "XOM": {
        "company_name": "Exxon Mobil Corporation",
        "sector": "Energy",
        "industry": "Oil & Gas Integrated",
        "base_price": 119.20,
        "base_vol": 0.205,
        "beta": 0.74,
        "pe": 14.2,
        "fwd_pe": 12.8,
        "roe": 0.19,
        "pm": 0.115,
        "fcf": 36_000_000_000,
        "adv_shares": 14_800_000,
        "rec": "hold",
        "conviction": 6,
    },
    "GOOGL": {
        "company_name": "Alphabet Inc.",
        "sector": "Communication Services",
        "industry": "Internet Content & Information",
        "base_price": 167.30,
        "base_vol": 0.258,
        "beta": 1.06,
        "pe": 24.2,
        "fwd_pe": 20.8,
        "roe": 0.29,
        "pm": 0.275,
        "fcf": 69_000_000_000,
        "adv_shares": 22_500_000,
        "rec": "buy",
        "conviction": 8,
    },
    "AMZN": {
        "company_name": "Amazon.com, Inc.",
        "sector": "Consumer Discretionary",
        "industry": "Internet Retail",
        "base_price": 189.60,
        "base_vol": 0.285,
        "beta": 1.22,
        "pe": 41.5,
        "fwd_pe": 32.0,
        "roe": 0.22,
        "pm": 0.082,
        "fcf": 48_000_000_000,
        "adv_shares": 34_000_000,
        "rec": "buy",
        "conviction": 8,
    },
    "SPY": {
        "company_name": "SPDR S&P 500 ETF Trust",
        "sector": "Index",
        "industry": "Broad Market ETF",
        "base_price": 582.50,
        "base_vol": 0.138,
        "beta": 1.00,
        "pe": 24.8,
        "fwd_pe": 22.0,
        "roe": 0.20,
        "pm": 0.120,
        "fcf": 0,
        "adv_shares": 65_000_000,
        "rec": "buy",
        "conviction": 7,
    },
    "XLK": {
        "company_name": "Technology Select Sector SPDR Fund",
        "sector": "Technology",
        "industry": "Sector ETF",
        "base_price": 226.40,
        "base_vol": 0.210,
        "beta": 1.18,
        "pe": 31.5,
        "fwd_pe": 27.0,
        "roe": 0.32,
        "pm": 0.240,
        "fcf": 0,
        "adv_shares": 8_500_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLF": {
        "company_name": "Financial Select Sector SPDR Fund",
        "sector": "Financials",
        "industry": "Sector ETF",
        "base_price": 46.80,
        "base_vol": 0.165,
        "beta": 0.94,
        "pe": 15.8,
        "fwd_pe": 14.2,
        "roe": 0.15,
        "pm": 0.220,
        "fcf": 0,
        "adv_shares": 38_000_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLE": {
        "company_name": "Energy Select Sector SPDR Fund",
        "sector": "Energy",
        "industry": "Sector ETF",
        "base_price": 91.20,
        "base_vol": 0.215,
        "beta": 0.78,
        "pe": 13.4,
        "fwd_pe": 12.1,
        "roe": 0.18,
        "pm": 0.110,
        "fcf": 0,
        "adv_shares": 16_000_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLV": {
        "company_name": "Health Care Select Sector SPDR Fund",
        "sector": "Healthcare",
        "industry": "Sector ETF",
        "base_price": 152.10,
        "base_vol": 0.145,
        "beta": 0.72,
        "pe": 21.0,
        "fwd_pe": 18.5,
        "roe": 0.21,
        "pm": 0.150,
        "fcf": 0,
        "adv_shares": 9_200_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLY": {
        "company_name": "Consumer Discretionary Select Sector SPDR Fund",
        "sector": "Consumer Discretionary",
        "industry": "Sector ETF",
        "base_price": 198.50,
        "base_vol": 0.205,
        "beta": 1.15,
        "pe": 26.4,
        "fwd_pe": 22.8,
        "roe": 0.24,
        "pm": 0.095,
        "fcf": 0,
        "adv_shares": 6_400_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLI": {
        "company_name": "Industrial Select Sector SPDR Fund",
        "sector": "Industrials",
        "industry": "Sector ETF",
        "base_price": 135.40,
        "base_vol": 0.160,
        "beta": 0.98,
        "pe": 22.1,
        "fwd_pe": 19.6,
        "roe": 0.19,
        "pm": 0.115,
        "fcf": 0,
        "adv_shares": 8_800_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLC": {
        "company_name": "Communication Services Select Sector SPDR Fund",
        "sector": "Communication Services",
        "industry": "Sector ETF",
        "base_price": 90.60,
        "base_vol": 0.185,
        "beta": 1.04,
        "pe": 20.5,
        "fwd_pe": 18.0,
        "roe": 0.18,
        "pm": 0.165,
        "fcf": 0,
        "adv_shares": 5_900_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLP": {
        "company_name": "Consumer Staples Select Sector SPDR Fund",
        "sector": "Consumer Staples",
        "industry": "Sector ETF",
        "base_price": 81.90,
        "base_vol": 0.125,
        "beta": 0.58,
        "pe": 21.8,
        "fwd_pe": 19.9,
        "roe": 0.22,
        "pm": 0.088,
        "fcf": 0,
        "adv_shares": 11_500_000,
        "rec": "hold",
        "conviction": 6,
    },
    "XLU": {
        "company_name": "Utilities Select Sector SPDR Fund",
        "sector": "Utilities",
        "industry": "Sector ETF",
        "base_price": 79.30,
        "base_vol": 0.150,
        "beta": 0.55,
        "pe": 18.2,
        "fwd_pe": 16.8,
        "roe": 0.11,
        "pm": 0.135,
        "fcf": 0,
        "adv_shares": 12_200_000,
        "rec": "hold",
        "conviction": 6,
    }
}

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Communication Services": "XLC",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
}

SECTORS = [
    "Technology", "Healthcare", "Financials", 
    "Consumer Discretionary", "Energy", "Industrials", 
    "Communication Services", "Consumer Staples", "Utilities"
]

def _ticker_seed(ticker: str) -> int:
    clean = ticker.strip().upper()
    digest = hashlib.md5(clean.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)

# ---------------------------------------------------------------------------
# RSK-001: fat tails + volatility clustering + injected market stress episodes
# ---------------------------------------------------------------------------
# Returns are R_stock = beta * R_market + idio, where both the market factor and
# the idiosyncratic component follow GARCH(1,1) with standardized Student-t shocks:
#   sigma2_t = omega + alpha * eps2_{t-1} + beta * sigma2_{t-1}
# omega is set so the unconditional vol equals the target vol.
N_HISTORY_DAYS = 504
MARKET_ANNUAL_VOL = 0.138
MARKET_ANNUAL_DRIFT = 0.10
T_DOF = 6.0             # Student-t degrees of freedom (spec: 4-6)
T_CLIP_SIGMA = 6.0      # clip standardized shocks at +/-6 sigma so one draw cannot dominate sample moments
GARCH_ALPHA = 0.15      # ARCH term; alpha + beta = 0.98 persistence
GARCH_BETA = 0.83       # GARCH term
STRESS_VOL_MULTIPLIER = 3.0  # market-factor vol multiplier inside stress windows -> correlations rise
HISTORY_END_DATE = datetime(2026, 10, 14)

# Two market-wide stress episodes, indexed into the 504-day history (0 = oldest).
STRESS_WINDOWS = [
    {"name": "Liquidity shock (5d)", "key": "liquidity_shock_5d", "start": 120, "length": 5, "market_return": -0.12},
    {"name": "Drawdown (20d)", "key": "drawdown_20d", "start": 360, "length": 20, "market_return": -0.20},
]


def _history_dates(n_days: int = N_HISTORY_DAYS) -> list:
    """Business-day calendar for the mock history, ending on HISTORY_END_DATE."""
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(end=HISTORY_END_DATE, periods=n_days)]


def get_stress_windows(n_days: int = N_HISTORY_DAYS) -> list:
    """Injected stress windows with index ranges and calendar dates (for UI, backtests and diagnostics)."""
    dates = _history_dates(n_days)
    out = []
    for w in STRESS_WINDOWS:
        start, end = w["start"], w["start"] + w["length"] - 1
        out.append({
            **w,
            "end": end,
            "start_date": dates[start],
            "end_date": dates[end],
            "index_in_252d": (start - (n_days - 252)) if start >= n_days - 252 else None,
        })
    return out


def stress_mask(n_days: int = N_HISTORY_DAYS) -> np.ndarray:
    """Boolean mask over the 504-day history: True inside injected stress windows."""
    m = np.zeros(n_days, dtype=bool)
    for w in STRESS_WINDOWS:
        m[w["start"]:w["start"] + w["length"]] = True
    return m


def _standardized_t(rng: np.random.RandomState, n: int) -> np.ndarray:
    """Unit-variance Student-t draws, clipped at +/- T_CLIP_SIGMA."""
    z = rng.standard_t(T_DOF, n) / math.sqrt(T_DOF / (T_DOF - 2.0))
    return np.clip(z, -T_CLIP_SIGMA, T_CLIP_SIGMA)


def _garch_t_path(rng: np.random.RandomState, n: int, annual_vol: float,
                  drift: np.ndarray = None, vol_mult: np.ndarray = None) -> np.ndarray:
    """
    GARCH(1,1) path with Student-t shocks and unconditional vol = annual_vol.
    vol_mult scales the realised shock (exogenous stress overlay) without feeding
    back into the variance recursion, so the process stays stationary.
    """
    var_u = (annual_vol / math.sqrt(252.0)) ** 2
    omega = var_u * (1.0 - GARCH_ALPHA - GARCH_BETA)
    z = _standardized_t(rng, n)
    out = np.empty(n)
    s2 = var_u
    prev = 0.0
    for t in range(n):
        if t:
            s2 = omega + GARCH_ALPHA * prev * prev + GARCH_BETA * s2
        base = math.sqrt(s2) * z[t]
        mult = 1.0 if vol_mult is None else vol_mult[t]
        mu = 0.0 if drift is None else drift[t]
        out[t] = mu + mult * base
        prev = base
    return out


_MARKET_CACHE = {}


def generate_market_returns(n_days: int = N_HISTORY_DAYS) -> np.ndarray:
    """
    Fixed reproducible benchmark (SPY) daily returns for up to 504 trading days (2 years).
    GARCH(1,1)-t market factor (seed 42) with two injected stress episodes: inside each
    window the drift delivers the episode's total market return and vol is x3.
    """
    if n_days not in _MARKET_CACHE:
        drift = np.full(n_days, MARKET_ANNUAL_DRIFT / 252.0)
        vol_mult = np.ones(n_days)
        for w in STRESS_WINDOWS:
            if w["start"] + w["length"] <= n_days:
                sl = slice(w["start"], w["start"] + w["length"])
                drift[sl] = math.log1p(w["market_return"]) / w["length"]
                vol_mult[sl] = STRESS_VOL_MULTIPLIER
        rng = np.random.RandomState(42)
        _MARKET_CACHE[n_days] = _garch_t_path(rng, n_days, MARKET_ANNUAL_VOL, drift, vol_mult)
    return _MARKET_CACHE[n_days].copy()

def get_deterministic_mock_profile(ticker: str) -> dict:
    """
    Produces deterministic, internally consistent single-stock profile and 1-year history.
    """
    clean = ticker.strip().upper()
    seed = _ticker_seed(clean)
    
    if clean in ANCHOR_PROFILES:
        anchor = ANCHOR_PROFILES[clean]
        sector = anchor["sector"]
        industry = anchor["industry"]
        current_price = anchor["base_price"]
        annual_vol = anchor["base_vol"]
        beta = anchor["beta"]
        pe = anchor["pe"]
        fwd_pe = anchor["fwd_pe"]
        roe = anchor["roe"]
        pm = anchor["pm"]
        fcf = anchor["fcf"]
        adv_shares = anchor["adv_shares"]
        rec = anchor["rec"]
        conviction = anchor["conviction"]
        company_name = anchor["company_name"]
    else:
        sector = SECTORS[seed % len(SECTORS)]
        industry = f"{sector} Solutions"
        current_price = round(35.0 + (seed % 280) + ((seed >> 4) % 100) / 100.0, 2)
        annual_vol = round(0.18 + ((seed >> 2) % 35) / 100.0, 3)
        beta = round(0.65 + ((seed >> 5) % 140) / 100.0, 2)
        pe = round(14.0 + ((seed >> 3) % 400) / 10.0, 1)
        fwd_pe = round(pe * 0.88, 1)
        roe = round(0.12 + ((seed >> 6) % 30) / 100.0, 2)
        pm = round(0.08 + ((seed >> 7) % 25) / 100.0, 2)
        fcf = int((seed % 15 + 1) * 1_000_000_000)
        adv_shares = int(2_000_000 + (seed % 35_000_000))
        company_name = f"{clean} Corporation"
        rec_val = seed % 3
        rec = "buy" if rec_val == 0 else ("hold" if rec_val == 1 else "sell")
        conviction = 5 + (seed % 5)

    # Multi-factor return simulation: R_stock = beta * R_m + idiosyncratic (504 days)
    mkt_returns = generate_market_returns(504)
    stock_rng = np.random.RandomState(seed % 100000)
    
    idio_vol = math.sqrt(max(0.001, (annual_vol ** 2) - ((beta * MARKET_ANNUAL_VOL) ** 2)))
    # RSK-001: idiosyncratic GARCH(1,1)-t component (same per-ticker seed as before)
    idio_returns = _garch_t_path(stock_rng, 504, idio_vol)
    
    daily_returns_504 = (beta * mkt_returns) + idio_returns
    
    # Calculate R-squared vs market over trailing 252d
    cov_matrix = np.cov(daily_returns_504[-252:], mkt_returns[-252:])
    corr = cov_matrix[0, 1] / (np.std(daily_returns_504[-252:]) * np.std(mkt_returns[-252:]) + 1e-9)
    r_squared = round(float(corr ** 2), 2)
    
    # Generate price path ending exactly at current_price
    cum_returns = np.cumprod(1.0 + daily_returns_504)
    scale_factor = current_price / cum_returns[-1]
    price_series_504 = np.round(cum_returns * scale_factor, 2).tolist()
    price_series = price_series_504[-252:]
    daily_returns = daily_returns_504[-252:]
    
    # Realized vol and EWMA vol (lambda = 0.94)
    realized_vol = round(float(np.std(daily_returns) * math.sqrt(252)), 4)
    weights = np.array([0.06 * (0.94 ** i) for i in range(len(daily_returns))])[::-1]
    weights /= np.sum(weights)
    ewma_var = np.sum(weights * (daily_returns ** 2))
    ewma_vol = round(float(math.sqrt(ewma_var * 252)), 4)
    
    # Support and resistance (20-day swing pivots)
    last_20 = price_series[-20:]
    support_level = round(float(min(last_20) * 0.985), 2)
    resistance_level = round(float(max(last_20) * 1.015), 2)
    
    # Moving averages
    ma50 = round(float(np.mean(price_series[-50:])), 2)
    ma200 = round(float(np.mean(price_series[-200:])), 2)
    
    # RSI (14)
    deltas = np.diff(price_series[-15:])
    gains = np.maximum(deltas, 0)
    losses = np.abs(np.minimum(deltas, 0))
    avg_gain = np.mean(gains) if len(gains) else 0.0
    avg_loss = np.mean(losses) if len(losses) else 0.0
    rs = (avg_gain / (avg_loss + 1e-9))
    rsi = round(float(100.0 - (100.0 / (1.0 + rs))), 1)
    
    # MACD approximation
    ema12 = pd.Series(price_series).ewm(span=12).mean().iloc[-1]
    ema26 = pd.Series(price_series).ewm(span=26).mean().iloc[-1]
    macd = round(float(ema12 - ema26), 2)
    
    # Max Drawdown
    arr = np.array(price_series)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    max_dd = round(float(np.min(drawdowns)), 4)
    trough_idx = int(np.argmin(drawdowns))
    peak_idx = int(np.argmax(arr[:trough_idx + 1])) if trough_idx > 0 else 0
    days_to_recover = "not recovered" if arr[-1] < running_max[-1] * 0.99 else f"recovered in {len(arr) - trough_idx} days"
    
    # Real calendar dates for 1y peak & trough
    ref_date = datetime(2026, 10, 14)
    peak_days_ago = int((252 - peak_idx) * 365 / 252)
    trough_days_ago = int((252 - trough_idx) * 365 / 252)
    peak_date_str = (ref_date - timedelta(days=peak_days_ago)).strftime("%Y-%m-%d")
    trough_date_str = (ref_date - timedelta(days=trough_days_ago)).strftime("%Y-%m-%d")
    
    # Sharpe & Sortino (rf = 0.045)
    rf = 0.045
    ann_return = float((price_series[-1] / price_series[0]) - 1.0)
    sharpe = round((ann_return - rf) / max(0.01, realized_vol), 2)
    downside_ret = daily_returns[daily_returns < 0]
    downside_vol = float(np.std(downside_ret) * math.sqrt(252)) if len(downside_ret) else 0.01
    sortino = round((ann_return - rf) / max(0.01, downside_vol), 2)
    
    # VaR 95 (historical & parametric) and CVaR 97.5
    var_95_param = round(float(-1.645 * (realized_vol / math.sqrt(252))), 4)
    var_95_hist = round(float(np.percentile(daily_returns, 5)), 4)
    tail_returns = daily_returns[daily_returns <= np.percentile(daily_returns, 2.5)]
    cvar_975 = round(float(np.mean(tail_returns)), 4) if len(tail_returns) else var_95_hist
    
    # Day change
    prev_close = round(float(price_series[-2]), 2) if len(price_series) > 1 else current_price
    day_change = round(current_price - prev_close, 2)
    day_change_pct = round((day_change / prev_close) * 100.0, 2)
    
    # Scenarios (Bull, Base, Bear) summing to prob 1.00
    upside_bias = (seed % 15) / 100.0
    base_target = round(current_price * (1.08 + upside_bias), 2)
    bull_target = round(current_price * (1.25 + upside_bias * 1.5), 2)
    bear_target = round(current_price * (0.85 - upside_bias * 0.5), 2)
    
    p_bear = 0.20
    p_base = 0.55
    p_bull = 0.25
    expected_return = round(
        (p_bear * (bear_target / current_price - 1.0) +
         p_base * (base_target / current_price - 1.0) +
         p_bull * (bull_target / current_price - 1.0)) * 100.0,
        2
    )
    
    review_date = (datetime.now() + timedelta(days=63)).strftime("%Y-%m-%d")
    invalidation_price = round(min(support_level, current_price * 0.91), 2)
    
    as_of = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "ticker": clean,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "current_price": current_price,
        "previous_close": prev_close,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "price_series_252d": price_series,
        "price_series_504d": price_series_504,
        "daily_returns": daily_returns.tolist(),
        "annualized_volatility": realized_vol,
        "ewma_volatility": ewma_vol,
        "beta": beta,
        "r_squared": r_squared,
        "sector_beta": round(beta * 0.92, 2),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_dd,
        "max_drawdown_peak_date": peak_date_str,
        "max_drawdown_trough_date": trough_date_str,
        "days_to_recover": days_to_recover,
        "var_95_1d": var_95_hist,
        "var_95_parametric": var_95_param,
        "var_99_1d": round(float(np.percentile(daily_returns, 1)), 4),
        "cvar_975_1d": cvar_975,
        "pe_ratio": pe,
        "forward_pe": fwd_pe,
        "return_on_equity": roe,
        "profit_margins": pm,
        "debt_to_equity": round(45.0 + (seed % 80), 1),
        "revenue_growth": round(0.06 + ((seed % 18) / 100.0), 3),
        "free_cashflow": fcf,
        "adv_20d_shares": adv_shares,
        "adv_20d_dollars": round(adv_shares * current_price, 2),
        "bid_ask_spread_bps": round(1.5 + (seed % 45) / 10.0, 1),
        "support_level": support_level,
        "resistance_level": resistance_level,
        "ma50": ma50,
        "ma200": ma200,
        "rsi": rsi,
        "macd": macd,
        "horizon_days": 63,
        "target_price": base_target,
        "expected_return": expected_return,
        "invalidation_price": invalidation_price,
        "review_date": review_date,
        "recommendation": rec,
        "conviction": conviction,
        "scenarios": {
            "bear": {"target": bear_target, "prob": p_bear, "return_pct": round((bear_target / current_price - 1.0) * 100, 2)},
            "base": {"target": base_target, "prob": p_base, "return_pct": round((base_target / current_price - 1.0) * 100, 2)},
            "bull": {"target": bull_target, "prob": p_bull, "return_pct": round((bull_target / current_price - 1.0) * 100, 2)}
        },
        "_provenance": {
            "source": "mock_engine",
            "as_of": as_of,
            "window": "252d",
            "method": "single-factor model; GARCH(1,1) Student-t (nu=6) market and idiosyncratic shocks; 2 injected market stress windows; per-ticker deterministic seed"
        }
    }

def get_multi_asset_returns(tickers: list[str]) -> pd.DataFrame:
    """
    Returns aligned 252-day return series for multiple tickers, maintaining realistic correlations.
    """
    clean_tickers = [t.strip().upper() for t in tickers if t.strip()]
    data = {}
    for t in clean_tickers:
        prof = get_deterministic_mock_profile(t)
        data[t] = prof["daily_returns"]
    return pd.DataFrame(data)


DEFAULT_DIAGNOSTIC_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "JPM", "XOM", "GOOGL", "AMZN", "SPY"]


def compute_mock_diagnostics(tickers: list = None) -> dict:
    """
    RSK-001 acceptance diagnostics over the full 504-day mock history:
    per-ticker excess kurtosis and lag-1 autocorrelation of squared returns, plus the
    average pairwise correlation inside the injected stress windows vs calm days.
    """
    tickers = [t.strip().upper() for t in (tickers or DEFAULT_DIAGNOSTIC_TICKERS) if t and t.strip()]
    mask = stress_mask(N_HISTORY_DAYS)
    rows = []
    series = {}
    for t in tickers:
        prices = np.array(get_deterministic_mock_profile(t)["price_series_504d"], dtype=float)
        r = prices[1:] / prices[:-1] - 1.0  # 503 returns; return i belongs to day i+1
        series[t] = r
        x = r - r.mean()
        ex_kurt = float((x ** 4).mean() / (x ** 2).mean() ** 2 - 3.0)
        sq = r ** 2 - (r ** 2).mean()
        acf1 = float((sq[1:] * sq[:-1]).sum() / (sq * sq).sum())
        rows.append({
            "ticker": t,
            "excess_kurtosis": round(ex_kurt, 3),
            "acf1_squared_returns": round(acf1, 3),
            "worst_day_return": round(float(r.min()), 4),
            "kurtosis_pass": ex_kurt > 1.0,
            "acf_pass": acf1 > 0.1,
        })
    corr = None
    names = [t for t in tickers if t != "SPY"]
    if len(names) >= 2:
        m = mask[1:]
        mat = np.array([series[t] for t in names])
        iu = np.triu_indices(len(names), 1)
        calm = float(np.corrcoef(mat[:, ~m])[iu].mean())
        stressed = float(np.corrcoef(mat[:, m])[iu].mean())
        corr = {
            "tickers": names,
            "calm_avg_pairwise_corr": round(calm, 3),
            "stress_avg_pairwise_corr": round(stressed, 3),
            "ratio": round(stressed / calm, 2) if calm else None,
            "pass": calm > 0 and stressed > 1.3 * calm,
            "n_stress_days": int(m.sum()),
            "n_calm_days": int((~m).sum()),
        }
    return {
        "tickers": rows,
        "summary": {
            "kurtosis_pass_count": sum(r["kurtosis_pass"] for r in rows),
            "acf_pass_count": sum(r["acf_pass"] for r in rows),
            "n": len(rows),
            "median_acf1_squared": round(float(np.median([r["acf1_squared_returns"] for r in rows])), 3) if rows else None,
        },
        "stress_correlation": corr,
        "stress_windows": get_stress_windows(N_HISTORY_DAYS),
        "model": {
            "innovations": f"Student-t, nu={T_DOF}, unit variance, clipped at +/-{T_CLIP_SIGMA} sigma",
            "garch": {"alpha": GARCH_ALPHA, "beta": GARCH_BETA, "persistence": round(GARCH_ALPHA + GARCH_BETA, 2)},
            "market_unconditional_vol": MARKET_ANNUAL_VOL,
            "stress_vol_multiplier": STRESS_VOL_MULTIPLIER,
        },
        "_provenance": {
            "source": "mock_engine",
            "window": f"{N_HISTORY_DAYS}d",
            "as_of": HISTORY_END_DATE.strftime("%Y-%m-%d"),
            "method": "sample moments of simple daily returns from price_series_504d",
        },
    }
