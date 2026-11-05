# AI Engine documentation

## Provider abstraction

`app/ai/providers/base.py` defines `BaseProvider` with `chat_completion()`. Concrete
providers: `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`, `MockProvider`.
Factory: `app/ai/providers/registry.py::create_provider()` reads `AI_PROVIDER`.

The engine depends only on `BaseProvider` — not bound to any single LLM provider.

## Grounding rule

The LLM is **not** a source of facts. Every factual claim comes from a read-only tool
querying PostgreSQL. The engine:

1. Selects tools via a deterministic intent router (`_IntentRouter`) based on user message.
2. Executes tools through `ToolRegistry` (read-only DB session).
3. Composes the answer from tool results via the LLM.
4. If no tool matches → answers honestly "I don't know" (RU/UZ exact wording).

## Read-only AI tools

All tools in `app/ai/tools/` have Pydantic input/output schemas, parameter validation,
error handling, result limits (`MAX_RESULT_ROWS = 1000`), and call logging.

Tools (22): search_deals, get_deal_details, search_contracts, get_contract_details,
search_brokers, get_broker_details, search_participants, get_participant_details,
get_broker_statistics, get_participant_statistics, get_deal_statistics,
get_product_statistics, get_region_statistics, get_industry_statistics, get_exchange_rate,
calculate_deal_volume, calculate_unit_price, calculate_amount_uzs, compare_periods,
get_top_brokers, get_top_products, get_dataset_information.

No arbitrary SQL execution by the AI.

## System prompt

`backend/app/ai/prompts/system_prompt.md` — Russian and Uzbek, strict anti-hallucination
rules, exact "I don't know" formulations.

## Formulas

- `volume = quantity * lot_size`
- `unit_price = amount / (quantity * lot_size)`
- `amount_uzs = amount * usd_rate` (rate looked up by deal date; if missing → `rate_available=false`)

## Evaluation

Separate from model training. Golden questions + expected answers/tool calls/DB results.
Runs produce accuracy, latency, token usage, and per-question pass/fail. Does not alter
model weights.
