"""Base class for read-only AI tools.

Every tool declares Pydantic input/output schemas, validates parameters,
limits result size, handles errors, and logs its calls.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)

MAX_RESULT_ROWS = 1000


class ToolError(Exception):
    """Raised when a tool cannot complete."""


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    tool: str
    latency_ms: int | None = None


class BaseTool(ABC, Generic[InputT, OutputT]):
    name: str
    description: str
    input_schema: type[InputT]
    output_schema: type[OutputT]

    def __init__(self) -> None:
        self._log = logging.getLogger(f"uzex_ai.tools.{self.name}")

    @abstractmethod
    async def _run(self, db: AsyncSession, input_data: InputT) -> OutputT:
        raise NotImplementedError

    async def execute(self, db: AsyncSession, raw_input: dict[str, Any]) -> ToolResult:
        start = time.time()
        try:
            input_data = self.input_schema.model_validate(raw_input)
        except ValidationError as exc:
            self._log.warning("Tool %s invalid input: %s", self.name, exc)
            return ToolResult(
                ok=False,
                error=f"Неверные параметры: {exc}",
                tool=self.name,
                latency_ms=int((time.time() - start) * 1000),
            )
        try:
            output = await self._run(db, input_data)
            data = output.model_dump()
            self._log.info("Tool %s executed ok", self.name)
            return ToolResult(
                ok=True,
                data=data,
                tool=self.name,
                latency_ms=int((time.time() - start) * 1000),
            )
        except ToolError as exc:
            self._log.warning("Tool %s error: %s", self.name, exc)
            return ToolResult(
                ok=False,
                error=str(exc),
                tool=self.name,
                latency_ms=int((time.time() - start) * 1000),
            )
        except Exception as exc:
            self._log.exception("Tool %s unexpected error", self.name)
            return ToolResult(
                ok=False,
                error=f"Внутренняя ошибка инструмента: {exc}",
                tool=self.name,
                latency_ms=int((time.time() - start) * 1000),
            )
