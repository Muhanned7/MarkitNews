import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from agents.api_monitor import record_external_api_call
from ingestion.models import CompanyFootprint, PhysicalHub
from ingestion.footprint_agent import research_company_footprint, generate_perspective_queries
from loguru import logger

# Temporal Regime Thresholds (in days)
ACTIVE_SHOCK_MAX_DAYS = 30
RECOVERY_LAG_MAX_DAYS = 180


def classify_article_temporal_regime(
    pub_date_str: Optional[str],
    reference_now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Deterministically parses an article's publication timestamp (RFC-2822 RSS <pubDate>
    or ISO-8601 Atom <updated>) and classifies it into a Supply-Chain Temporal Regime:
      - ACTIVE_SHOCK (0 - 30 days): Immediate operational flow disruption; valid for live Contradiction Radar alerts.
      - RECOVERY_LAG (31 - 180 days): Medium-term inventory whip-saw, rebuild, or COGS/margin lag phase.
      - HISTORICAL_STRUCTURAL (> 180 days): Resolved operational flow; use strictly for long-term structural
        vulnerability (SPOF proof, dual-sourcing shifts, geographic diversification) — NEVER as a live shipment halt.
    """
    now_dt = reference_now or datetime.now(timezone.utc)
    if not pub_date_str or not isinstance(pub_date_str, str):
        return {
            "age_days": None,
            "temporal_regime": "UNKNOWN_DATE",
            "is_live_contradiction_eligible": True,
            "temporal_guidance": "Publication date unavailable; verify recency before treating as an active shock."
        }

    parsed_dt: Optional[datetime] = None
    raw_str = pub_date_str.strip()
    try:
        parsed_dt = parsedate_to_datetime(raw_str)
    except Exception:
        try:
            iso_norm = raw_str.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(iso_norm)
        except Exception:
            parsed_dt = None

    if parsed_dt is None:
        return {
            "age_days": None,
            "temporal_regime": "UNKNOWN_DATE",
            "is_live_contradiction_eligible": True,
            "temporal_guidance": "Unparseable timestamp; verify recency before treating as an active shock."
        }

    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

    age_days = max(0, (now_dt - parsed_dt).days)

    if age_days <= ACTIVE_SHOCK_MAX_DAYS:
        return {
            "age_days": age_days,
            "temporal_regime": "ACTIVE_SHOCK",
            "is_live_contradiction_eligible": True,
            "temporal_guidance": (
                f"Published {age_days}d ago (ACTIVE_SHOCK <=30d): Direct operational flow impact on current quarter "
                "shipments/production. Eligible for live Contradiction Radar alert."
            )
        }
    elif age_days <= RECOVERY_LAG_MAX_DAYS:
        return {
            "age_days": age_days,
            "temporal_regime": "RECOVERY_LAG",
            "is_live_contradiction_eligible": True,
            "temporal_guidance": (
                f"Published {age_days}d ago (RECOVERY_LAG 31-180d): Physical shock is in rebuild/recovery phase; "
                "evaluate for lagged inventory drawdown, expedited freight costs, or upcoming quarterly gross-margin compression."
            )
        }
    else:
        years_ago = round(age_days / 365.25, 1)
        return {
            "age_days": age_days,
            "temporal_regime": "HISTORICAL_STRUCTURAL",
            "is_live_contradiction_eligible": False,
            "temporal_guidance": (
                f"Published {age_days}d (~{years_ago} yrs) ago (HISTORICAL_STRUCTURAL >180d): DO NOT cite as an active "
                "shipment halt or breaking contradiction. Evaluate strictly for long-term structural supply-chain effect: "
                "Single-Point-of-Failure (SPOF) historical proof, post-crisis geographic diversification, or dual-sourcing shifts."
            )
        }

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*"
}

SEC_HEADERS = {
    "User-Agent": "MarketPulseResearch/1.0 (contact: research@marketpulse.local)",
    "Accept": "application/atom+xml, application/xml, text/xml, */*"
}

def clean_xml_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # Strip HTML tags if any
    import re
    cleaned = re.sub(r"<[^>]+>", "", text)
    return cleaned.strip()

async def fetch_rss_feed(
    client: httpx.AsyncClient,
    query_str: str,
    gl: str = "US",
    hl: str = "en-US",
    ceid: str = "US:en",
    max_items: int = 5,
    recency_window: Optional[str] = "90d",
    include_historical_fallback: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetches and parses a localized Google News RSS feed with deterministic Temporal Regime classification.
    - First queries with `when:{recency_window}` (default 90d) so live Contradiction Radar prioritizes active/recent shocks.
    - If 0 recent items exist and `include_historical_fallback=True`, falls back to the un-windowed archive
      and deterministically tags old articles (`age_days > 180`) as `HISTORICAL_STRUCTURAL` so downstream
      agents analyze their long-term structural supply-chain effect rather than treating them as breaking news.
    """
    async def _query_rss(q_text: str) -> List[Dict[str, Any]]:
        encoded_q = quote_plus(q_text)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl={gl}&ceid={ceid}"
        parsed_items: List[Dict[str, Any]] = []
        t0 = time.time()
        try:
            resp = await client.get(url, headers=HEADERS, timeout=8.0)
            record_external_api_call(
                provider="google_news_rss",
                endpoint="https://news.google.com/rss/search",
                operation=f"fetch_rss_feed ({gl}/{hl})",
                status_code=resp.status_code,
                duration_ms=(time.time() - t0) * 1000,
            )
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item")[:max_items * 2]:
                    title = clean_xml_text(item.findtext("title"))
                    link = item.findtext("link") or ""
                    pub_date = item.findtext("pubDate") or ""
                    source_elem = item.find("source")
                    source_name = source_elem.text if source_elem is not None else "Google News"

                    # Split source from title if format is "Title - Source"
                    if " - " in title and source_name == "Google News":
                        parts = title.rsplit(" - ", 1)
                        title = parts[0]
                        source_name = parts[1]

                    temporal_meta = classify_article_temporal_regime(pub_date)
                    parsed_items.append({
                        "title": title,
                        "url": link,
                        "source": source_name,
                        "published_at": pub_date,
                        "age_days": temporal_meta["age_days"],
                        "temporal_regime": temporal_meta["temporal_regime"],
                        "is_live_contradiction_eligible": temporal_meta["is_live_contradiction_eligible"],
                        "temporal_guidance": temporal_meta["temporal_guidance"],
                        "language": hl,
                        "country": gl
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch RSS for query '{q_text}' ({gl}/{hl}): {e}")
        return parsed_items

    # 1. Primary recency-scoped query for active/recent operational events
    scoped_query = f"{query_str} when:{recency_window}" if recency_window and "when:" not in query_str else query_str
    articles = await _query_rss(scoped_query)

    # 2. If recency window yields fewer than max_items and historical structural context is allowed, merge archive hits
    if len(articles) < max_items and include_historical_fallback and scoped_query != query_str:
        archive_articles = await _query_rss(query_str)
        seen_urls = {a["url"] for a in articles}
        for arch in archive_articles:
            if arch["url"] not in seen_urls:
                seen_urls.add(arch["url"])
                articles.append(arch)
                if len(articles) >= max_items:
                    break

    # Sort newest first (None age_days placed after known recent articles)
    articles.sort(key=lambda a: a["age_days"] if a.get("age_days") is not None else 999999)
    return articles[:max_items]

async def fetch_sec_filings_atom(
    client: httpx.AsyncClient,
    company_name: str,
    cik: Optional[str] = None,
    max_items: int = 5
) -> List[Dict[str, Any]]:
    """Fetches real-time 8-K filings from SEC EDGAR Atom feed filtered by company."""
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"
    filings = []
    
    try:
        resp = await client.get(url, headers=SEC_HEADERS, timeout=8.0)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            name_lower = company_name.lower().split()[0] # e.g. "tesla", "apple", "accenture"
            
            for entry in root.findall(".//atom:entry", ns):
                title = clean_xml_text(entry.findtext("atom:title", namespaces=ns))
                summary = clean_xml_text(entry.findtext("atom:summary", namespaces=ns))
                updated = entry.findtext("atom:updated", namespaces=ns) or ""
                link_elem = entry.find("atom:link", namespaces=ns)
                link = link_elem.attrib.get("href") if link_elem is not None else ""
                
                # Match by company name or CIK if present
                if name_lower in title.lower() or (cik and cik in title) or (cik and cik in summary):
                    temporal_meta = classify_article_temporal_regime(updated)
                    filings.append({
                        "title": title,
                        "url": link,
                        "source": "SEC EDGAR 8-K",
                        "published_at": updated,
                        "age_days": temporal_meta["age_days"],
                        "temporal_regime": temporal_meta["temporal_regime"],
                        "is_live_contradiction_eligible": temporal_meta["is_live_contradiction_eligible"],
                        "temporal_guidance": temporal_meta["temporal_guidance"],
                        "summary": summary[:200]
                    })
                    if len(filings) >= max_items:
                        break
    except Exception as e:
        logger.warning(f"Failed to fetch SEC 8-K Atom feed: {e}")
        
    return filings

async def fetch_tri_perspective_mesh(
    ticker: str,
    footprint: Optional[CompanyFootprint] = None,
    max_items_per_tier: int = 4
) -> Dict[str, Any]:
    """
    Ingests live headlines across all 3 primary perspective tiers:
    1. Western Wire
    2. Localized On-Ground Press (from all discovered hubs)
    3. Corporate PR & Regulatory 8-K
    Plus:
    4. Supplier Disruption Watch
    """
    # 1. Resolve footprint if not provided
    if not footprint:
        footprint = await research_company_footprint(ticker)
        
    queries = generate_perspective_queries(footprint)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Task 1: Western Wire Feed
        w_task = fetch_rss_feed(
            client=client,
            query_str=queries.western_query["search_term"],
            gl=queries.western_query["gl"],
            hl=queries.western_query["hl"],
            ceid=queries.western_query["ceid"],
            max_items=max_items_per_tier
        )

        # Task 2: Localized On-Ground Press Feeds (concurrent across all discovered hubs)
        local_tasks = []
        for lq in queries.local_queries:
            local_tasks.append(
                fetch_rss_feed(
                    client=client,
                    query_str=lq["search_term"],
                    gl=lq["gl"],
                    hl=lq["hl"],
                    ceid=lq["ceid"],
                    max_items=max_items_per_tier
                )
            )

        # Task 3: Corporate Official PR & SEC 8-K
        pr_query_str = queries.corporate_query["pr_search_term"]
        pr_task = fetch_rss_feed(
            client=client,
            query_str=pr_query_str,
            gl="US",
            hl="en-US",
            ceid="US:en",
            max_items=max_items_per_tier
        )
        sec_task = fetch_sec_filings_atom(
            client=client,
            company_name=footprint.name,
            cik=footprint.cik,
            max_items=max_items_per_tier
        )

        # Task 4: Supplier Disruption Watch Feeds (top 2 suppliers)
        supplier_tasks = []
        for sq in queries.supplier_queries[:2]:
            supplier_tasks.append(
                fetch_rss_feed(
                    client=client,
                    query_str=sq["search_term"],
                    gl=sq["gl"],
                    hl=sq["hl"],
                    ceid="US:en",
                    max_items=2
                )
            )

        # Execute concurrent network fetch
        results = await asyncio.gather(
            w_task,
            asyncio.gather(*local_tasks) if local_tasks else asyncio.sleep(0, result=[]),
            pr_task,
            sec_task,
            asyncio.gather(*supplier_tasks) if supplier_tasks else asyncio.sleep(0, result=[]),
            return_exceptions=True
        )

        western_articles = results[0] if isinstance(results[0], list) else []
        local_results_list = results[1] if isinstance(results[1], list) else []
        corporate_pr_articles = results[2] if isinstance(results[2], list) else []
        sec_filings = results[3] if isinstance(results[3], list) else []
        supplier_results_list = results[4] if isinstance(results[4], list) else []

    # Format localized press with hub context and verified source links
    local_press_by_hub = []
    for i, hub in enumerate(footprint.hubs):
        articles = local_results_list[i] if i < len(local_results_list) and isinstance(local_results_list[i], list) else []
        local_press_by_hub.append({
            "hub_name": hub.hub_name,
            "region": hub.region_name,
            "country_code": hub.country_code,
            "facility_type": hub.facility_type,
            "source_url": hub.source_url,
            "source_type": hub.source_type,
            "evidence_quote": hub.evidence_quote,
            "articles": articles
        })

    # Format corporate filings & PR
    combined_corporate = corporate_pr_articles + sec_filings

    # Format supplier watch
    supplier_watch = []
    for j, s in enumerate(footprint.key_suppliers[:2]):
        articles = supplier_results_list[j] if j < len(supplier_results_list) and isinstance(supplier_results_list[j], list) else []
        supplier_name = s.name if hasattr(s, "name") else (s.get("name") if isinstance(s, dict) else str(s))
        source_url = getattr(s, "source_url", None) or (s.get("source_url") if isinstance(s, dict) else None)
        evidence_quote = getattr(s, "evidence_quote", None) or (s.get("evidence_quote") if isinstance(s, dict) else None)
        supplier_watch.append({
            "supplier": supplier_name,
            "source_url": source_url,
            "evidence_quote": evidence_quote,
            "articles": articles
        })

    return {
        "ticker": footprint.ticker,
        "company_name": footprint.name,
        "archetype": footprint.archetype,
        "western_wire": {
            "tier_label": "Tier 1: Western Financial Wires (Global Perspective)",
            "query_used": queries.western_query["search_term"],
            "count": len(western_articles),
            "articles": western_articles
        },
        "local_press": {
            "tier_label": "Tier 2: Localized On-Ground Press (Operational Ground Truth)",
            "hubs_tracked": len(footprint.hubs),
            "hubs": local_press_by_hub
        },
        "corporate_pr": {
            "tier_label": "Tier 3: Corporate Communications & SEC 8-K Disclosures",
            "count": len(combined_corporate),
            "articles": combined_corporate
        },
        "supplier_disruption_watch": {
            "tier_label": "Tier 4: Critical Tier-1 Supplier Disruption Monitoring",
            "suppliers_tracked": len(supplier_watch),
            "suppliers": supplier_watch
        }
    }
