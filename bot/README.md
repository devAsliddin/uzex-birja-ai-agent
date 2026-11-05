# Birja reyestri — Telegram bot

Telegram bot over the FastAPI backend (`/api/v1`). Command answers come straight from the backend API
(SQL aggregates) — no LLM. Only free-text questions go to `/ai/chat`, and only when `BACKEND_API_KEY` is set and that endpoint works.

## Commands

| Command | What it returns |
|---|---|
| `/summary [yil]` | total turnover (so'm + USD), deal count, average deal, USD rate, top 3 regions, top 3 categories |
| `/deal <raqam>` | deal card: amount so'm + USD, status, product, volume, date, seller/buyer (STIR), brokers, contract, payment/delivery |
| `/broker <BK001>` | rank N/120, deals, turnover, region, seller/buyer side split, average deal, status breakdown |
| `/top_brokers [yil]` | top 10 brokers by turnover (see the note below about the year) |
| `/export <DD.MM.YYYY> <DD.MM.YYYY> [holat] [xlsx]` | CSV (default) or Excel file from `/export/deals` |
| `/help`, `/start` | the command list |
| `/chatid` | this chat's ID (also works in chats that are not allowed yet; used during setup) |

Statuses for `/export`: `yangi, imzolanmagan, tuzilgan, kutilmoqda, tolangan, bajarilgan, qisman, bekor`
(the Russian status names work too).
Export limits: up to `EXPORT_MAX_ROWS` rows (default 20 000; the bot asks `/deals` for the row count first),
45 MB per file, one export every 30 s per chat.

Year note: `/brokers` has no year filter in the backend. The bot sends `year` anyway. If the backend does not
echo that year back, the answer says "barcha yillar" and adds a note.

Reply format: the first line is the direct answer, followed by short detail lines. No emoji and no greetings.

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

### 2. Create the test group and add the bot
1. In Telegram, create a new group (for example "Birja test"). Add your bot as a member.
2. Start the bot (`run_bot.ps1`). It runs even when `ALLOWED_CHAT_IDS` is empty, but then only `/chatid` works.
3. In the group, send `/chatid@<your_bot_username>`. The bot replies `Chat ID: -100xxxxxxxxxx (supergroup).`
4. Put that ID into `bot\.env`: `ALLOWED_CHAT_IDS=-100xxxxxxxxxx`. Separate several IDs with commas.
5. Restart the bot, then send `/summary 2025` in the group.

### .env keys

| Key | Meaning |
|---|---|
| `BOT_TOKEN` | token from @BotFather (required; the bot exits with a clear message if it is missing or malformed) |
| `BACKEND_URL` | FastAPI base URL, default `http://127.0.0.1:8000/api/v1` |
| `ALLOWED_CHAT_IDS` | comma-separated chat IDs that are served; all other chats are refused |
| `BACKEND_API_KEY` | `X-API-Key` sent only on `/ai/chat` (backend requires JWT/API key there). Empty: free text gets the command list, no AI call |
| `RATE_LIMIT_PER_MIN` | addressed messages per chat per minute (default 20) |
| `EXPORT_MAX_ROWS` | maximum rows per export (default 20 000) |

## Group behaviour
- Commands work as `/cmd` and as `/cmd@botname`.
- In groups, the bot answers free text only when it is @mentioned or when someone replies to one of its
  messages. Other group messages are ignored. In a private chat (if that chat is allowed), every message is
  treated as addressed to the bot.
- Free text goes to `/ai/chat` as the plain `message` field: the user's text is data, and the bot adds no
  instructions of its own. Control characters are stripped, and the text is cut to 500 characters. If
  `/ai/chat` fails, the bot replies with the command list and does not retry for 5 minutes.

## Security
- Only `ALLOWED_CHAT_IDS` are served. Any other chat gets one short refusal per minute that shows its chat ID,
  for setup. No backend call is made for such chats. Logs record a hashed chat reference, never names or texts.
- Input is validated before any backend call: deal number `^\d{1,12}$`, broker `^BK\d{3}$`, year `20xx`,
  dates `DD.MM.YYYY` (real calendar dates, start <= end), status from a whitelist.
- Per-chat sliding-window rate limit, plus a 30 s export cooldown that is reserved before any await, so there
  are no races.
- Backend errors (network, 5xx, bad JSON) produce one generic message, with no stack traces or URLs. The token
  is never printed or logged: httpx INFO logging is off, and startup errors show only the exception type.
- Replies are plain text (`parse_mode=None`), so backend or AI text cannot inject HTML or Markdown.
- `.env` and `.venv` are git-ignored. `.env.example` contains only fake values.

## Agent layout
**One bot process. No separate orchestrator is needed.** The bot is a single agent: command, then backend
API, then formatted text. Every command maps directly to one REST endpoint (or two parallel calls for
`/summary`), so there is nothing to route or plan. The only "intelligent" path is free text, and the backend's
AI engine (`/ai/chat`) already does tool calling there. Adding an orchestrator or more agents would add
latency and tokens and would duplicate that engine's work. If the group later needs distinct capabilities
(for example scheduled reports), add them as handlers in this same process.

## Tests
`tests/test_smoke.py` checks the exact format of each command, validation, 404s, group mention/reply rules,
AI-down fallback, unauthorized chats, the rate limit and the generic backend error. `tests/test_stress.py`
runs 200 and 2000 concurrent updates through the real dispatcher with a mocked backend (20 ms latency),
including garbage input. It also checks a 300-message flood from one chat and 20 concurrent exports.
`tests/test_live.py` sends the commands through the dispatcher to the real backend (read-only calls). It is
skipped unless `LIVE_BACKEND` is set:
`$env:LIVE_BACKEND="http://127.0.0.1:8000/api/v1"; .venv\Scripts\python -m pytest tests/test_live.py -s`.
