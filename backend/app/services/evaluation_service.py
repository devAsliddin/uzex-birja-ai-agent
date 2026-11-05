"""AI evaluation service.

Runs golden-question tests against the AI engine and records results.
Not automatic model training — just quality measurement and comparison.
"""

import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.engine import AIEngine
from app.crud import (
    crud_evaluation_dataset,
    crud_evaluation_question,
    crud_evaluation_result,
    crud_evaluation_run,
)
from app.db.models.prompt_version import PromptVersion


class EvaluationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_dataset(self, name: str, description: str | None = None):
        existing = await crud_evaluation_dataset.get_by_name(self.db, name=name)
        if existing:
            raise ValueError("Dataset already exists")
        return await crud_evaluation_dataset.create(
            self.db,
            obj_in={"name": name, "description": description},
        )

    async def add_question(
        self,
        dataset_id: int,
        question: str,
        language: str = "ru",
        expected_answer: str | None = None,
        expected_tool_calls: list | None = None,
        expected_db_result: Any | None = None,
        category: str | None = None,
        is_unknown: bool = False,
        difficulty: str | None = None,
    ):
        return await crud_evaluation_question.create(
            self.db,
            obj_in={
                "dataset_id": dataset_id,
                "question": question,
                "language": language,
                "expected_answer": expected_answer,
                "expected_tool_calls": json.dumps(expected_tool_calls or [], default=str),
                "expected_db_result": json.dumps(expected_db_result, default=str) if expected_db_result is not None else None,
                "category": category,
                "is_unknown": is_unknown,
                "difficulty": difficulty,
            },
        )

    async def run_evaluation(
        self,
        name: str,
        model: str,
        dataset_id: int,
        prompt_version_id: int | None = None,
    ) -> dict[str, Any]:
        engine = AIEngine()
        run = await crud_evaluation_run.create(
            self.db,
            obj_in={
                "name": name,
                "model": model,
                "prompt_version_id": prompt_version_id,
                "status": "running",
            },
        )
        questions = await crud_evaluation_question.get_multi_by_dataset(self.db, dataset_id=dataset_id)
        results = []
        passed = 0
        total_latency = 0
        total_tokens = 0
        try:
            for q in questions:
                t0 = time.time()
                try:
                    result = await engine.process_message(
                        q.question,
                        language=q.language or "ru",
                    )
                    latency = int((time.time() - t0) * 1000)
                    total_latency += latency
                    token_usage = result.get("token_usage", {}) if isinstance(result.get("token_usage"), dict) else {}
                    total_tokens += token_usage.get("total_tokens", 0)

                    # Evaluation logic
                    is_passed = self._evaluate(q, result)
                    if is_passed:
                        passed += 1
                    scores = {"factual_accuracy": 1.0 if is_passed else 0.0}
                    await crud_evaluation_result.create(
                        self.db,
                        obj_in={
                            "run_id": run.id,
                            "question_id": q.id,
                            "actual_answer": result.get("response"),
                            "actual_tool_calls": json.dumps(result.get("tool_calls", []), default=str),
                            "actual_db_result": json.dumps(result.get("tool_results", []), default=str),
                            "passed": is_passed,
                            "scores": json.dumps(scores, default=str),
                            "errors": None,
                            "latency_ms": latency,
                            "token_usage": json.dumps(token_usage, default=str),
                        },
                    )
                    results.append(
                        {
                            "question_id": q.id,
                            "question": q.question,
                            "passed": is_passed,
                            "latency_ms": latency,
                            "answer": result.get("response"),
                        }
                    )
                except Exception as exc:
                    await crud_evaluation_result.create(
                        self.db,
                        obj_in={
                            "run_id": run.id,
                            "question_id": q.id,
                            "actual_answer": None,
                            "actual_tool_calls": None,
                            "actual_db_result": None,
                            "passed": False,
                            "scores": None,
                            "errors": json.dumps({"error": str(exc)}, default=str),
                            "latency_ms": int((time.time() - t0) * 1000),
                            "token_usage": None,
                        },
                    )
                    results.append({"question_id": q.id, "question": q.question, "passed": False, "error": str(exc)})
        finally:
            await engine.close()

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        summary = {
            "total": len(questions),
            "passed": passed,
            "failed": len(questions) - passed,
            "accuracy": round(passed / len(questions), 3) if questions else 0.0,
            "avg_latency_ms": round(total_latency / len(questions), 1) if questions else 0,
            "total_tokens": total_tokens,
        }
        run.summary = json.dumps(summary, default=str)
        await self.db.commit()
        await self.db.refresh(run)
        return {"run_id": run.id, "summary": summary, "results": results}

    @staticmethod
    def _evaluate(question, result) -> bool:
        """Simple evaluation: unknown questions should produce 'не знаю' style answers;
        known questions should produce a non-empty answer with tool calls."""
        answer = (result.get("response") or "").strip()
        if not answer:
            return False
        if question.is_unknown:
            return "не знаю" in answer.lower() or "bilmayman" in answer.lower()
        return bool(result.get("tool_calls")) and len(answer) > 0

    async def list_runs(self, skip: int = 0, limit: int = 100):
        return await crud_evaluation_run.get_multi(self.db, skip=skip, limit=limit)

    async def get_run_results(self, run_id: int, skip: int = 0, limit: int = 100):
        return await crud_evaluation_result.get_multi_by_run(self.db, run_id=run_id, skip=skip, limit=limit)

    async def list_prompt_versions(self, skip: int = 0, limit: int = 100):
        from sqlalchemy import select
        res = await self.db.execute(select(PromptVersion).order_by(PromptVersion.created_at.desc()).offset(skip).limit(limit))
        return res.scalars().all()

