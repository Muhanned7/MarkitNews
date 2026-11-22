"""Scratch demo: runs one footprint lookup, then prints the new fingerprint columns."""
import asyncio
import json
import sys

from agents.db import query
from ingestion.footprint_agent import research_company_footprint

TICKER = sys.argv[1] if len(sys.argv) > 1 else "TSLA"


def show(label: str) -> None:
    res = query(
        """SELECT ticker, source, source_fingerprint, fingerprint_checked_at, updated_at
           FROM company_footprints WHERE ticker = %s""",
        [TICKER],
    )
    print(f"\n--- {label} ---")
    if not res.rows:
        print("(no row)")
        return
    row = res.rows[0]
    for k, v in row.items():
        if k == "source_fingerprint":
            v = json.dumps(v, indent=2)
        print(f"{k:24}: {v}")


async def main() -> None:
    fp = await research_company_footprint(TICKER)
    print(f"\nFootprint: {fp.name} | hubs={len(fp.hubs)} | suppliers={len(fp.key_suppliers)}")
    show("company_footprints row")

    cols = query(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_name = 'company_footprints' ORDER BY ordinal_position"""
    )
    print("\n--- table columns ---")
    for c in cols.rows:
        print(f"{c['column_name']:24}: {c['data_type']}")


asyncio.run(main())
