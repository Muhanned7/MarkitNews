"""
FastAPI Router for Quantitative Portfolio Management (QPM) Endpoints
Includes Portfolio CRUD, Holdings Accounting, Ledoit-Wolf Risk Attribution,
Position Sizing, CSV Import, and Analysis Snapshot Diffs.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
import json
import csv
import io
from datetime import datetime
from loguru import logger

from agents.db import query
from auth import get_service_or_user
from agents.portfolio_engine import (
    calculate_portfolio_holdings,
    calculate_portfolio_risk,
    calculate_position_sizing,
    compute_snapshot_diff
)
from agents.mock_market_data import get_deterministic_mock_profile, compute_mock_diagnostics

portfolio_router = APIRouter(tags=["Portfolio Management"])

# Pydantic Request Models
class CreatePortfolioRequest(BaseModel):
    name: str
    base_ccy: Optional[str] = "USD"
    benchmark: Optional[str] = "SPY"
    cash: Optional[float] = 100000.0
    target_vol: Optional[float] = 0.15

class AddPositionRequest(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    side: Optional[str] = "long"

class AddTransactionRequest(BaseModel):
    ticker: str
    qty: float
    price: float
    fees: Optional[float] = 0.0
    note: Optional[str] = ""
    thesis: Optional[str] = ""
    sizing_method: Optional[str] = ""
    invalidation_price: Optional[float] = None
    override_reason: Optional[str] = None  # RSK-003: required when the trade creates/worsens a hard limit breach

class ImportCsvRequest(BaseModel):
    csv_content: str

def _resolve_user_id(user: dict) -> int:
    sub = user.get("sub", "")
    try:
        return int(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Authenticated user required")


def _assert_portfolio_owner(portfolio_id: int, user: dict) -> dict:
    """Fetches a portfolio and verifies that it belongs to the authenticated user (prevents IDOR)."""
    user_id = _resolve_user_id(user)
    p_res = query("SELECT * FROM portfolios WHERE id = %s", [portfolio_id])
    if not p_res.rows:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    portfolio = p_res.rows[0]
    if int(portfolio["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: portfolio does not belong to current user")
    return portfolio

def _seed_default_portfolio(user_id: int) -> dict:
    """Creates a default portfolio with initial seed positions and transactions if none exists."""
    p_res = query(
        """INSERT INTO portfolios (user_id, name, base_ccy, benchmark, cash, target_vol)
           VALUES (%s, 'Tech & Quant Strategy', 'USD', 'SPY', 100000.00, 0.1500)
           RETURNING id, user_id, name, base_ccy, benchmark, cash, target_vol, created_at;""",
        [user_id]
    )
    if not p_res.rows:
        raise HTTPException(status_code=500, detail="Failed to initialize default portfolio")
    
    port = p_res.rows[0]
    p_id = port["id"]
    
    # Initial seed positions
    seed_positions = [
        ("AAPL", 80.0, 215.00, "long"),
        ("MSFT", 45.0, 410.00, "long"),
        ("NVDA", 100.0, 125.00, "long")
    ]
    
    for ticker, qty, avg_cost, side in seed_positions:
        query(
            """INSERT INTO positions (portfolio_id, ticker, quantity, avg_cost, side)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (portfolio_id, ticker) DO NOTHING;""",
            [p_id, ticker, qty, avg_cost, side]
        )
        query(
            """INSERT INTO transactions (portfolio_id, ticker, qty, price, fees, note, thesis, sizing_method)
               VALUES (%s, %s, %s, %s, 0.0, 'Initial portfolio position', 'Core quantitative holding', 'volatility target');""",
            [p_id, ticker, qty, avg_cost]
        )
        
    return port

# =========================================================================
# 1. PORTFOLIOS CRUD
# =========================================================================

@portfolio_router.get("/portfolios")
async def list_portfolios(user: dict = Depends(get_service_or_user)):
    user_id = _resolve_user_id(user)
    res = query(
        """SELECT id, user_id, name, base_ccy, benchmark, cash, target_vol, created_at, updated_at
           FROM portfolios WHERE user_id = %s ORDER BY id ASC;""",
        [user_id]
    )
    
    # Auto-seed default portfolio if user has none
    if not res.rows:
        default_port = _seed_default_portfolio(user_id)
        res = query(
            """SELECT id, user_id, name, base_ccy, benchmark, cash, target_vol, created_at, updated_at
               FROM portfolios WHERE user_id = %s ORDER BY id ASC;""",
            [user_id]
        )
        
    portfolios = []
    for row in res.rows:
        p_id = row["id"]
        pos_res = query("SELECT ticker, quantity, avg_cost, side FROM positions WHERE portfolio_id = %s", [p_id])
        holdings = calculate_portfolio_holdings(pos_res.rows, float(row["cash"]))
        
        portfolios.append({
            "id": p_id,
            "name": row["name"],
            "base_ccy": row["base_ccy"],
            "benchmark": row["benchmark"],
            "cash": float(row["cash"]),
            "target_vol": float(row["target_vol"]),
            "nav": holdings["nav"],
            "positions_count": holdings["positions_count"],
            "total_unrealized_pnl": holdings["total_unrealized_pnl"],
            "total_unrealized_pnl_pct": holdings["total_unrealized_pnl_pct"],
            "created_at": str(row["created_at"])
        })
        
    return portfolios

@portfolio_router.post("/portfolios")
async def create_portfolio(req: CreatePortfolioRequest, user: dict = Depends(get_service_or_user)):
    user_id = _resolve_user_id(user)
    res = query(
        """INSERT INTO portfolios (user_id, name, base_ccy, benchmark, cash, target_vol)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id, user_id, name, base_ccy, benchmark, cash, target_vol, created_at;""",
        [user_id, req.name, req.base_ccy, req.benchmark, req.cash, req.target_vol]
    )
    if not res.rows:
        raise HTTPException(status_code=500, detail="Failed to create portfolio")
    return res.rows[0]

@portfolio_router.get("/portfolios/{portfolio_id}")
async def get_portfolio(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    portfolio = _assert_portfolio_owner(portfolio_id, user)
    
    pos_res = query("SELECT * FROM positions WHERE portfolio_id = %s ORDER BY id ASC", [portfolio_id])
    holdings = calculate_portfolio_holdings(pos_res.rows, float(portfolio["cash"]))
    
    tx_all_res = query(
        """SELECT ticker, qty, price, realized_pnl FROM transactions WHERE portfolio_id = %s""",
        [portfolio_id]
    )
    total_realized_pnl = sum(float(t.get("realized_pnl") or 0.0) for t in tx_all_res.rows)
    realized_by_ticker = {}
    for t in tx_all_res.rows:
        sym = t["ticker"]
        realized_by_ticker[sym] = realized_by_ticker.get(sym, 0.0) + float(t.get("realized_pnl") or 0.0)
        
    for p in holdings["positions"]:
        p["realized_pnl"] = round(realized_by_ticker.get(p["ticker"], 0.0), 2)
        
    holdings["total_realized_pnl"] = round(total_realized_pnl, 2)
    holdings["total_pnl"] = round(holdings["total_unrealized_pnl"] + total_realized_pnl, 2)
    
    tx_res = query(
        """SELECT * FROM transactions WHERE portfolio_id = %s ORDER BY ts DESC LIMIT 25""",
        [portfolio_id]
    )
    
    return {
        "portfolio": {
            "id": portfolio["id"],
            "name": portfolio["name"],
            "base_ccy": portfolio["base_ccy"],
            "benchmark": portfolio["benchmark"],
            "cash": float(portfolio["cash"]),
            "target_vol": float(portfolio["target_vol"]),
            "created_at": str(portfolio["created_at"])
        },
        "holdings": holdings,
        "recent_transactions": [
            {
                "id": t["id"],
                "ticker": t["ticker"],
                "ts": str(t["ts"]),
                "qty": float(t["qty"]),
                "price": float(t["price"]),
                "fees": float(t["fees"]),
                "note": t["note"],
                "thesis": t["thesis"],
                "sizing_method": t["sizing_method"],
                "invalidation_price": float(t["invalidation_price"]) if t["invalidation_price"] else None
            } for t in tx_res.rows
        ]
    }

# =========================================================================
# 2. POSITIONS & TRANSACTIONS
# =========================================================================

@portfolio_router.post("/portfolios/{portfolio_id}/positions")
async def add_or_update_position(portfolio_id: int, req: AddPositionRequest, user: dict = Depends(get_service_or_user)):
    _assert_portfolio_owner(portfolio_id, user)
    clean_ticker = req.ticker.strip().upper()
    if req.quantity <= 0 or req.avg_cost <= 0:
        raise HTTPException(status_code=400, detail="Quantity and avg_cost must be positive numbers")
    
    # Upsert position
    query(
        """INSERT INTO positions (portfolio_id, ticker, quantity, avg_cost, side)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (portfolio_id, ticker)
           DO UPDATE SET quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost, side = EXCLUDED.side;""",
        [portfolio_id, clean_ticker, req.quantity, req.avg_cost, req.side or "long"]
    )
    
    # Log transaction
    query(
        """INSERT INTO transactions (portfolio_id, ticker, qty, price, fees, note, thesis)
           VALUES (%s, %s, %s, %s, 0.0, 'Position entry/adjustment', 'Portfolio management update');""",
        [portfolio_id, clean_ticker, req.quantity, req.avg_cost]
    )
    
    return await get_portfolio(portfolio_id, user=user)

@portfolio_router.delete("/portfolios/{portfolio_id}/positions/{ticker}")
async def delete_position(portfolio_id: int, ticker: str, user: dict = Depends(get_service_or_user)):
    _assert_portfolio_owner(portfolio_id, user)
    clean_ticker = ticker.strip().upper()
    
    # Find existing position to record exit price
    pos_res = query("SELECT * FROM positions WHERE portfolio_id = %s AND ticker = %s", [portfolio_id, clean_ticker])
    if pos_res.rows:
        pos = pos_res.rows[0]
        prof = get_deterministic_mock_profile(clean_ticker)
        exit_price = prof["current_price"]
        # Credit cash
        proceeds = float(pos["quantity"]) * exit_price
        query("UPDATE portfolios SET cash = cash + %s WHERE id = %s", [proceeds, portfolio_id])
        # Record sell transaction
        query(
            """INSERT INTO transactions (portfolio_id, ticker, qty, price, note, thesis)
               VALUES (%s, %s, %s, %s, 'Position closed', 'Full liquidation');""",
            [portfolio_id, clean_ticker, -float(pos["quantity"]), exit_price]
        )
    
    query("DELETE FROM positions WHERE portfolio_id = %s AND ticker = %s", [portfolio_id, clean_ticker])
    return {"success": True, "ticker": clean_ticker}

@portfolio_router.post("/portfolios/{portfolio_id}/transactions")
async def add_transaction(portfolio_id: int, req: AddTransactionRequest, user: dict = Depends(get_service_or_user)):
    _assert_portfolio_owner(portfolio_id, user)
    clean_ticker = req.ticker.strip().upper()
        
    pos_res = query("SELECT * FROM positions WHERE portfolio_id = %s AND ticker = %s", [portfolio_id, clean_ticker])
    
    realized_trade_pnl = 0.0
    if req.qty < 0:
        if not pos_res.rows:
            raise HTTPException(status_code=400, detail=f"Cannot sell {abs(req.qty)} shares of {clean_ticker}: no open position.")
        curr_qty = float(pos_res.rows[0]["quantity"])
        if abs(req.qty) > curr_qty:
            raise HTTPException(status_code=400, detail=f"Cannot sell {abs(req.qty)} shares of {clean_ticker}: you only hold {curr_qty} shares.")
        curr_cost = float(pos_res.rows[0]["avg_cost"])
        realized_trade_pnl = round(abs(req.qty) * (req.price - curr_cost), 4)

    # RSK-003 pre-trade limit check: a trade that creates or worsens a hard breach
    # needs an override reason; the override is logged in limit_overrides.
    from agents.risk_router import pre_trade_check, record_override, evaluate_portfolio
    check = pre_trade_check(portfolio_id, clean_ticker, req.qty, req.price, req.fees or 0.0)
    override_reason = (req.override_reason or "").strip()
    if check["requires_override"] and len(override_reason) < 10:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This trade would breach hard risk limits: "
                           + "; ".join(b["message"] for b in check["blocking_breaches"])
                           + ". Provide an override reason (min 10 characters) to proceed.",
                "code": "HARD_LIMIT_BREACH",
                "blocking_breaches": check["blocking_breaches"],
            },
        )
    
    # Record transaction with realized_pnl
    tx_ins = query(
        """INSERT INTO transactions (
            portfolio_id, ticker, qty, price, fees, note, thesis, sizing_method, invalidation_price, realized_pnl
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;""",
        [
            portfolio_id, clean_ticker, req.qty, req.price, req.fees or 0.0,
            req.note, req.thesis, req.sizing_method, req.invalidation_price, realized_trade_pnl
        ]
    )
    
    # Adjust position
    trade_cost = req.qty * req.price + (req.fees or 0.0)
    
    if pos_res.rows:
        pos = pos_res.rows[0]
        curr_qty = float(pos["quantity"])
        curr_cost = float(pos["avg_cost"])
        new_qty = curr_qty + req.qty
        
        if new_qty <= 0:
            query("DELETE FROM positions WHERE portfolio_id = %s AND ticker = %s", [portfolio_id, clean_ticker])
        else:
            # Weighted average cost for additions
            if req.qty > 0:
                new_avg_cost = ((curr_qty * curr_cost) + (req.qty * req.price)) / new_qty
            else:
                new_avg_cost = curr_cost
            query(
                "UPDATE positions SET quantity = %s, avg_cost = %s WHERE portfolio_id = %s AND ticker = %s",
                [new_qty, new_avg_cost, portfolio_id, clean_ticker]
            )
    else:
        if req.qty > 0:
            query(
                "INSERT INTO positions (portfolio_id, ticker, quantity, avg_cost, side) VALUES (%s, %s, %s, %s, 'long')",
                [portfolio_id, clean_ticker, req.qty, req.price]
            )
            
    # Adjust cash balance
    query("UPDATE portfolios SET cash = cash - %s WHERE id = %s", [trade_cost, portfolio_id])

    if check["requires_override"]:
        record_override(
            portfolio_id, tx_ins.rows[0]["id"] if tx_ins.rows else None, clean_ticker, req.qty, req.price,
            check["blocking_breaches"], override_reason, str(user.get("email") or user.get("sub") or "unknown"),
        )
    evaluate_portfolio(portfolio_id, sync=True)  # open/refresh/resolve breach records for the new book
    
    return await get_portfolio(portfolio_id, user=user)

@portfolio_router.post("/portfolios/{portfolio_id}/import")
async def import_csv_positions(portfolio_id: int, req: ImportCsvRequest, user: dict = Depends(get_service_or_user)):
    _assert_portfolio_owner(portfolio_id, user)
    """
    Imports positions from CSV format (ticker,qty,avg_cost).
    Supports headers, comma/semicolon/tab delimiters.
    Validates symbols against tickers database.
    """
    raw_content = req.csv_content.strip()
    if not raw_content:
        raise HTTPException(status_code=400, detail="Empty CSV content")
        
    lines = raw_content.splitlines()
    imported_count = 0
    errors = []
    
    for line_idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue
            
        # Detect delimiter
        delimiter = ","
        if "\t" in line_clean:
            delimiter = "\t"
        elif ";" in line_clean:
            delimiter = ";"
            
        parts = [p.strip().strip('"').strip("'") for p in line_clean.split(delimiter)]
        if len(parts) < 3:
            continue
            
        # Check header
        if parts[0].lower() in ("ticker", "symbol") and parts[1].lower() in ("qty", "quantity", "shares"):
            continue
            
        try:
            ticker = parts[0].strip().upper()
            qty = float(parts[1])
            avg_cost = float(parts[2])
            side = parts[3].lower() if len(parts) > 3 else "long"
            
            if qty <= 0 or avg_cost <= 0:
                continue

            # Validate ticker exists in database
            t_check = query("SELECT symbol FROM tickers WHERE symbol = %s", [ticker])
            if not t_check.rows:
                errors.append(f"Line {line_idx+1}: Unknown ticker '{ticker}'. Ticker not found in database.")
                continue
                
            query(
                """INSERT INTO positions (portfolio_id, ticker, quantity, avg_cost, side)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (portfolio_id, ticker)
                   DO UPDATE SET quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost, side = EXCLUDED.side;""",
                [portfolio_id, ticker, qty, avg_cost, side]
            )
            query(
                """INSERT INTO transactions (portfolio_id, ticker, qty, price, fees, note, thesis)
                   VALUES (%s, %s, %s, %s, 0.0, 'Batch CSV import', 'Imported position');""",
                [portfolio_id, ticker, qty, avg_cost]
            )
            imported_count += 1
        except Exception as e:
            errors.append(f"Line {line_idx+1}: {e}")
            
    return {
        "success": True,
        "imported_count": imported_count,
        "errors": errors
    }

# =========================================================================
# 3. PORTFOLIO RISK & FACTOR ANALYTICS
# =========================================================================

@portfolio_router.get("/portfolios/{portfolio_id}/risk")
async def get_portfolio_risk(portfolio_id: int, user: dict = Depends(get_service_or_user)):
    portfolio = _assert_portfolio_owner(portfolio_id, user)
    
    pos_res = query("SELECT * FROM positions WHERE portfolio_id = %s", [portfolio_id])
    holdings = calculate_portfolio_holdings(pos_res.rows, float(portfolio["cash"]))
    
    risk_data = calculate_portfolio_risk(holdings["positions"], float(portfolio["cash"]), portfolio["benchmark"])
    
    return {
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolio["name"],
        "benchmark": portfolio["benchmark"],
        "target_vol": float(portfolio["target_vol"]),
        "nav": holdings["nav"],
        "cash": holdings["cash"],
        "risk": risk_data,
        "_provenance": {
            "source": "LedoitWolf_Shrunk_Covariance",
            "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": "252d",
            "method": "Euler risk contribution decomposition, sigma_p = sqrt(w^T * Sigma * w) * sqrt(252)"
        }
    }

# =========================================================================
# 4. POSITION SIZING ENGINE
# =========================================================================

@portfolio_router.get("/portfolios/{portfolio_id}/sizing/{ticker}")
async def get_position_sizing(
    portfolio_id: int,
    ticker: str,
    method: Optional[str] = "vol_target",
    daily_risk_budget: Optional[float] = 0.0025,
    conviction: Optional[int] = None,
    expected_return: Optional[float] = None,
    current_price: Optional[float] = None,
    user: dict = Depends(get_service_or_user)
):
    clean_ticker = ticker.strip().upper()
    portfolio = _assert_portfolio_owner(portfolio_id, user)
    
    pos_res = query("SELECT * FROM positions WHERE portfolio_id = %s", [portfolio_id])
    holdings = calculate_portfolio_holdings(pos_res.rows, float(portfolio["cash"]))
    
    sizing = calculate_position_sizing(
        clean_ticker,
        holdings["nav"],
        holdings["positions"],
        method=method or "vol_target",
        daily_risk_budget=daily_risk_budget or 0.0025,
        target_vol=float(portfolio["target_vol"]),
        conviction_override=conviction,
        expected_return_override=expected_return,
        current_price_override=current_price
    )
    return sizing

# =========================================================================
# 5. ANALYSIS SNAPSHOTS & DIFF ENGINE
# =========================================================================

@portfolio_router.get("/snapshots/{ticker}")
async def get_snapshots(ticker: str, user: dict = Depends(get_service_or_user)):
    clean_ticker = ticker.strip().upper()
    res = query(
        """SELECT id, ticker, ts, price_at_ts, recommendation, conviction, target,
                  expected_return, horizon_days, invalidation_price, scenarios_json,
                  model, mock_mode
           FROM analysis_snapshots
           WHERE ticker = %s
           ORDER BY ts DESC
           LIMIT 30;""",
        [clean_ticker]
    )
    return [
        {
            "id": r["id"],
            "ticker": r["ticker"],
            "ts": str(r["ts"]),
            "price_at_ts": float(r["price_at_ts"]),
            "recommendation": r["recommendation"],
            "conviction": r["conviction"],
            "target": float(r["target"]) if r["target"] else None,
            "expected_return": float(r["expected_return"]) if r["expected_return"] else None,
            "horizon_days": r["horizon_days"],
            "invalidation_price": float(r["invalidation_price"]) if r["invalidation_price"] else None,
            "scenarios": r["scenarios_json"] if isinstance(r["scenarios_json"], dict) else json.loads(r["scenarios_json"] or "{}"),
            "model": r["model"],
            "mock_mode": r["mock_mode"]
        } for r in res.rows
    ]

@portfolio_router.get("/snapshots/{ticker}/diff")
async def get_snapshot_diff(ticker: str, user: dict = Depends(get_service_or_user)):
    clean_ticker = ticker.strip().upper()
    res = query(
        """SELECT id, ticker, ts, price_at_ts, recommendation, conviction, target,
                  expected_return, horizon_days, invalidation_price, scenarios_json
           FROM analysis_snapshots
           WHERE ticker = %s
           ORDER BY ts DESC
           LIMIT 2;""",
        [clean_ticker]
    )
    latest = res.rows[0] if len(res.rows) > 0 else None
    previous = res.rows[1] if len(res.rows) > 1 else None
    
    return compute_snapshot_diff(latest, previous)

@portfolio_router.get("/mock/prices/{ticker}", dependencies=[Depends(get_service_or_user)])
async def get_mock_prices(ticker: str, days: int = 504):
    """
    Returns deterministic 504-day price series and returns for a symbol.
    Guaranteed: the last bar equals the displayed current_price.
    """
    clean = ticker.strip().upper()
    prof = get_deterministic_mock_profile(clean)
    prices = prof.get("price_series_504d", prof["price_series_252d"])
    if days < len(prices):
        prices = prices[-days:]
        
    return {
        "ticker": clean,
        "company_name": prof["company_name"],
        "sector": prof["sector"],
        "current_price": prof["current_price"],
        "days": len(prices),
        "prices": prices,
        "last_bar": prices[-1],
        "beta": prof["beta"],
        "volatility": prof["annualized_volatility"],
        "r_squared": prof["r_squared"],
        "adv_shares": prof["adv_20d_shares"],
        "pe": prof["pe_ratio"],
        "fcf": prof["free_cashflow"]
    }


@portfolio_router.get("/mock/diagnostics", dependencies=[Depends(get_service_or_user)])
async def get_mock_diagnostics(tickers: Optional[str] = None):
    """
    RSK-001: fat-tail / volatility-clustering / stress-correlation diagnostics of the mock engine.
    `tickers` is a comma-separated list; defaults to the anchor universe.
    """
    lst = [t for t in tickers.split(",")] if tickers else None
    return compute_mock_diagnostics(lst)
