"""Command line CSV import:  python -m app.cli_import [--data-dir PATH]"""

from __future__ import annotations

import argparse
import asyncio
import time

from app.db.session import close_database, get_session_factory
from app.services.import_service import ImportService


async def _run(data_dir: str | None) -> int:
    service = ImportService(data_dir=data_dir)
    print(f"DATA_DIR = {service.data_dir.resolve()}")
    code = 0
    async with get_session_factory()() as db:
        t0 = time.perf_counter()
        for step in (
            service.import_brokers,
            service.import_participants,
            service.import_usd_rates,
            service.import_contracts,
            service.import_deals,
        ):
            t = time.perf_counter()
            report = await step(db)
            print(f"{report.summary_line()}  [{time.perf_counter() - t:.1f}s]")
            for err in report.errors:
                print(f"  ERROR: {err}")
                code = 1
        print(f"total {time.perf_counter() - t0:.1f}s")
    await close_database()
    return code


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_run(args.data_dir)))


if __name__ == "__main__":
    main()
