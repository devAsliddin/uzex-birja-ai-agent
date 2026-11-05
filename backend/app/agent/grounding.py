"""Number formatting and deterministic grounding check.

Every number in a generated answer must be derivable (exactly or by rounding / scale words
like "млрд", "mln") from the SQL result rows or from the question itself; every quoted
name must appear in the rows or the question. Otherwise the answer is rejected.
"""

from __future__ import annotations

import math
import re
from typing import Any

_ID_COL = re.compile(r"(^|_)(no|num|number|inn|stir|code|id|year|month|day|tn_ved|ved|kod)(_|$)|inn|code|year", re.I)

NBSP = " "


def _group(int_str: str) -> str:
    neg = int_str.startswith("-")
    s = int_str.lstrip("-")
    out = []
    while len(s) > 3:
        out.insert(0, s[-3:])
        s = s[:-3]
    out.insert(0, s)
    return ("-" if neg else "") + " ".join(out)


def fmt_number(v: float | int, col: str = "") -> str:
    if isinstance(v, bool):
        return str(int(v))
    if col and _ID_COL.search(col):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) >= 1):
        return _group(str(int(v)))
    if not math.isfinite(v):
        return str(v)
    s = f"{v:.2f}"
    ip, dp = s.split(".")
    dp = dp.rstrip("0")
    return _group(ip) + ("." + dp if dp else "")


def fmt_cell(v: Any, col: str = "") -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return fmt_number(v, col)
    return v


def format_rows(columns: list[str], rows: list[list[Any]]) -> list[list[Any]]:
    return [[fmt_cell(v, columns[i] if i < len(columns) else "") for i, v in enumerate(r)] for r in rows]


# ---------------------------------------------------------------------------
# number extraction
# ---------------------------------------------------------------------------
_SCALE_WORDS = [
    (r"трлн|триллион\w*|trln|trillion\w*|trilliard", 1e12),
    (r"млрд|миллиард\w*|mlrd|milliard\w*|billion\w*", 1e9),
    (r"млн|миллион\w*|mln|million\w*", 1e6),
    (r"тыс\.?|тысяч\w*|ming", 1e3),
]
_NUM = re.compile(
    r"(?<![\w.])(-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?)"
    r"(?:\s*(" + "|".join(p for p, _ in _SCALE_WORDS) + r")(?![\w]))?",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
_LIST_NUM = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")
_CODE = re.compile(r"\bBK\d{2,4}\b", re.I)


def _scale_of(word: str | None) -> float:
    if not word:
        return 1.0
    w = word.lower()
    for pat, sc in _SCALE_WORDS:
        if re.fullmatch(pat, w, re.I):
            return sc
    return 1.0


def _to_float(token: str) -> tuple[float, int]:
    t = token.replace(" ", "").replace(NBSP, "").replace(" ", "")
    decimals = 0
    if "," in t or "." in t:
        sep = "," if "," in t else "."
        ip, dp = t.rsplit(sep, 1)
        ip = ip.replace(",", "").replace(".", "")
        decimals = len(dp)
        t = f"{ip}.{dp}"
    return float(t), decimals


def extract_numbers(text: str) -> list[tuple[float, int, float, str]]:
    """Return (value, decimals, scale, raw) for every number in text (dates split into parts)."""
    out: list[tuple[float, int, float, str]] = []
    text = _LIST_NUM.sub(" ", text)

    def _date_repl(m: re.Match) -> str:
        for g in m.groups():
            if g:
                out.append((float(int(g)), 0, 1.0, g))
        return " "

    text = _DATE.sub(_date_repl, text)
    for m in _NUM.finditer(text):
        try:
            val, dec = _to_float(m.group(1))
        except ValueError:
            continue
        out.append((val, dec, _scale_of(m.group(2)), m.group(0)))
    return out


def _source_numbers(columns: list[str], rows: list[list[Any]], extra_texts: list[str]) -> set[float]:
    nums: set[float] = set()
    for r in rows:
        for v in r:
            if isinstance(v, bool):
                nums.add(float(v))
            elif isinstance(v, (int, float)):
                nums.add(float(v))
            elif isinstance(v, str):
                for val, _d, sc, _raw in extract_numbers(v):
                    nums.add(val * sc)
                    nums.add(val)
    for t in extra_texts:
        for val, _d, sc, _raw in extract_numbers(t):
            nums.add(val * sc)
            nums.add(val)
    nums.add(float(len(rows)))
    return nums


def _matches(val: float, dec: int, scale: float, sources: set[float]) -> bool:
    val = abs(val)
    for s in sources:
        s = abs(s)
        for sc in {scale, 1.0} if scale != 1.0 else {1.0}:
            x = s / sc
            tol = 0.5 * 10 ** (-dec) + 1e-9
            if abs(x - val) <= tol:
                return True
            # allow rounding to fewer significant digits only via a scale word (e.g. 205.74 трлн)
        if scale == 1.0 and dec == 0 and val >= 1000:
            # integer rounding of a fractional source (e.g. 1 234 567.89 -> 1 234 568)
            if abs(round(s) - val) <= 1:
                return True
    return False


def check_grounding(
    answer: str, columns: list[str], rows: list[list[Any]], question: str, extra_texts: list[str] | None = None
) -> list[str]:
    """Return list of ungrounded tokens (empty = grounded)."""
    extra = [question] + list(extra_texts or [])
    sources = _source_numbers(columns, rows, extra)
    bad: list[str] = []
    for val, dec, scale, raw in extract_numbers(answer):
        if not _matches(val, dec, scale, sources):
            bad.append(raw.strip())
    hay = " ".join(str(v) for r in rows for v in r if v is not None) + " " + " ".join(extra)
    hay_n = _norm_text(hay)
    for code in _CODE.findall(answer):
        if code.lower() not in hay_n:
            bad.append(code)
    for q in re.findall(r"«([^»]{2,120})»|\"([^\"]{2,120})\"|“([^”]{2,120})”", answer):
        name = next((x for x in q if x), "")
        if name and _norm_text(name) not in hay_n:
            bad.append(name)
    return bad


_QUOTES = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "«": '"', "»": '"', "“": '"', "”": '"'})


def _norm_text(s: str) -> str:
    return " ".join(s.translate(_QUOTES).casefold().split())


def has_any_number(text: str) -> bool:
    return bool(re.search(r"\d", text))
