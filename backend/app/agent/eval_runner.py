"""Run the golden set against the agent engine.

Usage (from backend/):  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.agent.eval_runner [--ids c01,s01] [--tag name]
Writes ../eval/results_<tag>.json and prints accuracy, no_data correctness, hallucinations, latency, tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from app.agent.engine import AgentEngine
from app.agent.grounding import extract_numbers

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"


def _norm(s: str) -> str:
    tr = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "«": '"', "»": '"', "“": '"', "”": '"', " ": " "})
    return " ".join(str(s).translate(tr).casefold().split())


def _num_found(expected: float, answer: str, tol: float) -> bool:
    for val, _dec, scale, _raw in extract_numbers(answer):
        got = val * scale
        if expected == 0:
            if got == 0:
                return True
            continue
        rel = abs(got - expected) / abs(expected)
        if scale != 1.0:
            # "42.72 трлн": allow the rounding implied by the written precision
            if rel <= max(tol, 0.006):
                return True
        elif rel <= tol or abs(got - expected) <= 0.011:
            return True
    return False


def _item_found(item: Any, answer: str, tol: float) -> bool:
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return _num_found(float(item), answer, tol)
    s = str(item)
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return _num_found(float(s), answer, tol) or s in answer
    if s == "Нет":
        return bool(re.search(r"(?i)\bнет\b|yo'q|йўқ|emas\b|эмас", answer))
    if s == "Да":
        return bool(re.search(r"(?i)\b(да|ha|ҳа)\b|to.?lovchisi|плательщик", answer))
    n = _norm(s)
    a = _norm(answer)
    if n in a:
        return True
    # company names: accept without outer quotes / legal form
    core = re.sub(r'"', "", n)
    return core in re.sub(r'"', "", a)


def grade(item: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    ans = res.get("answer", "")
    q = item["question"]
    if item["kind"] == "no_data":
        q_nums = {round(v * s, 6) for v, _d, s, _r in extract_numbers(q)}
        # a date the question itself names ("12 мая 2024" -> "12.05.2024") is not an invented number
        for dd, mm, yy in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", ans):
            if float(yy) in q_nums and float(int(dd)) in q_nums:
                q_nums.add(float(int(mm)))
        extra = [r for v, _d, s, r in extract_numbers(ans) if round(v * s, 6) not in q_nums and v != 0]
        # fixed no_data sentence carries no numbers; anything else with numbers = invented
        ok_status = res.get("status") == "no_data" or (not extra and res.get("status") == "ok")
        halluc = bool(extra) and res.get("status") != "no_data"
        return {"correct": ok_status and not halluc, "hallucination": halluc, "invented": extra}
    exp = item["expected"]["value"]
    tol = float(item.get("tolerance") or 0.0)
    items = exp if isinstance(exp, list) else [exp]
    found = [_item_found(x, ans, tol) for x in items]
    return {"correct": all(found), "hallucination": False, "found": found}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(EVAL_DIR / "golden.jsonl"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="run only the first N questions")
    ap.add_argument("--provider", default="rules", help='AI_MODEL_CHAIN override, e.g. "rules" or "gemini:gemini-3-flash-preview"')
    args = ap.parse_args()
    items = [json.loads(line) for line in open(args.golden, encoding="utf-8") if line.strip()]
    if args.provider:
        import os

        os.environ["AI_MODEL_CHAIN"] = args.provider
    if args.ids:
        want = set(args.ids.split(","))
        items = [i for i in items if i["id"] in want]
    if args.limit:
        items = items[: args.limit]
    engine = AgentEngine(cache_path="")
    tag = args.tag or engine.sql_model
    sem = asyncio.Semaphore(args.concurrency)

    async def run(item):
        async with sem:
            t0 = time.monotonic()
            r = (await engine.ask(item["question"], "auto")).to_dict()
            r["wall_ms"] = int((time.monotonic() - t0) * 1000)
            g = grade(item, r)
            mark = "OK " if g["correct"] else "BAD"
            print(f"{mark} {item['id']:5} {r['status']:7} {r['wall_ms']:6}ms | {r['answer'][:110]!r}", flush=True)
            return {"id": item["id"], "category": item.get("category"), "kind": item["kind"], "lang": item["lang"],
                    "question": item["question"], "expected": item["expected"], **g, "result": r}

    out = await asyncio.gather(*(run(i) for i in items))
    n = len(out)
    exact = [o for o in out if o["kind"] == "exact"]
    nod = [o for o in out if o["kind"] == "no_data"]
    lat = sorted(o["result"]["wall_ms"] for o in out)
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0  # noqa: E731
    toks = [o["result"]["tokens"].get("total", 0) for o in out if o["result"]["tokens"]]
    by_cat: dict[str, list[int]] = {}
    for o in out:
        by_cat.setdefault(o["category"] or o["kind"], []).append(1 if o["correct"] else 0)
    summary = {
        "tag": tag,
        "n": n,
        "accuracy_all": round(sum(o["correct"] for o in out) / max(n, 1), 4),
        "exact_correct": f"{sum(o['correct'] for o in exact)}/{len(exact)}",
        "no_data_correct": f"{sum(o['correct'] for o in nod)}/{len(nod)}",
        "hallucinations": sum(o["hallucination"] for o in out),
        "errors": sum(o["result"]["status"] == "error" for o in out),
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_cat.items())},
        "latency_p50_ms": p(0.5),
        "latency_p95_ms": p(0.95),
        "latency_max_ms": lat[-1] if lat else 0,
        "avg_tokens": round(statistics.mean(toks)) if toks else 0,
        "failed_ids": [o["id"] for o in out if not o["correct"]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    EVAL_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", tag)
    path = EVAL_DIR / f"results_{safe}.json"
    path.write_text(json.dumps({"summary": summary, "results": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", path)


if __name__ == "__main__":
    asyncio.run(main())
