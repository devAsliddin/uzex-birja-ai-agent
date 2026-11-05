"""Mini App: URL source (env vs tunnel file), menu button refresh, /start web_app button."""

from __future__ import annotations

from aiogram.methods import SendMessage, SetChatMenuButton

from app import webapp
from conftest import Harness


def test_clean_url():
    assert webapp.clean_url("https://abc.trycloudflare.com") == "https://abc.trycloudflare.com/"
    assert webapp.clean_url("  https://x.test/app/ \n") == "https://x.test/app/"
    for bad in ("", None, "http://x.test", "javascript:alert(1)", "https://", "https://a b.test", "x" * 600):
        assert webapp.clean_url(bad) is None


def test_file_wins_over_env(tmp_path):
    f = tmp_path / "webapp_url.txt"
    assert webapp.read_url("https://env.test", f) == "https://env.test/"  # no file yet
    f.write_text("https://tunnel.test\n", encoding="utf-8")
    assert webapp.read_url("https://env.test", f) == "https://tunnel.test/"
    f.write_text("garbage", encoding="utf-8")
    assert webapp.read_url("", f) is None


async def test_menu_button_set_once_and_on_change(tmp_path):
    hh = Harness()
    try:
        state = hh.dp["bot_state"]
        f = tmp_path / "u.txt"
        menu = lambda: [r for r in hh.session.requests if isinstance(r, SetChatMenuButton)]  # noqa: E731
        await webapp.refresh(hh.bot, state, "", f)
        assert menu() == [] and state.webapp_url is None  # no URL yet: silent
        f.write_text("https://one.test", encoding="utf-8")
        await webapp.refresh(hh.bot, state, "", f)
        await webapp.refresh(hh.bot, state, "", f)  # unchanged: no second call
        assert len(menu()) == 1
        assert menu()[0].menu_button.web_app.url == "https://one.test/" and menu()[0].chat_id is None
        f.write_text("https://two.test", encoding="utf-8")
        await webapp.refresh(hh.bot, state, "", f)
        assert len(menu()) == 2 and state.webapp_url == "https://two.test/"
    finally:
        await hh.close()


async def test_start_has_open_app_button():
    hh = Harness()
    try:
        out = [m for m in await hh.send("/start", chat_id=5, chat_type="private") if isinstance(m, SendMessage)]
        assert all(b.web_app is None for row in out[0].reply_markup.inline_keyboard for b in row)  # no URL yet
        hh.dp["bot_state"].webapp_url = "https://app.test/"
        out = [m for m in await hh.send("/start", chat_id=5, chat_type="private") if isinstance(m, SendMessage)]
        first = out[0].reply_markup.inline_keyboard[0][0]
        assert first.text.startswith("Ilovani ochish") and first.web_app.url == "https://app.test/"
        out = [m for m in await hh.send("/start") if isinstance(m, SendMessage)]  # group: plain link
        first = out[0].reply_markup.inline_keyboard[0][0]
        assert first.web_app is None and first.url == "https://app.test/"
    finally:
        await hh.close()
