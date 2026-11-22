"""
FastAPI Router for Quantitative Research Analyst (QRA) Endpoints (QRA-001 .. QRA-013)
"""

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from agents.qra_engine import (
    GICS_11_SECTORS,
    SIGNAL_CATALOG,
    compare_research_runs,
    compute_ic_tear_sheet,
    get_research_panel,
    get_research_panel_csv,
    get_signal_details,
    get_universe_as_of,
    list_research_runs,
    run_backtest,
    save_research_run,
    scan_signal_leakage,
    update_research_run_meta,
)
from agents.qra_advanced import (
    compute_agent_evaluation_lab,
    compute_factor_attribution,
    compute_overfitting_controls,
    compute_signal_blend,
    deploy_strategy_to_screener,
    run_quantitative_screener,
)

qra_router = APIRouter(tags=["Quantitative Research (QRA)"])


class BacktestRequest(BaseModel):
    signal_name: str = "planted_alpha_strong"
    rebalance_freq: str = "monthly"
    weighting: str = "equal_top_n"
    mode: str = "long_short"
    top_n: int = 20
    max_weight: float = 0.08
    sector_cap: float = 0.30
    lag: int = 1
    fixed_cost_bps: float = 5.0
    impact_coeff: float = 0.10
    aum: float = 10_000_000.0
    sector_neutral: bool = False
    beta_neutral: bool = False
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    save_run: bool = False
    question_key: str = "general_alpha"
    tags: Optional[List[str]] = None
    notes: str = ""


class RunMetaUpdateRequest(BaseModel):
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class BlendRequest(BaseModel):
    weights: Optional[Dict[str, float]] = None
    method: str = "custom"
    horizon: int = 21
    sector_neutral: bool = False


class DeployScreenerRequest(BaseModel):
    strategy_name: str = "Verified Alpha Strategy"
    signal_name: Optional[str] = "planted_alpha_strong"
    weights: Optional[Dict[str, float]] = None
    top_n: int = 15
    force_override: bool = False


@qra_router.get("/research/universe")
async def api_research_universe(date: Optional[str] = Query(None, description="Point-in-time YYYY-MM-DD date")):
    try:
        return await asyncio.to_thread(get_universe_as_of, date)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.get("/research/panel")
async def api_research_panel(
    universe: str = "mock100",
    fields: Optional[str] = Query("close,ret_1d,mcap,sector,pe,roe,fcf_yield"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    as_of: Optional[str] = None,
    tickers: Optional[str] = None,
    limit: int = Query(2000, ge=1, le=25000),
):
    if universe.strip().lower() != "mock100":
        raise HTTPException(status_code=400, detail="Only universe='mock100' is supported")
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
    return await asyncio.to_thread(
        get_research_panel,
        field_list,
        start,
        end,
        as_of,
        ticker_list,
        limit,
    )


@qra_router.get("/research/panel.csv")
async def api_research_panel_csv(
    fields: Optional[str] = Query("close,ret_1d,mcap,sector,pe,roe,fcf_yield"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    as_of: Optional[str] = None,
    tickers: Optional[str] = None,
    limit: int = Query(5000, ge=1, le=50000),
):
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
    csv_body = await asyncio.to_thread(
        get_research_panel_csv,
        field_list,
        start,
        end,
        as_of,
        ticker_list,
        limit,
    )
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="research_panel_pit.csv"'},
    )


@qra_router.get("/research/signals")
async def api_list_signals():
    return {
        "signals": list(SIGNAL_CATALOG.values()),
        "count": len(SIGNAL_CATALOG),
        "sectors": GICS_11_SECTORS,
    }


@qra_router.get("/research/signals/{signal_name}")
async def api_get_signal(
    signal_name: str,
    as_of: Optional[str] = None,
    winsorize: bool = True,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    zscore: bool = True,
):
    try:
        return await asyncio.to_thread(
            get_signal_details,
            signal_name,
            as_of,
            winsorize,
            sector_neutral,
            beta_neutral,
            zscore,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@qra_router.get("/research/leakage-scan")
async def api_leakage_scan(
    signal: str = "planted_alpha_strong",
    lag: int = 1,
    simulate_bad_report_date: bool = False,
):
    try:
        return await asyncio.to_thread(
            scan_signal_leakage,
            signal,
            None,
            lag,
            simulate_bad_report_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@qra_router.get("/research/tear-sheet")
async def api_ic_tear_sheet(
    signal: str = "planted_alpha_strong",
    horizon: int = 21,
    sector_neutral: bool = False,
    beta_neutral: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    try:
        return await asyncio.to_thread(
            compute_ic_tear_sheet,
            signal,
            horizon,
            sector_neutral,
            beta_neutral,
            start,
            end,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@qra_router.get("/research/backtest")
async def api_get_backtest(
    signal: str = "planted_alpha_strong",
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
    start: Optional[str] = None,
    end: Optional[str] = None,
    save_run: bool = False,
    question_key: str = "general_alpha",
):
    try:
        bt = await asyncio.to_thread(
            run_backtest,
            signal,
            rebalance_freq,
            weighting,
            mode,
            top_n,
            max_weight,
            sector_cap,
            lag,
            fixed_cost_bps,
            impact_coeff,
            aum,
            sector_neutral,
            beta_neutral,
            start,
            end,
        )
        if save_run:
            saved = await asyncio.to_thread(
                save_research_run,
                signal,
                "backtest",
                question_key,
                bt["config"],
                bt["config_hash"],
                {
                    "net": bt["net_metrics"],
                    "gross": bt["gross_metrics"],
                    "capm": bt["capm_vs_spy"],
                    "costs": bt["costs_and_turnover"],
                    "leakage_badge": bt["leakage_scan"]["badge"],
                },
                bt["equity_chart"],
                [signal, rebalance_freq, mode],
                f"Saved via GET /research/backtest ({signal})",
            )
            bt["saved_run"] = saved
        return bt
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.post("/research/backtest")
async def api_post_backtest(body: BacktestRequest):
    try:
        bt = await asyncio.to_thread(
            run_backtest,
            body.signal_name,
            body.rebalance_freq,
            body.weighting,
            body.mode,
            body.top_n,
            body.max_weight,
            body.sector_cap,
            body.lag,
            body.fixed_cost_bps,
            body.impact_coeff,
            body.aum,
            body.sector_neutral,
            body.beta_neutral,
            body.start_date,
            body.end_date,
        )
        if body.save_run:
            saved = await asyncio.to_thread(
                save_research_run,
                body.signal_name,
                "backtest",
                body.question_key,
                bt["config"],
                bt["config_hash"],
                {
                    "net": bt["net_metrics"],
                    "gross": bt["gross_metrics"],
                    "capm": bt["capm_vs_spy"],
                    "costs": bt["costs_and_turnover"],
                    "leakage_badge": bt["leakage_scan"]["badge"],
                },
                bt["equity_chart"],
                body.tags or [body.signal_name, body.rebalance_freq],
                body.notes or "",
            )
            bt["saved_run"] = saved
        return bt
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.get("/research/runs")
async def api_list_runs(question_key: Optional[str] = None, tag: Optional[str] = None):
    return await asyncio.to_thread(list_research_runs, question_key, tag)


@qra_router.get("/research/runs/compare")
async def api_compare_runs(ids: str = Query(..., description="Comma-separated run IDs (2-4)")):
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
        return await asyncio.to_thread(compare_research_runs, id_list)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.patch("/research/runs/{run_id}")
async def api_patch_run(run_id: int, body: RunMetaUpdateRequest):
    try:
        return await asyncio.to_thread(update_research_run_meta, run_id, body.tags, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@qra_router.get("/research/factors")
async def api_factor_attribution(
    signal: str = "planted_alpha_strong",
    orthogonalize: Optional[str] = Query(None, description="Comma-separated factors to residualize against"),
):
    try:
        ortho_list = [x.strip() for x in orthogonalize.split(",") if x.strip()] if orthogonalize else None
        return await asyncio.to_thread(compute_factor_attribution, signal, ortho_list)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@qra_router.get("/research/agent-lab")
async def api_agent_eval_lab(universe: str = "mock100"):
    try:
        return await asyncio.to_thread(compute_agent_evaluation_lab, universe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.get("/research/overfitting")
async def api_overfitting_controls(
    signal: str = "planted_alpha_strong",
    horizon: int = 21,
    n_folds: int = 5,
    train_ratio: float = 0.70,
    n_trials: Optional[int] = None,
):
    try:
        return await asyncio.to_thread(
            compute_overfitting_controls,
            signal,
            horizon,
            n_folds,
            train_ratio,
            n_trials,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.get("/research/blend")
async def api_get_blend(
    method: str = "custom",
    horizon: int = 21,
    sector_neutral: bool = False,
    weights: Optional[str] = Query(None, description="e.g. momentum_12_1:0.3,value_composite:0.3,quality_composite:0.2,low_vol_63d:0.2"),
):
    w_dict = None
    if weights:
        w_dict = {}
        for part in weights.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                try:
                    w_dict[k.strip()] = float(v.strip())
                except ValueError:
                    pass
    res = await asyncio.to_thread(compute_signal_blend, w_dict, method, horizon, sector_neutral)
    out = {k: v for k, v in res.items() if k != "_blended_matrix"}
    return out


@qra_router.post("/research/blend")
async def api_post_blend(body: BlendRequest):
    res = await asyncio.to_thread(
        compute_signal_blend,
        body.weights,
        body.method,
        body.horizon,
        body.sector_neutral,
    )
    out = {k: v for k, v in res.items() if k != "_blended_matrix"}
    return out


@qra_router.post("/research/deploy-to-screener")
async def api_deploy_screener(body: DeployScreenerRequest):
    try:
        return await asyncio.to_thread(
            deploy_strategy_to_screener,
            body.strategy_name,
            body.signal_name,
            body.weights,
            body.top_n,
            body.force_override,
        )
    except PermissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@qra_router.get("/screen")
@qra_router.get("/research/screen")
async def api_screen(
    strategy: str = "planted_alpha_strong",
    min_z: float = -10.0,
    sector: Optional[str] = None,
    max_vol_pct: Optional[float] = None,
    min_conviction: Optional[int] = None,
    exclude_contradictions: bool = False,
    top_n: int = 25,
    filters: Optional[str] = None,
):
    # Support optional packed `filters` query string (e.g. GET /screen?filters=strategy:planted_alpha_strong,min_z:1.0)
    if filters:
        for item in filters.split(","):
            if ":" in item or "=" in item:
                sep = ":" if ":" in item else "="
                k, v = item.split(sep, 1)
                k = k.strip().lower()
                v = v.strip()
                if k == "strategy":
                    strategy = v
                elif k == "min_z":
                    try:
                        min_z = float(v)
                    except ValueError:
                        pass
                elif k == "sector":
                    sector = v
                elif k == "top_n":
                    try:
                        top_n = int(v)
                    except ValueError:
                        pass
                elif k == "exclude_contradictions":
                    exclude_contradictions = v.lower() in ("true", "1", "yes")

    return await asyncio.to_thread(
        run_quantitative_screener,
        strategy,
        min_z,
        sector,
        max_vol_pct,
        min_conviction,
        exclude_contradictions,
        top_n,
    )
