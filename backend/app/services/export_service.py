"""Streamed CSV / Excel export of (filtered) deals.

Rows are fetched in partitions and written incrementally, so memory stays flat
even for the 500k row cap (``EXPORT_MAX_ROWS``). Cells that could be
interpreted as spreadsheet formulas are neutralised (CSV/Excel injection).
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from fastapi.responses import StreamingResponse

from app.db.session import get_read_session_factory
from app.services import registry_service as rs

PARTITION = 5000
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, str) and v.startswith(_FORMULA_PREFIX):
        return "'" + v
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


async def _rows(conditions: list[Any]) -> AsyncIterator[list[dict[str, Any]]]:
    async with get_read_session_factory()() as session:
        result = await session.stream(rs.export_query(conditions))
        async for part in result.partitions(PARTITION):
            yield [rs._row_to_dict(r) for r in part]


def _filename(ext: str) -> str:
    return f"deals_{date.today().isoformat()}.{ext}"


def csv_response(conditions: list[Any]) -> StreamingResponse:
    async def gen() -> AsyncIterator[bytes]:
        buf = io.StringIO()
        buf.write("﻿")
        csv.writer(buf).writerow(rs.EXPORT_COLUMNS)
        yield buf.getvalue().encode("utf-8")
        async for part in _rows(conditions):
            buf = io.StringIO()
            w = csv.writer(buf)
            for d in part:
                w.writerow([_cell(d.get(c)) for c in rs.EXPORT_COLUMNS])
            yield buf.getvalue().encode("utf-8")

    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename("csv")}"'},
    )


def xlsx_response(conditions: list[Any]) -> StreamingResponse:
    from openpyxl import Workbook

    async def gen() -> AsyncIterator[bytes]:
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("deals")
        ws.append(rs.EXPORT_COLUMNS)
        async for part in _rows(conditions):
            for d in part:
                ws.append([_cell(d.get(c)) for c in rs.EXPORT_COLUMNS])
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb.save(path)
            with open(path, "rb") as f:
                while chunk := f.read(1 << 16):
                    yield chunk
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    return StreamingResponse(
        gen(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_filename("xlsx")}"'},
    )


def export_response(fmt: str, conditions: list[Any]) -> StreamingResponse:
    return xlsx_response(conditions) if fmt == "xlsx" else csv_response(conditions)
