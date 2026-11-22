"""
Backwards-compatible alias for the autonomous Footprint & Supplier Research Agent.
"""
from ingestion.footprint_agent import (
    research_company_footprint as get_or_resolve_footprint,
    generate_perspective_queries as generate_queries_from_footprint,
    research_company_footprint,
    generate_perspective_queries,
    BENCHMARK_PROFILES as CURATED_PROFILES
)
from ingestion.models import CompanyFootprint, PhysicalHub, GeneratedPerspectiveQueries

__all__ = [
    "get_or_resolve_footprint",
    "generate_queries_from_footprint",
    "research_company_footprint",
    "generate_perspective_queries",
    "CompanyFootprint",
    "PhysicalHub",
    "GeneratedPerspectiveQueries",
    "CURATED_PROFILES"
]