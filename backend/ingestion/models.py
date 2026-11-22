from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class PhysicalHub(BaseModel):
    region_name: str         # e.g., "Germany (Brandenburg)", "India (Bengaluru)", "United Kingdom (FRC Oversight)"
    country_code: str        # e.g., "DE", "ID", "TW", "CN", "IN", "GB", "US"
    language_code: str       # e.g., "de", "id", "zh-TW", "zh-CN", "en"
    hub_name: str            # e.g., "Gruenheide Gigafactory", "Bengaluru Delivery Center", "Hsinchu Fab 12"
    local_keywords: str      # e.g., "Fabrik OR Wasser OR Brand", "layoff OR dispute OR labor"
    facility_type: str       # e.g., "gigafactory", "foundry", "smelter", "global_delivery_center", "regulatory_tribunal", "data_center_campus"
    
    # Provenance fields for cross-checking:
    source_url: Optional[str] = None       # e.g. "https://www.sec.gov/ix?doc=/Archives/edgar/data/..."
    source_type: Optional[str] = None      # "sec_10k", "wikipedia", "press_report"
    evidence_quote: Optional[str] = None   # Short verbatim quote or fact excerpt

class SupplierEvidence(BaseModel):
    name: str                              # e.g., "TSMC", "CATL", "Foxconn"
    category: Optional[str] = None         # "foundry", "battery_cells", "assembly", "cloud_infrastructure"
    source_url: Optional[str] = None       # Verified source link
    source_type: Optional[str] = None      # "sec_10k", "wikipedia", "press_report"
    evidence_quote: Optional[str] = None   # Direct excerpt confirming supplier relationship

class FootprintEvaluation(BaseModel):
    faithfulness_score: float = 1.0        # Ratio of verified grounded claims (0.0 - 1.0)
    citation_grounding_score: float = 1.0  # Quality and validity of source URLs (0.0 - 1.0)
    completeness_score: float = 1.0        # Coverage of discovered hubs & tier-1 suppliers (0.0 - 1.0)
    overall_quality_score: float = 1.0     # Weighted harmonic mean score (0.0 - 1.0)
    grade: str = "A"                       # "A", "B", "C", "FAIL"
    guardrails_passed: bool = True
    hallucinations_detected: int = 0
    warnings: List[str] = []
    details: Dict[str, Any] = {}

class CompanyFootprint(BaseModel):
    ticker: str
    name: str
    cik: Optional[str] = None
    sector: Optional[str] = None
    primary_country: str = "US"
    archetype: str = "industrial_hardware"  # "industrial_hardware", "professional_services", "financial_institution", "digital_cloud_saas", "energy_mining_materials", "biotech_pharma"
    hubs: List[PhysicalHub] = []
    key_suppliers: List[Union[SupplierEvidence, str, Dict[str, Any]]] = []
    dependencies: List[str] = []
    western_focus: str = "earnings OR stock OR supply chain OR investigation"
    source: str = "research_agent"  # "research_agent", "curated", "dynamic_fallback"
    token_usage: Optional[Dict[str, Any]] = None
    evaluation: Optional[FootprintEvaluation] = None

class GeneratedPerspectiveQueries(BaseModel):
    ticker: str
    company_name: str
    archetype: str = "industrial_hardware"
    western_query: Dict[str, str]
    local_queries: List[Dict[str, str]]
    corporate_query: Dict[str, Any]
    supplier_queries: List[Dict[str, str]] = []