"""Evaluation system schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluationQuestionCreate(BaseModel):
    question: str
    language: str = "ru"
    expected_answer: str | None = None
    expected_tool_calls: list[dict[str, Any]] | None = None
    expected_db_result: Any | None = None
    category: str | None = None
    is_unknown: bool = False
    difficulty: str | None = None


class EvaluationQuestionOut(EvaluationQuestionCreate):
    id: int
    dataset_id: int

    model_config = ConfigDict(from_attributes=True)


class EvaluationDatasetCreate(BaseModel):
    name: str
    description: str | None = None


class EvaluationDatasetOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunCreate(BaseModel):
    name: str
    model: str
    prompt_version_id: int | None = None


class EvaluationRunOut(BaseModel):
    id: int
    name: str
    model: str
    status: str
    summary: Any | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationResultOut(BaseModel):
    id: int
    question_id: int
    passed: bool
    scores: Any | None = None
    errors: Any | None = None
    latency_ms: int | None = None
    token_usage: Any | None = None

    model_config = ConfigDict(from_attributes=True)


class PromptVersionCreate(BaseModel):
    version: str
    content: str
    is_active: bool = False
    created_by: str | None = None


class PromptVersionOut(BaseModel):
    id: int
    version: str
    is_active: bool
    created_at: datetime
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)
