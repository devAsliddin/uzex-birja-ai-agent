"""Smoke tests for the public Q&A agent (mocked LLM provider, fixture SQLite DB)."""

import json
import re

import pytest

from app.agent import engine as agent_engine
from app.agent.db import SQLValidationError, run_query, validate_sql
from app.agent.engine import AgentEngine, detect_language
from app.agent.grounding import check_grounding
from app.ai.providers.base import BaseProvider, LLMResponse


class FakeProvider(BaseProvider):
    """SQL calls return a fixed plan; answer calls echo the first cell or a scripted text."""

    def __init__(self, model, plan=None, answer=None):
        super().__init__(model)
        self.plan = plan or {"answerable": True, "sql": "SELECT COUNT(*) AS deals_count FROM v_deals", "basis": "all deals"}
        self.answer = answer
        self.calls = 0

    async def chat_completion(self, messages, **kwargs):
        self.calls += 1
        system = messages[0]["content"]
        if system.startswith("You translate"):
            return LLMResponse(json.dumps(self.plan), self.model, {"total_tokens": 10})
        if self.answer is not None:
            return LLMResponse(json.dumps({"no_data": False, "answer": self.answer}), self.model, {"total_tokens": 5})
        blob = re.search(r"<result_rows>\n(.*)\n</result_rows>", messages[1]["content"], re.S).group(1)
        first = json.loads(blob)["rows"][0][0]
        return LLMResponse(json.dumps({"no_data": False, "answer": f"Jami: {first} ta bitim."}), self.model, {"total_tokens": 5})

    async def close(self):
        pass


def make_engine(**kw):
    prov = FakeProvider("fake", **kw)
    return AgentEngine(provider_factory=lambda m: prov, sql_models=["fake"], answer_models=["fake"], cache_path=""), prov


def test_validate_sql_rejects_writes():
    for bad in ["DELETE FROM deals", "SELECT 1; DROP TABLE deals", "PRAGMA query_only=OFF",
                "ATTACH DATABASE 'x' AS y", "WITH a AS (SELECT 1) DELETE FROM deals", ""]:
        with pytest.raises(SQLValidationError):
            validate_sql(bad)
    assert validate_sql("SELECT 1 -- c\n;").startswith("SELECT 1")
    assert validate_sql("SELECT ';' AS s") == "SELECT ';' AS s"


def test_language_detection():
    assert detect_language("Сколько сделок в 2024 году?") == "ru"
    assert detect_language("2024-yilda nechta bitim bo‘lgan?") == "uz"
    assert detect_language("Тошкент шаҳрида нечта брокер бор?") == "uz"
    assert detect_language("x", "ru") == "ru"


def test_grounding_check():
    cols, rows = ["total_uzs"], [["42 724 135 079 483.66"], [42724135079483.664]]
    assert check_grounding("Оборот: 42 724 135 079 483.66 сум", cols, rows, "q") == []
    assert check_grounding("Оборот: 42.72 трлн сум", cols, rows, "q") == []
    assert check_grounding("Оборот: 51 000 сум", cols, rows, "q") == ["51 000"]
    assert check_grounding('Лидер «Fake LLC»', cols, rows, "q") == ["Fake LLC"]


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_ok_path(seeded):
    eng, _ = make_engine()
    r = await eng.ask("2024-yilda nechta bitim bo‘lgan?")
    assert r.status == "ok", r
    assert r.language == "uz"
    n = run_query("SELECT COUNT(*) FROM v_deals").rows[0][0]
    assert str(n) in r.answer.replace(" ", "")
    assert r.sql and r.columns == ["deals_count"] and r.basis


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_rejects_invented_numbers(seeded):
    eng, _ = make_engine(answer="Всего 987 654 321 сделок, лидер «Imaginary LLC».")
    r = await eng.ask("Сколько всего сделок?")
    assert r.status == "ok"
    assert "987" not in r.answer and "Imaginary" not in r.answer  # deterministic fallback from rows
    assert "deals_count" in r.answer


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_no_data_out_of_scope_without_llm(seeded):
    eng, prov = make_engine()
    r = await eng.ask("Какая погода в Ташкенте?")
    assert r.status == "no_data" and prov.calls == 0
    assert r.answer == agent_engine.NO_DATA["ru"]
    r2 = await eng.ask("2021-yilda nechta bitim bo'lgan?")
    assert r2.status == "no_data" and not re.search(r"\d", r2.answer)


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_no_data_on_empty_result(seeded):
    eng, _ = make_engine(plan={"answerable": True, "sql": "SELECT deal_no FROM deals WHERE deal_no = -1", "basis": "b"})
    r = await eng.ask("Сделка № -1?")
    assert r.status == "no_data" and r.answer == agent_engine.NO_DATA["ru"]
    eng2, _ = make_engine(plan={"answerable": False, "sql": "", "basis": ""})
    r2 = await eng2.ask("Kim direktor?")
    assert r2.status == "no_data" and r2.answer == agent_engine.NO_DATA["uz"]


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_retries_bad_sql_then_errors_cleanly(seeded):
    eng, prov = make_engine(plan={"answerable": True, "sql": "DELETE FROM deals", "basis": "b"})
    r = await eng.ask("Сколько сделок?")
    assert r.status == "no_data" and prov.calls == 3  # first plan + 2 fix attempts, then honest "don't know"
    assert r.answer == agent_engine.NO_DATA["ru"]


@pytest.mark.asyncio(loop_scope="session")
async def test_endpoint_public(client, monkeypatch):
    eng, _ = make_engine()
    monkeypatch.setattr("app.api.v1.endpoints.agent.get_agent", lambda: eng)
    r = await client.post("/api/v1/agent/ask", json={"question": "Сколько всего сделок?", "language": "auto"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["language"] == "ru" and body["sql"]
    r = await client.post("/api/v1/agent/ask", json={"question": "x" * 1001})
    assert r.status_code == 422


class ScriptedProvider(FakeProvider):
    """Returns plan per call from a list and records the SQL-step user prompts."""

    def __init__(self, model, plans):
        super().__init__(model)
        self.plans = list(plans)
        self.sql_prompts = []

    async def chat_completion(self, messages, **kwargs):
        if messages[0]["content"].startswith("You translate"):
            self.sql_prompts.append(messages[1]["content"])
            self.plan = self.plans.pop(0)
        return await super().chat_completion(messages, **kwargs)


def scripted(plans):
    prov = ScriptedProvider("fake", plans)
    return AgentEngine(provider_factory=lambda m: prov, sql_models=["fake"], answer_models=["fake"], cache_path=""), prov


@pytest.mark.asyncio(loop_scope="session")
async def test_followup_uses_conversation_sql(seeded):
    sql1 = "SELECT COUNT(*) AS deals_count FROM v_deals WHERE year = 2024"
    sql2 = "SELECT COUNT(*) AS deals_count FROM v_deals WHERE year = 2025"
    eng, prov = scripted([{"intent": "data", "answerable": True, "sql": sql1, "basis": "b"},
                          {"intent": "data", "answerable": True, "sql": sql2, "basis": "b"}])
    r1 = await eng.ask("Сколько сделок в 2024 году?")
    r2 = await eng.ask("а в 2025?", conversation_id=r1.conversation_id)
    assert r2.conversation_id == r1.conversation_id
    assert "<history>" in prov.sql_prompts[1] and sql1 in prov.sql_prompts[1]
    assert r2.sql == [sql2] and r2.status in ("ok", "no_data")


@pytest.mark.asyncio(loop_scope="session")
async def test_followup_with_client_history(seeded):
    eng, prov = scripted([{"intent": "data", "answerable": True, "sql": "SELECT COUNT(*) AS n FROM brokers", "basis": "b"}])
    hist = [{"role": "user", "content": "437067-sonli bitimda sotuvchi kim?"}, {"role": "assistant", "content": "Sotuvchi: X"}]
    await eng.ask("uning brokeri kim?", history=hist)
    assert "437067-sonli" in prov.sql_prompts[0] and "<history>" in prov.sql_prompts[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_smalltalk_has_no_numbers(seeded):
    eng, _ = scripted([{"intent": "smalltalk", "answerable": False, "sql": "", "basis": "",
                        "reply": "Salom! 2025-yilda 107 678 bitim bo'lgan."}])  # digits in reply must be dropped
    r = await eng.ask("Salom, sen kimsan?")  # static route: 0 LLM calls
    assert r.status == "ok" and not r.sql and agent_engine.HELP_TEXT["uz"] in r.answer
    assert "107" not in r.answer  # model-written reply with data facts is never used
    r2 = await eng.ask("Bitimlar haqida nimalarni bila olaman, qanday so'rash kerak?")  # LLM says smalltalk
    assert r2.status == "ok" and r2.answer == agent_engine.HELP_TEXT["uz"]


@pytest.mark.asyncio(loop_scope="session")
async def test_out_of_scope_intent(seeded):
    eng, _ = scripted([{"intent": "out_of_scope", "answerable": False, "sql": "", "basis": ""}])
    r = await eng.ask("Кто директор компании с ИНН 936085105?")
    assert r.status == "no_data" and r.answer == agent_engine.NO_DATA["ru"]


@pytest.mark.asyncio(loop_scope="session")
async def test_single_call_template_and_cache(seeded, tmp_path):
    plan = {"intent": "data", "answerable": True, "sql": "SELECT COUNT(*) AS deals_count FROM v_deals",
            "basis": "b", "answer_template": "Jami {deals_count} ta bitim tuzilgan. Yillar kesimida ko‘rsataymi?"}
    prov = FakeProvider("fake", plan=plan)
    eng = AgentEngine(provider_factory=lambda m: prov, sql_models=["fake"], answer_models=["fake"],
                      cache_path=str(tmp_path / "c.sqlite"))
    r = await eng.ask("Jami nechta bitim bor?")
    assert r.status == "ok" and prov.calls == 1  # one LLM call per data question
    n = run_query("SELECT COUNT(*) FROM v_deals").rows[0][0]
    assert str(n) in r.answer.replace(" ", "")
    r2 = await eng.ask("jami  nechta bitim bor?")
    assert prov.calls == 1 and r2.answer == r.answer and r2.tokens.get("cache_hit") == 1
    # template that references a missing column -> falls back to the answer call
    prov.plan = {**plan, "answer_template": "Jami {nonexistent} ta"}
    await eng.ask("Boshqa savol: jami nechta bitim?")
    assert prov.calls == 3


# ---------------------------------------------------------------------------
# rule-based engine (zero LLM calls) on the fixture DB
# ---------------------------------------------------------------------------
def rules_engine():
    import os

    os.environ["AI_MODEL_CHAIN"] = "rules"  # never reach a real LLM from tests
    return AgentEngine(cache_path="")  # default AI_MODEL_CHAIN = "rules"


@pytest.mark.asyncio(loop_scope="session")
async def test_rules_count_reports_all_and_valid(seeded):
    eng = rules_engine()
    total, valid = run_query("SELECT COUNT(*), SUM(is_valid) FROM v_deals WHERE year = 2022").rows[0]
    r = await eng.ask("2022-yilda nechta bitim tuzilgan?")
    assert r.status == "ok" and r.model.startswith("rules")
    flat = r.answer.replace(" ", "")
    assert str(total) in flat and str(valid or 0) in flat
    assert "is_valid" not in r.answer and "v_deals" not in r.answer


@pytest.mark.asyncio(loop_scope="session")
async def test_rules_followup_replaces_year(seeded):
    eng = rules_engine()
    r1 = await eng.ask("Сколько сделок было в 2022 году?")
    r2 = await eng.ask("а в 2023?", conversation_id=r1.conversation_id)
    assert r2.status == "ok" and "2023" in r2.sql[0] and "2022" not in r2.sql[0]
    r3 = await eng.ask("а в 2023?", history=[{"role": "user", "content": "Сколько сделок было в 2022 году?"}])
    assert r3.status == "ok" and "2023" in r3.sql[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_rules_unknown_ids_and_topics(seeded):
    eng = rules_engine()
    r = await eng.ask("BK999 brokerining aylanmasi qancha?")
    assert r.status == "no_data" and "BK999" in r.answer and not r.rows
    r = await eng.ask("Сколько сделок было в 2021 году?")
    assert r.status == "no_data" and r.answer.startswith(agent_engine.NO_DATA["ru"])
    for q in ["Birjada oltin bo‘yicha nechta bitim tuzilgan?", "Какой курс евро 15.06.2025?",
              "Кто директор компании с ИНН 936085105?"]:
        r = await eng.ask(q)
        assert r.status == "no_data", q
        assert not re.search(r"\d", r.answer.splitlines()[0]), q


@pytest.mark.asyncio(loop_scope="session")
async def test_rules_smalltalk_static(seeded):
    eng = rules_engine()
    r = await eng.ask("Привет! Что ты умеешь?")
    assert r.status == "ok" and r.model == "static" and agent_engine.HELP_TEXT["ru"] in r.answer
