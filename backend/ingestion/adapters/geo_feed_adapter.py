import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime
from ingestion.models import CompanyFootprint, PhysicalHub
from ingestion.footprint_agent import research_company_footprint, generate_perspective_queries
from loguru import logger

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
    max_items: int = 5
) -> List[Dict[str, Any]]:
    """Fetches and parses a localized Google News RSS feed."""
    encoded_q = quote_plus(query_str)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl={gl}&ceid={ceid}"
    
    articles = []
    try:
        resp = await client.get(url, headers=HEADERS, timeout=8.0)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:max_items]:
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

                articles.append({
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "published_at": pub_date,
                    "language": hl,
                    "country": gl
                })
    except Exception as e:
        logger.warning(f"Failed to fetch RSS for query '{query_str}' ({gl}/{hl}): {e}")
        
    return articles

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
                    filings.append({
                        "title": title,
                        "url": link,
                        "source": "SEC EDGAR 8-K",
                        "published_at": updated,
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
