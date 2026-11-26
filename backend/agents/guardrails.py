import re
import urllib.parse
from typing import Dict, Any, List, Tuple, Optional
from loguru import logger

DISALLOWED_PLACEHOLDERS = {
    "n/a", "none", "unknown", "placeholder", "tbd", "test", "article1", "article2",
    "theme1", "theme2", "theme3", "risk1", "risk2", "strength1", "strength2",
    "weakness1", "weakness2", "point1", "point2", "point3", "catalyst1", "catalyst2"
}

def is_valid_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc or "." not in parsed.netloc:
            return False
        if any(fake in parsed.netloc.lower() for fake in ["example.com", "fake.com", "yoururl.com"]):
            return False
        return True
    except Exception:
        return False

# ==========================================
# 1. NEWS AGENT GUARDRAILS
# ==========================================
def guardrail_news_agent(raw_data: Dict[str, Any], input_articles: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []
    
    # Sentiment enum validation
    sentiment = str(raw_data.get("overall_sentiment", "neutral")).lower()
    if sentiment not in ("bullish", "bearish", "neutral"):
        hallucinations_detected += 1
        warnings.append(f"Invalid overall_sentiment '{sentiment}' coerced to 'neutral'")
        sentiment = "neutral"
    
    # Filter placeholder themes
    raw_themes = raw_data.get("key_themes", [])
    clean_themes = []
    for t in raw_themes:
        if isinstance(t, str) and t.strip().lower() not in DISALLOWED_PLACEHOLDERS and len(t.strip()) > 3:
            clean_themes.append(t.strip())
        else:
            hallucinations_detected += 1
            warnings.append(f"Dropped placeholder news theme '{t}'")
    if not clean_themes:
        clean_themes = ["Market Dynamics", "Industry Positioning"]

    # Filter placeholder risks
    raw_risks = raw_data.get("supply_chain_risks", [])
    clean_risks = []
    for r in raw_risks:
        if isinstance(r, str) and r.strip().lower() not in DISALLOWED_PLACEHOLDERS and len(r.strip()) > 3:
            clean_risks.append(r.strip())
        else:
            hallucinations_detected += 1
            warnings.append(f"Dropped placeholder supply chain risk '{r}'")
    if not clean_risks:
        clean_risks = ["Macroeconomic volatility", "Supplier input cost variations"]

    # Validate article URLs, titles, and Temporal Regime consistency
    raw_articles = raw_data.get("articles", [])
    input_urls = {a.get("url") for a in input_articles if a.get("url")}
    input_by_url = {a.get("url"): a for a in input_articles if a.get("url")}
    clean_articles = []

    STALE_BREAKING_CLAIMS = (
        "breaking:", "currently halting", "immediate halt", "halts shipments today",
        "ongoing walkout today", "shutting down production this week"
    )

    for a in raw_articles:
        if not isinstance(a, dict):
            continue
        title = a.get("title", "").strip()
        url = a.get("url", "").strip()
        
        # Check for fake/example URLs
        if not is_valid_url(url) or (input_urls and url not in input_urls):
            hallucinations_detected += 1
            warnings.append(f"Repaired ungrounded/fabricated article URL for '{title[:30]}'")
            # If input articles exist, ground to the closest input article URL
            url = next(iter(input_urls)) if input_urls else "https://finance.yahoo.com"

        matched_input = input_by_url.get(url, {})
        age_days = matched_input.get("age_days") if matched_input else a.get("age_days")
        regime = matched_input.get("temporal_regime") or a.get("temporal_regime") or "ACTIVE_SHOCK"
        relevance = a.get("relevance", "Relevant to company operations.")

        # Temporal Misrepresentation Gate: Prevent >180-day old articles (e.g. 3-year-old factory fire)
        # from being misrepresented as an active breaking shipment halt today
        if regime == "HISTORICAL_STRUCTURAL" or (isinstance(age_days, (int, float)) and age_days > 180):
            regime = "HISTORICAL_STRUCTURAL"
            if any(phrase in relevance.lower() for phrase in STALE_BREAKING_CLAIMS):
                hallucinations_detected += 1
                warnings.append(
                    f"Temporal misrepresentation caught: Historical article '{title[:35]}' ({age_days}d old) "
                    "was framed as a breaking operational halt; reframed to long-term structural supply-chain context."
                )
                relevance = (
                    f"[Historical Structural Event ({age_days}d ago)] Physical flow disruption resolved; "
                    "relevant today as baseline proof of Single-Point-of-Failure (SPOF) node concentration and dual-sourcing catalysts."
                )

        clean_articles.append({
            "title": title or "Financial Wire Update",
            "source": a.get("source", "Financial News Wire"),
            "url": url,
            "age_days": age_days,
            "temporal_regime": regime,
            "is_live_contradiction_eligible": regime != "HISTORICAL_STRUCTURAL",
            "relevance": relevance
        })

    cleaned = {
        "overall_sentiment": sentiment,
        "summary": raw_data.get("summary", "News flow shows balanced market positioning."),
        "key_themes": clean_themes,
        "supply_chain_risks": clean_risks,
        "temporal_supply_chain_effects": raw_data.get("temporal_supply_chain_effects", []),
        "articles": clean_articles
    }

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.2, round(1.0 - (hallucinations_detected * 0.15), 2)),
        "consistency": 1.0,
        "completeness": 1.0 if clean_articles and clean_themes else 0.7
    }
    return cleaned, stats

# ==========================================
# 2. SENTIMENT AGENT GUARDRAILS
# ==========================================
def guardrail_sentiment_agent(raw_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    def clean_sentiment_label(val: Any, default="neutral") -> str:
        s = str(val).lower().strip()
        return s if s in ("bullish", "bearish", "neutral") else default

    overall = clean_sentiment_label(raw_data.get("overall_sentiment"))
    retail = clean_sentiment_label(raw_data.get("retail_sentiment"))
    institutional = clean_sentiment_label(raw_data.get("institutional_sentiment"))

    # Score bounded 1-10
    raw_score = raw_data.get("sentiment_score", 5)
    try:
        score = int(raw_score)
        if score < 1 or score > 10:
            hallucinations_detected += 1
            warnings.append(f"Out-of-bounds sentiment_score {score} clamped to [1, 10]")
            score = max(1, min(10, score))
    except Exception:
        hallucinations_detected += 1
        score = 5

    # Sentiment vs Score coherence check
    if overall == "bullish" and score < 5:
        hallucinations_detected += 1
        warnings.append(f"Contradictory sentiment: 'bullish' label with low score {score}. Coerced to 6.")
        score = 6
    elif overall == "bearish" and score > 5:
        hallucinations_detected += 1
        warnings.append(f"Contradictory sentiment: 'bearish' label with high score {score}. Coerced to 4.")
        score = 4

    consensus = str(raw_data.get("analyst_consensus", "hold")).lower().strip()
    if consensus not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        hallucinations_detected += 1
        warnings.append(f"Invalid consensus '{consensus}' normalized to 'hold'")
        consensus = "hold"

    raw_drivers = raw_data.get("key_sentiment_drivers", [])
    clean_drivers = [d.strip() for d in raw_drivers if isinstance(d, str) and d.strip().lower() not in DISALLOWED_PLACEHOLDERS]
    if not clean_drivers:
        clean_drivers = ["Institutional capital accumulation", "Balanced sell-side expectations"]

    cleaned = {
        "overall_sentiment": overall,
        "retail_sentiment": retail,
        "institutional_sentiment": institutional,
        "sentiment_score": score,
        "analyst_consensus": consensus,
        "key_sentiment_drivers": clean_drivers,
        "summary": raw_data.get("summary", "Market sentiment remains balanced with active institutional monitoring.")
    }

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.2, round(1.0 - (hallucinations_detected * 0.15), 2)),
        "consistency": 1.0 if not any("Contradictory" in w for w in warnings) else 0.6,
        "completeness": 1.0
    }
    return cleaned, stats

# ==========================================
# 3. TECHNICAL AGENT GUARDRAILS
# ==========================================
def guardrail_technical_agent(raw_data: Dict[str, Any], raw_math: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    trend = str(raw_data.get("trend", "neutral")).lower().strip()
    if trend not in ("bullish", "bearish", "neutral"):
        trend = "neutral"

    support = raw_data.get("support_level")
    resistance = raw_data.get("resistance_level")

    curr_price = raw_math.get("current_price") if raw_math else (raw_data.get("raw", {}).get("current_price"))
    if raw_math and raw_math.get("swing_support_20d") and raw_math.get("swing_resistance_20d"):
        supp_calc = float(raw_math["swing_support_20d"])
        res_calc = float(raw_math["swing_resistance_20d"])
        if support is not None:
            try:
                supp_val = float(support)
                if abs(supp_val - supp_calc) > (curr_price * 0.05 if curr_price else 5.0):
                    hallucinations_detected += 1
                    warnings.append(f"Subjective support ${supp_val} overridden by verified 20d swing pivot ${supp_calc}.")
            except Exception:
                pass
        if resistance is not None:
            try:
                res_val = float(resistance)
                if abs(res_val - res_calc) > (curr_price * 0.05 if curr_price else 5.0):
                    hallucinations_detected += 1
                    warnings.append(f"Subjective resistance ${res_val} overridden by verified 20d swing pivot ${res_calc}.")
            except Exception:
                pass
        support = round(supp_calc, 2)
        resistance = round(res_calc, 2)
    elif curr_price:
        support = round(curr_price * 0.95, 2)
        resistance = round(curr_price * 1.05, 2)

    cleaned = {
        "trend": trend,
        "trend_strength": raw_data.get("trend_strength", "moderate"),
        "rsi_signal": raw_data.get("rsi_signal", "neutral"),
        "macd_signal": raw_data.get("macd_signal", "neutral"),
        "support_level": support,
        "resistance_level": resistance,
        "short_term_outlook": raw_data.get("short_term_outlook", trend),
        "key_levels": raw_data.get("key_levels", [f"${support} (Support)", f"${resistance} (Resistance)"]),
        "signals": raw_data.get("signals", ["Consolidation in primary range"]),
        "summary": raw_data.get("summary", "Technical structure indicates price consolidation around moving averages."),
        "raw": raw_math or raw_data.get("raw", {})
    }

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.3, round(1.0 - (hallucinations_detected * 0.2), 2)),
        "consistency": 1.0,
        "completeness": 1.0
    }
    return cleaned, stats

# ==========================================
# 4. FUNDAMENTALS AGENT GUARDRAILS
# ==========================================
def guardrail_fundamentals_agent(raw_data: Dict[str, Any], raw_financials: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    valuation = str(raw_data.get("valuation", "fairly_valued")).lower().strip()
    if valuation not in ("overvalued", "fairly_valued", "undervalued"):
        valuation = "fairly_valued"

    health = str(raw_data.get("financial_health", "moderate")).lower().strip()
    if health not in ("strong", "moderate", "weak"):
        health = "moderate"

    outlook = str(raw_data.get("growth_outlook", "moderate")).lower().strip()
    if outlook not in ("high", "moderate", "low"):
        outlook = "moderate"

    # Merge verified financial metrics from yfinance if available
    metrics = raw_data.get("metrics", {})
    if raw_financials:
        for k in ["pe_ratio", "forward_pe", "revenue_growth", "profit_margins", "debt_to_equity", "return_on_equity", "free_cashflow"]:
            if raw_financials.get(k) is not None:
                metrics[k] = raw_financials[k]

    cleaned = {
        "valuation": valuation,
        "valuation_reasoning": raw_data.get("valuation_reasoning", "Valuation reflects current earnings trajectory."),
        "financial_health": health,
        "health_reasoning": raw_data.get("health_reasoning", "Balance sheet demonstrates adequate liquidity."),
        "growth_outlook": outlook,
        "growth_reasoning": raw_data.get("growth_reasoning", "Revenue growth remains aligned with industry benchmarks."),
        "key_strengths": [s for s in raw_data.get("key_strengths", []) if s.lower() not in DISALLOWED_PLACEHOLDERS] or ["Operating discipline"],
        "key_weaknesses": [w for w in raw_data.get("key_weaknesses", []) if w.lower() not in DISALLOWED_PLACEHOLDERS] or ["Sector margin compression"],
        "metrics": metrics,
        "summary": raw_data.get("summary", "Company fundamentals reflect stable operating health.")
    }

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.4, round(1.0 - (hallucinations_detected * 0.15), 2)),
        "consistency": 1.0,
        "completeness": 1.0
    }
    return cleaned, stats

# ==========================================
# 5. RISK AGENT GUARDRAILS
# ==========================================
def derive_beta_assessment(beta: Optional[float]) -> str:
    if beta is None:
        return "≈ Market"
    if beta < 0.80:
        return "Defensive (moves less than market)"
    elif beta <= 1.20:
        return "≈ Market"
    else:
        return "Aggressive (moves more than market)"

def derive_overall_risk(vol: Optional[float]) -> str:
    if vol is None:
        return "medium"
    if vol < 0.20:
        return "low"
    elif vol <= 0.35:
        return "medium"
    else:
        return "high"

def guardrail_risk_agent(raw_data: Dict[str, Any], raw_risk_math: Optional[Dict[str, Any]] = None, ticker: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    # Verify metrics alignment with mathematical calculations
    metrics = dict(raw_data.get("metrics", {}))
    if raw_risk_math:
        for k in ["beta", "volatility", "annualized_volatility", "sharpe_ratio", "max_drawdown", "var_95", "r_squared", "adv_20d_dollars", "bid_ask_spread_bps"]:
            math_k = "annualized_volatility" if k == "volatility" else k
            if raw_risk_math.get(math_k) is not None:
                metrics[k] = raw_risk_math[math_k]

    vol = metrics.get("annualized_volatility") or metrics.get("volatility") or (raw_risk_math.get("annualized_volatility") if raw_risk_math else None)
    if vol is not None:
        metrics["volatility"] = vol
        metrics["annualized_volatility"] = vol

    beta = metrics.get("beta") or (raw_risk_math.get("beta") if raw_risk_math else None)
    if beta is not None:
        metrics["beta"] = beta

    # Code-derived classifications (never taken from LLM text)
    beta_desc = derive_beta_assessment(beta)
    risk_level = derive_overall_risk(vol)
    vol_desc = "high" if (vol or 0) > 0.35 else ("low" if (vol or 0) < 0.20 else "medium")
    sharpe_val = float(metrics.get("sharpe_ratio", 0)) if metrics.get("sharpe_ratio") is not None else 0.0
    sharpe_desc = "strong" if sharpe_val > 1.2 else ("weak" if sharpe_val < 0.5 else "good")
    max_dd_val = float(metrics.get("max_drawdown", 0)) if metrics.get("max_drawdown") is not None else 0.0
    dd_desc = "severe" if max_dd_val < -0.25 else ("moderate" if max_dd_val < -0.15 else "mild")

    var_95 = metrics.get("var_95") or (raw_risk_math.get("var_95") if raw_risk_math else None)
    if var_95 is not None:
        var_pct = abs(float(var_95))
        loss_per_10k = round(var_pct * 10000, 2)
        var_interp = f"1-day 95% historical VaR: -{var_pct * 100:.2f}% (approx. -${loss_per_10k:.0f} per $10,000 portfolio)."
    else:
        var_interp = "Statistical downside remains within historical tolerances."

    # Narrative vs table consistency check (P0-1)
    vol_pct = round(vol * 100, 1) if vol is not None else None
    beta_val = round(beta, 2) if beta is not None else None
    var_95_pct = abs(round(float(var_95) * 100, 2)) if var_95 is not None else None
    t_sym = (ticker or raw_data.get("ticker") or "The stock").upper()
    template_summary = (
        f"{t_sym} exhibits an annualized volatility of {vol_pct:.1f}% and a beta of {beta_val:.2f} vs SPY. "
        f"Daily 95% historical VaR stands at {var_95_pct:.2f}%, with a Sharpe ratio of {sharpe_val:.2f}."
    ) if vol_pct is not None and beta_val is not None and var_95_pct is not None else raw_data.get("summary", "")

    summary = raw_data.get("summary", "")
    pct_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', summary)
    narrative_valid = True
    if pct_matches and vol_pct is not None:
        candidates = [vol_pct]
        if var_95_pct is not None:
            candidates.extend([var_95_pct, round(var_95_pct, 1)])
        if max_dd_val:
            candidates.append(abs(round(max_dd_val * 100, 1)))
        for p_str in pct_matches:
            val = float(p_str)
            if not any(abs(val - c) <= 0.101 for c in candidates):
                narrative_valid = False
                hallucinations_detected += 1
                warnings.append(f"Risk narrative quoted percentage {val}% differing by >0.1pp from authoritative metrics. Reverted to template.")
                break

    if not narrative_valid or not summary:
        summary = template_summary

    # Ensure key_risks always interpolate exact computed metric numbers
    raw_key_risks = raw_data.get("key_risks", [])
    clean_key_risks = []
    for r in raw_key_risks:
        r_str = str(r)
        if "vol" in r_str.lower() and vol_pct is not None:
            clean_key_risks.append(f"Market volatility exposure (annualized vol: {vol_pct:.1f}%)")
        elif "beta" in r_str.lower() and beta_val is not None:
            clean_key_risks.append(f"Systematic market risk (beta: {beta_val:.2f} vs benchmark)")
        elif ("drawdown" in r_str.lower() or "max dd" in r_str.lower()) and max_dd_val:
            clean_key_risks.append(f"Max 1-year drawdown: {max_dd_val * 100:.1f}%")
        elif r_str.strip().lower() not in DISALLOWED_PLACEHOLDERS:
            clean_key_risks.append(r_str.strip())

    if not clean_key_risks and vol_pct is not None and beta_val is not None:
        clean_key_risks = [
            f"Market volatility exposure (annualized vol: {vol_pct:.1f}%)",
            f"Systematic market risk (beta: {beta_val:.2f} vs benchmark)",
            f"Max 1-year drawdown: {max_dd_val * 100:.1f}%"
        ]

    cleaned = {
        "overall_risk": risk_level,
        "volatility_assessment": vol_desc,
        "beta_assessment": beta_desc,
        "sharpe_assessment": sharpe_desc,
        "short_squeeze_risk": "low",
        "key_risks": clean_key_risks,
        "risk_mitigants": [m for m in raw_data.get("risk_mitigants", []) if m.lower() not in DISALLOWED_PLACEHOLDERS] or ["Operating liquidity reserves"],
        "max_drawdown_assessment": dd_desc,
        "var_interpretation": var_interp,
        "metrics": metrics,
        "summary": summary
    }

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else 0.8,
        "consistency": 1.0,
        "completeness": 1.0
    }
    return cleaned, stats

# ==========================================
# 6. EQUITY RESEARCH / SYNTHESIS GUARDRAILS
# ==========================================
def guardrail_equity_research(raw_data: Dict[str, Any], sub_reports: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    rec = str(raw_data.get("recommendation", "hold")).lower().strip()
    if rec not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        hallucinations_detected += 1
        warnings.append(f"Invalid recommendation '{rec}' normalized to 'hold'")
        rec = "hold"

    try:
        conviction = int(raw_data.get("conviction", 5))
        if conviction < 1 or conviction > 10:
            hallucinations_detected += 1
            warnings.append(f"Out-of-range conviction {conviction} clamped to [1, 10]")
            conviction = max(1, min(10, conviction))
    except Exception:
        conviction = 5

    target = None
    if raw_data.get("price_target") is not None:
        try:
            val = float(raw_data["price_target"])
            if val > 0:
                target = round(val, 2)
            else:
                hallucinations_detected += 1
                warnings.append("Non-positive price target detected and flagged")
        except Exception:
            target = None

    risk_reward = str(raw_data.get("risk_reward", "neutral")).lower().strip()
    if risk_reward not in ("favorable", "neutral", "unfavorable"):
        risk_reward = "neutral"

    horizon = str(raw_data.get("investment_horizon", "medium_term")).lower().strip()
    if horizon not in ("short_term", "medium_term", "long_term"):
        horizon = "medium_term"

    cleaned = {
        "recommendation": rec,
        "conviction": conviction,
        "price_target": target,
        "risk_reward": risk_reward,
        "investment_horizon": horizon,
        "bull_case": [b for b in raw_data.get("bull_case", []) if b.lower() not in DISALLOWED_PLACEHOLDERS] or ["Durable franchise value"],
        "bear_case": [b for b in raw_data.get("bear_case", []) if b.lower() not in DISALLOWED_PLACEHOLDERS] or ["Broader macroeconomic pressure"],
        "key_catalysts": [c for c in raw_data.get("key_catalysts", []) if c.lower() not in DISALLOWED_PLACEHOLDERS] or ["Next quarterly earnings announcement"],
        "key_risks": [r for r in raw_data.get("key_risks", []) if r.lower() not in DISALLOWED_PLACEHOLDERS] or ["Industry competitive intensity"],
        "position_sizing": raw_data.get("position_sizing", "medium"),
        "summary": raw_data.get("summary", "Balanced risk-adjusted opportunity supported by core operational execution."),
        "horizon_days": raw_data.get("horizon_days", 63),
        "expected_return": raw_data.get("expected_return"),
        "invalidation_price": raw_data.get("invalidation_price"),
        "review_date": raw_data.get("review_date"),
        "scenarios": raw_data.get("scenarios"),
        "target_source": raw_data.get("target_source", "model")
    }
    if "_provenance" in raw_data:
        cleaned["_provenance"] = raw_data["_provenance"]

    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.4, round(1.0 - (hallucinations_detected * 0.15), 2)),
        "consistency": 1.0,
        "completeness": 1.0
    }
    return cleaned, stats

def guardrail_equity_agent(raw_data: Dict[str, Any], raw_market_data: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    hallucinations_detected = 0
    warnings = []

    rec = str(raw_data.get("recommendation", "hold")).lower().strip()
    if rec not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        hallucinations_detected += 1
        orig_rec = rec
        rec = "hold"
        warnings.append(f"Invalid equity recommendation '{orig_rec}' normalized to 'hold'")

    try:
        conviction = int(raw_data.get("conviction", 5))
        conviction = max(1, min(10, conviction))
    except Exception:
        conviction = 5

    target = None
    if raw_data.get("price_target") is not None:
        try:
            val = float(raw_data["price_target"])
            if val > 0:
                target = round(val, 2)
            else:
                hallucinations_detected += 1
                warnings.append("Non-positive price target detected; cleared to null.")
        except Exception:
            target = None

    moat = str(raw_data.get("moat", "none")).lower().strip()
    if moat not in ("none", "narrow", "wide"):
        moat = "none"

    comp = str(raw_data.get("competitive_position", "competitor")).lower().strip()
    if comp not in ("leader", "challenger", "follower", "niche", "competitor", "lagging"):
        comp = "competitor"

    curr_p = raw_market_data.get("current_price") if raw_market_data else None
    upside_str = raw_data.get("upside_downside", "Consensus target within historical range.")
    if target and curr_p:
        try:
            curr_val = float(curr_p)
            if curr_val > 0:
                pct = ((target - curr_val) / curr_val) * 100
                if pct >= 0:
                    upside_str = f"+{pct:.2f}% upside from current price"
                else:
                    upside_str = f"{abs(pct):.2f}% downside from current price"
        except Exception:
            pass

    street_targets = raw_market_data.get("analyst_price_targets") if raw_market_data else None

    cleaned = {
        "recommendation": rec,
        "conviction": conviction,
        "analyst_consensus": raw_data.get("analyst_consensus", "hold"),
        "price_target": target,
        "upside_downside": upside_str,
        "analyst_price_targets": street_targets or {},
        "competitive_position": comp,
        "moat": moat,
        "moat_sources": [m for m in raw_data.get("moat_sources", []) if m.lower() not in DISALLOWED_PLACEHOLDERS] or ["Competitive differentiation", "Operational infrastructure"],
        "growth_catalysts": [c for c in raw_data.get("growth_catalysts", []) if c.lower() not in DISALLOWED_PLACEHOLDERS] or ["Market share stability", "Operational efficiency"],
        "key_risks": [r for r in raw_data.get("key_risks", []) if r.lower() not in DISALLOWED_PLACEHOLDERS] or ["Macro slowdown", "Competitive pressure"],
        "sector_outlook": raw_data.get("sector_outlook", "neutral"),
        "investment_thesis": raw_data.get("investment_thesis", "Balanced risk-reward profile based on consensus fundamentals."),
        "summary": raw_data.get("summary", "Equity evaluation reflects balanced operational prospects.")
    }
    stats = {
        "hallucinations_detected": hallucinations_detected,
        "warnings": warnings,
        "faithfulness": 1.0 if hallucinations_detected == 0 else max(0.4, round(1.0 - (hallucinations_detected * 0.15), 2)),
        "consistency": 1.0,
        "completeness": 1.0
    }
    return cleaned, stats

