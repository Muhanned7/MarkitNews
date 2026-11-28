import asyncio
import hashlib
import html as html_lib
import re
import urllib.parse
import xml.etree.ElementTree as ET
import time
from typing import Dict, Any, List, Optional
import httpx
from loguru import logger
from agents.api_monitor import record_external_api_call

SEC_HEADERS = {
    "User-Agent": "MarketPulseResearch/1.0 (contact: research@marketpulse.local)",
    "Accept": "application/json, text/html, */*"
}

WIKI_HEADERS = {
    "User-Agent": "MarketPulseBot/1.0 (contact: info@marketpulse.local)",
    "Accept": "application/json"
}

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Cache ticker-to-CIK mapping
_CIK_CACHE: Dict[str, str] = {
    "TSLA": "0001318605",
    "AAPL": "0000320193",
    "NVDA": "0001045810",
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "TSM": "0001046179",
    "VALE": "0000917225",
    "ACN": "0001467373",
    "CRM": "0001108524"
}

async def resolve_cik(client: httpx.AsyncClient, ticker: str) -> Optional[str]:
    """Resolves SEC CIK for a ticker symbol."""
    clean_t = ticker.upper().strip()
    if clean_t in _CIK_CACHE:
        return _CIK_CACHE[clean_t]
    
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        resp = await client.get(url, headers=SEC_HEADERS, timeout=6.0)
        if resp.status_code == 200:
            data = resp.json()
            for entry in data.values():
                if entry.get("ticker", "").upper() == clean_t:
                    cik_num = str(entry["cik_str"]).zfill(10)
                    _CIK_CACHE[clean_t] = cik_num
                    return cik_num
    except Exception as e:
        logger.warning(f"Could not resolve CIK for {ticker}: {e}")
    return None

async def fetch_sec_properties(ticker: str, cik: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches Item 2 (Properties) and overseas subsidiary details from the latest SEC 10-K / 20-F.
    Returns the excerpt and the permanent SEC EDGAR filing URL.
    """
    clean_t = ticker.upper().strip()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        cik_num = cik or await resolve_cik(client, clean_t)
        if not cik_num:
            return {
                "found": False,
                "error": f"No CIK found for ticker {ticker}",
                "source_type": "sec_10k",
                "source_url": None,
                "text": ""
            }

        cik_clean = str(int(cik_num))
        cik_10 = cik_num.zfill(10)
        
        try:
            # 1. Fetch submission history
            sub_url = f"https://data.sec.gov/submissions/CIK{cik_10}.json"
            t0 = time.time()
            resp = await client.get(sub_url, headers=SEC_HEADERS, timeout=8.0)
            record_external_api_call(
                provider="sec_edgar",
                endpoint=sub_url,
                operation="fetch_10k_submissions",
                ticker=clean_t,
                status_code=resp.status_code,
                duration_ms=(time.time() - t0) * 1000,
            )
            if resp.status_code != 200:
                return {
                    "found": False,
                    "error": f"SEC API returned status {resp.status_code}",
                    "source_type": "sec_10k",
                    "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik_10}",
                    "text": ""
                }

            sub_data = resp.json()
            recent = sub_data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            
            # Locate latest 10-K or 20-F
            target_idx = None
            for idx, form_type in enumerate(forms):
                if form_type in ["10-K", "20-F"]:
                    target_idx = idx
                    break

            if target_idx is None:
                return {
                    "found": False,
                    "error": "No 10-K or 20-F found in recent filings",
                    "source_type": "sec_10k",
                    "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik_10}",
                    "text": ""
                }

            acc_raw = recent["accessionNumber"][target_idx]
            acc_nodash = acc_raw.replace("-", "")
            doc_name = recent["primaryDocument"][target_idx]
            filing_date = recent["filingDate"][target_idx]
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_nodash}/{doc_name}"

            # 2. Fetch the filing text document (limit read to first 500KB to parse Item 2)
            doc_resp = await client.get(filing_url, headers=SEC_HEADERS, timeout=12.0)
            doc_html = doc_resp.text
            
            # Simple text extractor from HTML
            clean_text = re.sub(r"<style[^>]*>.*?</style>", "", doc_html, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<script[^>]*>.*?</script>", "", clean_text, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
            clean_text = html_lib.unescape(clean_text)
            clean_text = re.sub(r"\s+", " ", clean_text)

            # Locate actual "Item 2. Properties" section (skip short Table-of-Contents matches < 150 chars)
            candidates = [
                m.group(1).strip()
                for m in re.finditer(
                    r"(Item\s+2[\.\:\-\s]+Properties.*?)(?=Item\s+3[\.\:\-\s]|Item\s+4[\.\:\-\s]|PART\s+II\b|$)",
                    clean_text,
                    re.IGNORECASE,
                )
                if len(m.group(1).strip()) > 150
            ]

            item2_text = ""
            if candidates:
                # Pick the substantive Item 2 body (not the TOC row)
                item2_text = max(candidates[:3], key=len)[:3000].strip()

            # Also harvest supply-chain / manufacturing sentences from the 10-K so supplier evidence is included
            facility_snippets = []
            sentences = re.split(r"(?<=[.!?])\s+", clean_text)
            for s in sentences:
                s_low = s.lower()
                if 35 < len(s) < 500 and any(
                    w in s_low
                    for w in [
                        "principal properties",
                        "manufacturing facilities",
                        "gigafactory",
                        "corporate headquarters",
                        "square feet",
                        "tsmc",
                        "taiwan semiconductor",
                        "foxconn",
                        "foundry",
                        "contract manufacturer",
                        "wafer",
                        "packaging",
                    ]
                ):
                    facility_snippets.append(s.strip())
                    if len(facility_snippets) >= 10:
                        break

            extra_supply_text = " ".join(facility_snippets)[:2000]
            combined_sec_text = f"{item2_text} {extra_supply_text}".strip()[:4000]

            return {
                "found": True,
                "ticker": clean_t,
                "cik": cik_10,
                "filing_date": filing_date,
                "source_type": "sec_10k",
                "source_url": filing_url,
                "text": combined_sec_text or "Properties disclosed in Item 2."
            }

        except Exception as e:
            logger.warning(f"Error fetching SEC properties for {ticker}: {e}")
            return {
                "found": False,
                "error": str(e),
                "source_type": "sec_10k",
                "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik_10}" if cik_10 else None,
                "text": ""
            }

async def fetch_wikipedia_facilities(company_name: str) -> Dict[str, Any]:
    """
    Fetches facility, manufacturing, operational campus, and subsidiary paragraphs from Wikipedia.
    Returns extracted text and the exact Wikipedia article URL.
    """
    # Clean company suffixes for accurate Wikipedia page search
    clean_name = _clean_company_name(company_name)
    encoded_q = urllib.parse.quote(clean_name)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # 1. Search for title
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded_q}&limit=1&format=json"
            s_resp = await client.get(search_url, headers=WIKI_HEADERS, timeout=6.0)
            if s_resp.status_code != 200:
                return {"found": False, "source_type": "wikipedia", "source_url": None, "text": ""}
                
            s_data = s_resp.json()
            if not s_data[1]:
                return {"found": False, "source_type": "wikipedia", "source_url": None, "text": ""}
                
            title = s_data[1][0]
            wiki_url = s_data[3][0]

            # 2. Fetch plaintext extract
            title_encoded = urllib.parse.quote(title)
            extract_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={title_encoded}&format=json"
            t_wiki = time.time()
            e_resp = await client.get(extract_url, headers=WIKI_HEADERS, timeout=8.0)
            record_external_api_call(
                provider="wikipedia",
                endpoint="https://en.wikipedia.org/w/api.php",
                operation=f"fetch_wikipedia_facilities ({title})",
                status_code=e_resp.status_code,
                duration_ms=(time.time() - t_wiki) * 1000,
            )
            if e_resp.status_code != 200:
                return {"found": False, "source_type": "wikipedia", "source_url": wiki_url, "text": ""}
                
            pages = e_resp.json().get("query", {}).get("pages", {})
            full_text = list(pages.values())[0].get("extract", "") if pages else ""

            # 3. Filter for paragraphs containing physical facilities, locations, supply chain
            relevant_paragraphs = []
            for p in full_text.split("\n"):
                p_lower = p.lower()
                if any(k in p_lower for k in [
                    "gigafactory", "factory", "plant", "foundry", "assembly", 
                    "manufacturing", "delivery center", "headquarters", "campus",
                    "subsidiaries", "supplier", "facilities", "foxconn", "tsmc"
                ]) and len(p.split()) > 10:
                    relevant_paragraphs.append(p.strip())
                    if len(relevant_paragraphs) >= 8:
                        break

            extracted_snippet = "\n\n".join(relevant_paragraphs)[:4000]

            return {
                "found": True,
                "company_name": company_name,
                "wikipedia_title": title,
                "source_type": "wikipedia",
                "source_url": wiki_url,
                "text": extracted_snippet or full_text[:1500]
            }
        except Exception as e:
            logger.warning(f"Error fetching Wikipedia facilities for {company_name}: {e}")
            return {"found": False, "source_type": "wikipedia", "source_url": None, "text": ""}

def _clean_company_name(company_name: str) -> str:
    """Strips legal suffixes (Inc, Corp, plc...) for Wikipedia lookups."""
    clean_name = re.sub(r"\b(Inc|Corporation|Corp|plc|Co|Ltd|LLC|S\.A\.|Holdings)\b\.?", "", company_name, flags=re.IGNORECASE)
    return clean_name.replace(",", "").replace(".", "").strip()


async def _latest_annual_accession(client: httpx.AsyncClient, ticker: str, cik: Optional[str]) -> Optional[str]:
    """Returns the accession number of the latest 10-K/20-F (submissions metadata only, no document download)."""
    try:
        cik_num = cik or await resolve_cik(client, ticker)
        if not cik_num:
            return None
        resp = await client.get(
            f"https://data.sec.gov/submissions/CIK{str(cik_num).zfill(10)}.json",
            headers=SEC_HEADERS, timeout=6.0
        )
        if resp.status_code != 200:
            return None
        recent = resp.json().get("filings", {}).get("recent", {})
        for idx, form_type in enumerate(recent.get("form", [])):
            if form_type in ("10-K", "20-F"):
                return recent["accessionNumber"][idx]
    except Exception as e:
        logger.warning(f"Fingerprint: SEC accession lookup failed for {ticker}: {e}")
    return None


async def _wiki_last_revision(client: httpx.AsyncClient, company_name: str) -> Optional[int]:
    """Returns the Wikipedia page's lastrevid in a single tiny API call."""
    try:
        params = {
            "action": "query", "generator": "search", "gsrsearch": _clean_company_name(company_name),
            "gsrlimit": 1, "prop": "info", "format": "json"
        }
        resp = await client.get("https://en.wikipedia.org/w/api.php", params=params, headers=WIKI_HEADERS, timeout=6.0)
        if resp.status_code != 200:
            return None
        pages = resp.json().get("query", {}).get("pages", {})
        if not pages:
            return None
        return next(iter(pages.values())).get("lastrevid")
    except Exception as e:
        logger.warning(f"Fingerprint: Wikipedia revision lookup failed for {company_name}: {e}")
    return None


async def fetch_wiki_content_hash(company_name: str) -> Optional[str]:
    """
    Hashes only the facility/supplier paragraphs of the Wikipedia article.
    Used as a 2nd-stage check so unrelated edits (typos, infobox tweaks) don't trigger re-research.
    """
    wiki = await fetch_wikipedia_facilities(company_name)
    if not wiki.get("found") or not wiki.get("text"):
        return None
    normalized = re.sub(r"\s+", " ", wiki["text"]).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


async def fetch_source_fingerprint(
    ticker: str,
    company_name: str,
    cik: Optional[str] = None,
    include_content_hash: bool = False
) -> Dict[str, Any]:
    """
    Cheap change-detection probe for a cached footprint (no LLM, no 10-K download).
    Fields are None when a source could not be reached, meaning 'unknown', not 'changed'.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        sec_acc, wiki_rev = await asyncio.gather(
            _latest_annual_accession(client, ticker.upper().strip(), cik),
            _wiki_last_revision(client, company_name)
        )
    fingerprint: Dict[str, Any] = {"sec_accession": sec_acc, "wiki_revid": wiki_rev}
    if include_content_hash:
        fingerprint["wiki_content_hash"] = await fetch_wiki_content_hash(company_name)
    return fingerprint


async def search_web_sources(query: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """
    Queries open search to uncover tier-1 suppliers, outsourced assemblers, or regional hubs.
    Tries DuckDuckGo HTML first, then falls back to free Google News Search RSS so development
    and live runs always receive real news articles and verified URLs at $0 cost.
    """
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Primary attempt: DuckDuckGo HTML
        try:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=WEB_HEADERS,
                timeout=6.0
            )
            if resp.status_code == 200:
                html = resp.text
                link_matches = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
                snippet_matches = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html)

                for i in range(min(len(snippet_matches), max_results)):
                    raw_snippet = html_lib.unescape(re.sub(r"<[^>]+>", "", snippet_matches[i])).strip()
                    raw_url = link_matches[i][0] if i < len(link_matches) else ""

                    if "uddg=" in raw_url:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                        actual_url = parsed.get("uddg", [raw_url])[0]
                    else:
                        actual_url = raw_url

                    if raw_snippet:
                        results.append({
                            "snippet": raw_snippet,
                            "source_url": actual_url or "https://duckduckgo.com",
                            "source_type": "web_search"
                        })
        except Exception as e:
            logger.debug(f"DuckDuckGo HTML search skipped for '{query}': {e}")

        # 2. Free Fallback: Google News Search RSS (100% free, no API key, returns real articles & URLs)
        if not results:
            try:
                encoded_q = urllib.parse.quote_plus(query)
                rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
                rss_resp = await client.get(rss_url, headers=WEB_HEADERS, timeout=8.0)
                if rss_resp.status_code == 200:
                    root = ET.fromstring(rss_resp.text)
                    for item in root.findall(".//item")[:max_results]:
                        title = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        desc_raw = item.findtext("description") or ""
                        desc_clean = html_lib.unescape(re.sub(r"<[^>]+>", " ", desc_raw)).strip()
                        desc_clean = re.sub(r"\s+", " ", desc_clean)
                        source_el = item.find("source")
                        source_url = (
                            source_el.attrib.get("url", "").strip()
                            if source_el is not None and source_el.attrib.get("url")
                            else link
                        )
                        snippet_text = f"{title}. {desc_clean}".strip() if desc_clean and desc_clean != title else title
                        if snippet_text:
                            results.append({
                                "snippet": snippet_text,
                                "source_url": link or source_url or "https://news.google.com",
                                "publisher_url": source_url,
                                "source_type": "web_search",
                            })
            except Exception as e:
                logger.warning(f"Google News RSS fallback search failed for '{query}': {e}")

    return results
