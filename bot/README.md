# Birja reyestri — Telegram AI assistant

Public Telegram bot over the FastAPI backend (`/api/v1`). Anyone can open it (jury: no install, no registration):
private chats and groups, no admins, no allow-list. Every user is equal; abuse protection = per-user rate limits
plus a global concurrency cap.

## How it answers
- Any free-text message (private chat; in groups when the bot is @mentioned or replied to) goes to
  `POST /agent/ask` as `{"question", "language": "auto", "history": [...]}`. Greetings and thanks go there too:
  the agent handles smalltalk itself.
- History: the last 6 question/answer turns per chat and per user are kept in memory and sent with each
  question, so follow-ups work ("а в 2025?", "uning brokeri kim?"). `/new` starts a fresh conversation.
- While waiting, the bot shows "typing…" (re-sent every 4 s). Total limit 80 s (including queueing),
  then a short apology in the question's language.
- Reply (HTML, every dynamic value escaped with `html.escape`): the answer as normal chat text, then a
  collapsed `<blockquote expandable>` "Manba / Источник · N ta qator / N строк" with the basis, the SQL
  (cut at 1500 chars) and, for at most 5 rows, the result rows. Telegram does not allow `pre`/`code`
  inside a blockquote, so the SQL there is plain text. If Telegram rejects the HTML, the same text is resent
  without markup. Labels follow the answer language (ru/uz).
- `status: "no_data"` answers ("Bilmayman — ...", "Не знаю — ...") are shown exactly as returned, with no source
  block. `status: "error"`, HTTP errors and timeouts produce a short localized apology (never backend text).
- `/start`: a short intro in Uzbek and Russian plus 3 example questions as inline buttons; tapping one asks it.

## Commands (secondary)

| Command | What it returns |
|---|---|
| `/new` | reset the conversation history |
| `/summary [yil]` | total turnover (so'm + USD), deal count, average deal, USD rate, top 3 regions, top 3 categories |
| `/deal <raqam>` | deal card: amount so'm + USD, status, product, volume, date, seller/buyer (STIR), brokers, contract, payment/delivery |
| `/broker <BK001>` | rank N/120, deals, turnover, region, seller/buyer side split, average deal, status breakdown |
| `/top_brokers [yil]` | top 10 brokers by turnover |
| `/export <DD.MM.YYYY> <DD.MM.YYYY> [holat] [xlsx]` | CSV (default) or Excel file from `/export/deals` |
| `/help` | the command list |

Statuses for `/export`: `yangi, imzolanmagan, tuzilgan, kutilmoqda, tolangan, bajarilgan, qisman, bekor`
(the Russian status names work too). Export limits: up to `EXPORT_MAX_ROWS` rows (default 20 000), 45 MB per
file, one export every 30 s per chat.

## Setup (Windows, no Docker)

```powershell
cd C:\Users\f1n\Desktop\hakaton
copy bot\.env.example bot\.env      # then edit bot\.env
powershell -ExecutionPolicy Bypass -File .\run_bot.ps1          # start the bot
powershell -ExecutionPolicy Bypass -File .\run_bot.ps1 -Test    # smoke + stress tests
```

Manual setup: `cd bot; py -3 -m venv .venv; .venv\Scripts\pip install -r requirements.txt; .venv\Scripts\python -m app.main`.
The backend must be running at `BACKEND_URL` (default `http://127.0.0.1:8000/api/v1`).

### 1. Create the bot
1. Open @BotFather in Telegram and send `/newbot`. Choose a name and a username ending in `bot`.
2. Copy the token into `bot\.env` as `BOT_TOKEN=...`. Keep it out of git, chats and screenshots.
3. Optional: to let the bot see replies and @mentions only (recommended), leave the default
   `/setprivacy` = Enabled. Commands, @mentions and replies to the bot still reach it.

### 2. Test group
Create a Telegram group, add the bot, and talk to it with @mention or by replying to its messages.
No chat IDs need to be configured.

### .env keys

| Key | Meaning |
|---|---|
| `BOT_TOKEN` | token from @BotFather (required; the bot exits with a clear message if it is missing or malformed) |
| `BACKEND_URL` | FastAPI base URL, default `http://127.0.0.1:8000/api/v1` |
| `RATE_LIMIT_PER_MIN` | addressed messages + button taps per user per minute (default 10) |
| `RATE_LIMIT_PER_DAY` | per user per 24 h (default 200) |
| `AGENT_CONCURRENCY` | simultaneous `/agent/ask` calls; the rest wait in a queue (default 20) |
| `AGENT_TIMEOUT` | seconds per question including queueing (default 80; the jury limit is 90) |
| `EXPORT_MAX_ROWS` | maximum rows per export (default 20 000) |

## Group behaviour
- Commands work as `/cmd` and as `/cmd@botname`.
- In groups the bot answers free text only when @mentioned or replied to, and threads its answer to the
  question. Other group messages are ignored. In a private chat every message is for the bot.

## Security
- Public by design: no allow-list, no admin commands. Limits: per-user sliding windows (minute + day),
  global concurrency semaphore, 500-char question cap, control characters stripped.
- The question and history are sent as JSON data fields; the bot adds no instructions of its own.
- Logs contain a hashed chat reference, status and latency only; never names, question text or the token.
- All agent output is HTML-escaped before sending; backend error text is never shown.
- Command input is validated before any backend call (deal number, broker code, year, dates, status whitelist).
- `.env` and `.venv` are git-ignored; `.env.example` contains only fake values.

## Agent layout
One bot process, no orchestrator. The intelligence lives in the backend agent (`/agent/ask`: text-to-SQL with
verification). The bot only routes text, keeps short history, and formats the answer with its source.

## Tests
`tests/test_smoke.py` (mocked backend): answer + source format, HTML escaping, 4096-char limit, no_data shown
as-is, error/HTTP 500/timeout apologies, history follow-ups and `/new`, greetings go to the agent, `/start`
buttons, group mention/reply rules, any chat served, per-user minute/day limits (messages and buttons),
concurrency cap, plus every command's format. `tests/test_stress.py`: 200 and 2000 concurrent mixed updates,
a 300-message flood, 20 concurrent exports, and 100 concurrent agent questions with 2 s mocked latency
(p50/p95 printed with `-s`). `tests/test_live.py` runs against a real backend when `LIVE_BACKEND` is set.
