"""Tool registry — maps tool names to tool instances."""

from typing import Any

from app.ai.tools.base import BaseTool
from app.ai.tools.brokers import (
    GetBrokerDetails,
    GetBrokerStatistics,
    GetTopBrokersTool,
    SearchBrokers,
)
from app.ai.tools.calculations import (
    CalculateAmountUzs,
    CalculateDealVolume,
    CalculateUnitPrice,
)
from app.ai.tools.compare import ComparePeriods
from app.ai.tools.contracts import GetContractDetails, SearchContracts
from app.ai.tools.dataset import GetDatasetInformation
from app.ai.tools.deals import GetDealDetails, SearchDeals
from app.ai.tools.exchange_rates import GetExchangeRate
from app.ai.tools.participants import (
    GetParticipantDetails,
    GetParticipantStatistics,
    SearchParticipants,
)
from app.ai.tools.statistics import (
    GetDealStatistics,
    GetIndustryStatistics,
    GetProductStatistics,
    GetRegionStatistics,
    GetTopProductsTool,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._register()

    def _register(self) -> None:
        tools: list[BaseTool] = [
            SearchDeals(),
            GetDealDetails(),
            SearchContracts(),
            GetContractDetails(),
            SearchBrokers(),
            GetBrokerDetails(),
            SearchParticipants(),
            GetParticipantDetails(),
            GetBrokerStatistics(),
            GetParticipantStatistics(),
            GetDealStatistics(),
            GetProductStatistics(),
            GetRegionStatistics(),
            GetIndustryStatistics(),
            GetExchangeRate(),
            CalculateDealVolume(),
            CalculateUnitPrice(),
            CalculateAmountUzs(),
            ComparePeriods(),
            GetTopBrokersTool(),
            GetTopProductsTool(),
            GetDatasetInformation(),
        ]
        for tool in tools:
            self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def schemas(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "description": tool.description,
                "input_schema": tool.input_schema.model_json_schema(),
            }
            for name, tool in self._tools.items()
        }
