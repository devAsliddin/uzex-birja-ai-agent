"use client";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ask, ApiError, type AgentAnswer, type AgentCell, type AgentLang, type AgentTurn } from "@/lib/api";
import { fmtInt, fmtMoney } from "@/lib/format";
import Markdown from "@/components/Markdown";

const EXAMPLES: { lang: AgentLang; tag: string; q: string }[] = [
  { lang: "uz", tag: "Soni", q: "2025-yilda jami nechta bitim tuzilgan?" },
  { lang: "uz", tag: "Reyting", q: "2024-yilda aylanma bo'yicha eng yirik broker kim?" },
  { lang: "uz", tag: "Bitim", q: "Eng katta summali bitim qaysi va sotuvchisi kim?" },
  { lang: "ru", tag: "Регион", q: "Какой регион лидирует по обороту в 2025 году?" },
  { lang: "ru", tag: "Статус", q: "Сколько сделок было аннулировано в 2022 году?" },
  { lang: "ru", tag: "Курс", q: "Какой был курс доллара 1 марта 2024 года?" },
];

const MAX_LEN = 500;
const HISTORY_TURNS = 6;
const STORE_KEY = "uzex-chat-v1";
const STORE_MAX = 60;

const T = {
  uz: {
    source: "Manba", basis: "Asos", sql: "SQL so'rov", result: "Natija", copy: "Nusxa", copied: "Nusxalandi",
    rows: (n: number) => `${fmtInt(n)} ta qator`, firstN: (k: number) => `birinchi ${k} tasi`,
    no_data: "Ma'lumot yo'q", error: "Xatolik", thinking: "o'ylayapti",
    failed: "Agent javob bermadi. Qayta urinib ko'ring.", timeout: "Javob 85 soniyada tayyor bo'lmadi. Savolni soddaroq qilib qayta yuboring.",
    errorAnswer: "Savolni qayta ishlab bo'lmadi. Savolni boshqacha ifodalab ko'ring.", retry: "Qayta urinish", noSql: "SQL so'rov qaytmadi.",
    copyAnswer: "Javobni nusxalash",
  },
  ru: {
    source: "Источник", basis: "Основание", sql: "SQL-запрос", result: "Результат", copy: "Копировать", copied: "Скопировано",
    rows: (n: number) => `${fmtInt(n)} ${ruRows(n)}`, firstN: (k: number) => `первые ${k}`,
    no_data: "Нет данных", error: "Ошибка", thinking: "думает",
    failed: "Агент не ответил. Попробуйте ещё раз.", timeout: "Ответ не был готов за 85 секунд. Попробуйте задать вопрос проще.",
    errorAnswer: "Не удалось обработать вопрос. Попробуйте переформулировать.", retry: "Повторить", noSql: "SQL-запрос не вернулся.",
    copyAnswer: "Копировать ответ",
  },
} as const;

function ruRows(n: number): string {
  const a = n % 10, b = n % 100;
  if (a === 1 && b !== 11) return "строка";
  if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return "строки";
  return "строк";
}

/** ru for Cyrillic without Uzbek-specific letters, else uz (same rule as the Telegram bot). */
function detectLang(s: string): AgentLang {
  if (/[ўқғҳЎҚҒҲ]/.test(s)) return "uz";
  const cyr = (s.match(/[Ѐ-ӿ]/g) ?? []).length;
  const lat = (s.match(/[A-Za-z]/g) ?? []).length;
  return cyr > lat ? "ru" : "uz";
}

const STATUS_COLOR = { ok: "#12805C", no_data: "#6B7685", error: "#B42318" } as const;

function cell(v: AgentCell): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? fmtInt(v) : fmtMoney(v);
  return String(v);
}

type Msg = {
  id: number;
  q: string;
  lang: AgentLang;
  startedAt: number;
  state: "pending" | "done" | "failed";
  res?: AgentAnswer;
  failure?: "timeout" | "failed";
  seconds?: number;
};

function loadStored(): Msg[] {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as Msg[];
    if (!Array.isArray(arr)) return [];
    // an answer that was still pending when the page closed is shown as failed (with retry)
    return arr
      .filter((m) => m && typeof m.q === "string" && typeof m.id === "number")
      .map((m) => (m.state === "pending" ? { ...m, state: "failed" as const, failure: "failed" as const } : m));
  } catch {
    return [];
  }
}

function saveStored(msgs: Msg[]) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(msgs.filter((m) => m.state !== "pending").slice(-STORE_MAX)));
  } catch { /* private mode / quota: chat still works without persistence */ }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

// ---------------------------------------------------------------------------
function CopyButton({ text, label, done, dark = false }: { text: string; label: string; done: string; dark?: boolean }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" aria-live="polite" onClick={async () => { await copyText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}
      className={`h-7 px-2 rounded-md text-[12px] font-medium inline-flex items-center gap-1.5 ${dark ? "text-white/75 hover:text-white hover:bg-white/10" : "text-ink-3 hover:text-ink hover:bg-[#EBEDF0]"}`}>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        {ok ? <path d="m3 8.5 3 3 7-7" /> : <><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" /><path d="M10.5 5V3.5A1.5 1.5 0 0 0 9 2H3.5A1.5 1.5 0 0 0 2 3.5V9A1.5 1.5 0 0 0 3.5 10.5H5" /></>}
      </svg>
      {ok ? done : label}
    </button>
  );
}

function ResultTable({ columns, rows }: { columns: string[]; rows: AgentCell[][] }) {
  const n = Math.max(columns.length, ...rows.map((r) => r.length));
  const cols = Array.from({ length: n }, (_, i) => columns[i] ?? `#${i + 1}`);
  const numeric = cols.map((_, i) => rows.length > 0 && rows.every((r) => r[i] === null || typeof r[i] === "number"));
  return (
    <div className="border border-line rounded-lg overflow-auto max-h-[360px]">
      <table className="reg w-full border-collapse">
        <thead className="sticky top-0"><tr>{cols.map((c, i) => <th key={i} className={numeric[i] ? "!text-right" : ""}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {cols.map((_, ci) => <td key={ci} className={numeric[ci] ? "num text-right" : "max-w-[280px] truncate"} title={typeof r[ci] === "string" ? String(r[ci]) : undefined}>{cell(r[ci])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcePanel({ res }: { res: AgentAnswer }) {
  const L = T[res.language];
  const [open, setOpen] = useState(false);
  const sql = res.sql.join(";\n\n");
  const shown = res.rows.length;
  return (
    <div className="card overflow-hidden mt-3">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-[#F8F9FB]">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-brand shrink-0" aria-hidden="true"><ellipse cx="8" cy="3.5" rx="5.5" ry="2" /><path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" /></svg>
        <span className="text-[13px] font-semibold text-brand">{L.source}</span>
        <span className="text-[12.5px] text-ink-3 num truncate">· {L.rows(res.row_count)}{res.basis ? ` · ${res.basis}` : ""}</span>
        <svg className={`ml-auto shrink-0 text-ink-3 transition-transform ${open ? "rotate-180" : ""}`} width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
      </button>
      {open && (
        <div className="px-3.5 pt-3 pb-4 space-y-4 border-t border-line">
          {res.basis && (
            <div>
              <div className="eyebrow mb-1">{L.basis}</div>
              <p className="text-[13.5px] text-ink-2 whitespace-pre-wrap break-words">{res.basis}</p>
            </div>
          )}
          <div>
            <div className="eyebrow mb-1">{L.sql}</div>
            {sql ? (
              <div className="rounded-lg bg-[#0F1E38] overflow-hidden">
                <div className="flex items-center justify-between pl-3 pr-1 h-9 border-b border-white/10">
                  <span className="font-mono text-[11.5px] text-white/50">SQL</span>
                  <CopyButton text={sql} label={L.copy} done={L.copied} dark />
                </div>
                <pre className="font-mono text-[12.5px] leading-[1.6] text-[#E6ECF7] p-3 overflow-auto whitespace-pre-wrap break-words max-h-[300px]">{sql}</pre>
              </div>
            ) : <p className="text-[13px] text-ink-3">{L.noSql}</p>}
          </div>
          {shown > 0 && (
            <div>
              <div className="flex items-baseline justify-between gap-3 mb-1">
                <div className="eyebrow">{L.result}</div>
                <div className="text-[12px] text-ink-3 num">{L.rows(res.row_count)}{res.row_count > shown ? ` · ${L.firstN(shown)}` : ""}</div>
              </div>
              <ResultTable columns={res.columns} rows={res.rows} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Avatar() {
  return <div className="w-8 h-8 shrink-0 rounded-full bg-brand text-white grid place-items-center text-[11px] font-semibold select-none" aria-hidden="true">AI</div>;
}

function AssistantRow({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <Avatar />
      <div className="flex-1 min-w-0 pt-1">{children}</div>
    </div>
  );
}

function Thinking({ m }: { m: Msg }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(t); }, []);
  const s = Math.max(0, Math.floor((now - m.startedAt) / 1000));
  return (
    <div className="inline-flex items-center gap-2.5 h-8 text-[14px] text-ink-3" role="status" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 160, 320].map((d) => <span key={d} className="w-1.5 h-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
      </span>
      <span>{T[m.lang].thinking}…</span>
      <span className="font-mono text-[12.5px] num">{s}s</span>
    </div>
  );
}

function Answer({ m, last, onRetry, onAsk, busy }: { m: Msg; last: boolean; onRetry: () => void; onAsk: (q: string) => void; busy: boolean }) {
  const lang = m.res?.language ?? m.lang;
  const L = T[lang];
  if (m.state === "pending") return <AssistantRow><Thinking m={m} /></AssistantRow>;
  if (m.state === "failed" || !m.res) {
    return (
      <AssistantRow>
        <div className="flex flex-wrap items-center gap-2.5" role="alert">
          <span className="badge" style={{ ["--c" as string]: STATUS_COLOR.error }}>{L.error}</span>
          <span className="text-[14px] text-ink-2">{m.failure === "timeout" ? L.timeout : L.failed}</span>
          <button type="button" className="btn !h-8 !px-3" onClick={onRetry} disabled={busy}>{L.retry}</button>
        </div>
      </AssistantRow>
    );
  }
  const r = m.res;
  const text = r.status === "error" ? L.errorAnswer : r.answer || (r.status === "no_data" ? L.no_data : L.errorAnswer);
  const hasSource = r.status === "ok" && (r.sql.length > 0 || !!r.basis || r.rows.length > 0);
  return (
    <AssistantRow>
      <div className={`text-[15px] leading-[1.65] break-words ${r.status === "ok" ? "text-ink" : "text-ink-2"}`}><Markdown text={text} /></div>
      <div className="mt-1.5 -ml-2 flex flex-wrap items-center gap-1 text-[12px] text-ink-3">
        <CopyButton text={text} label={L.copyAnswer} done={L.copied} />
        {r.status !== "ok" && <span className="badge !text-[11.5px] ml-1" style={{ ["--c" as string]: STATUS_COLOR[r.status] }}>{L[r.status]}</span>}
        {r.status === "error" && <button type="button" className="h-7 px-2 rounded-md hover:bg-[#EBEDF0] text-ink-2" onClick={onRetry} disabled={busy}>{L.retry}</button>}
        {m.seconds !== undefined && <span className="num ml-1" title={r.model || undefined}>{m.seconds.toFixed(1).replace(".", ",")} s</span>}
      </div>
      {hasSource && <SourcePanel res={r} />}
      {last && r.suggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {r.suggestions.map((s) => (
            <button key={s} type="button" disabled={busy} onClick={() => onAsk(s)}
              className="text-left rounded-full border border-line bg-white px-3 py-1.5 text-[13px] text-ink-2 hover:border-brand hover:text-ink disabled:opacity-50">{s}</button>
          ))}
        </div>
      )}
    </AssistantRow>
  );
}

// ---------------------------------------------------------------------------
export default function ChatPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [input, setInput] = useState("");
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const ctrl = useRef<AbortController | null>(null);
  const msgsRef = useRef<Msg[]>([]);
  msgsRef.current = msgs;
  const pending = msgs.some((m) => m.state === "pending");

  // restore the conversation (client only, after hydration)
  useEffect(() => {
    const stored = loadStored();
    nextId.current = stored.reduce((mx, m) => Math.max(mx, m.id), 0) + 1;
    setMsgs(stored);
    setLoaded(true);
    return () => ctrl.current?.abort();
  }, []);
  useEffect(() => { if (loaded) saveStored(msgs); }, [msgs, loaded]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, pending]);

  // auto-grow textarea
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 168)}px`;
  }, [input]);

  const send = useCallback(async (raw: string, replaceId?: number) => {
    const q = raw.trim().slice(0, MAX_LEN);
    if (!q || msgsRef.current.some((m) => m.state === "pending")) return;
    // last 6 answered turns go with the question so follow-ups ("а в 2025?") work
    const history: AgentTurn[] = msgsRef.current
      .filter((m) => m.id !== replaceId && m.state === "done" && m.res && m.res.status !== "error" && m.res.answer.trim())
      .slice(-HISTORY_TURNS)
      .flatMap((m) => [{ role: "user" as const, content: m.q }, { role: "assistant" as const, content: m.res!.answer.slice(0, 2000) }]);
    const id = nextId.current++;
    const startedAt = Date.now();
    const item: Msg = { id, q, lang: detectLang(q), startedAt, state: "pending" };
    setMsgs((p) => [...p.filter((m) => m.id !== replaceId), item]);
    setInput("");
    const c = new AbortController();
    ctrl.current = c;
    const done = (patch: Partial<Msg>) =>
      setMsgs((p) => p.map((m) => (m.id === id ? { ...m, ...patch, seconds: (Date.now() - startedAt) / 1000 } : m)));
    try {
      const res = await ask(q, { signal: c.signal, history });
      done({ state: "done", res });
    } catch (e) {
      if (ctrl.current !== c) return; // conversation was reset
      done({ state: "failed", failure: e instanceof ApiError && e.status === 408 ? "timeout" : "failed" });
    } finally {
      taRef.current?.focus();
    }
  }, []);

  const onSubmit = (e: FormEvent) => { e.preventDefault(); void send(input); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(input); }
  };
  const reset = () => {
    const c = ctrl.current;
    ctrl.current = null;
    c?.abort();
    setMsgs([]);
    setInput("");
    taRef.current?.focus();
  };
  const lastDone = [...msgs].reverse().find((m) => m.state !== "pending")?.id;

  return (
    <section className="flex flex-col min-h-[calc(100vh-3rem)] lg:min-h-[calc(100vh-4rem)]">
      <header className="w-full max-w-[760px] mx-auto flex items-center gap-3 min-h-[36px]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="eyebrow truncate">AI agent · UZEX 2022–2026</span>
        </div>
        {msgs.length > 0 && (
          <button type="button" onClick={reset} className="ml-auto h-8 px-3 rounded-lg border border-line bg-white text-[13px] text-ink-2 hover:bg-[#F8F9FB] inline-flex items-center gap-1.5 shrink-0">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
            Yangi suhbat
          </button>
        )}
      </header>

      <div className="flex-1 w-full max-w-[760px] mx-auto">
        {loaded && msgs.length === 0 && (
          <div className="pt-[6vh] sm:pt-[10vh] pb-6 text-center">
            <div className="mx-auto w-12 h-12 rounded-2xl bg-brand text-white grid place-items-center text-[15px] font-semibold">AI</div>
            <h1 className="mt-4 text-[24px] sm:text-[28px] font-semibold tracking-tight">Salom! Birja bitimlari haqida so&apos;rang</h1>
            <p className="mt-1.5 text-[14.5px] text-ink-3">Спросите о биржевых сделках 2022–2026 — на русском или узбекском.</p>
            <p className="mt-1 text-[13px] text-ink-3 max-w-[560px] mx-auto">
              Javob faqat ma&apos;lumotlar bazasidan: har bir javob ostida SQL va natija. Ma&apos;lumot bo&apos;lmasa, agent shuni ochiq aytadi.
            </p>
            <div className="mt-7 grid sm:grid-cols-2 gap-2 text-left">
              {EXAMPLES.map((e) => (
                <button key={e.q} type="button" onClick={() => void send(e.q)}
                  className="group rounded-xl border border-line bg-white px-3.5 py-3 hover:border-brand hover:shadow-sm transition-all">
                  <span className="block text-[11px] font-medium uppercase tracking-[.06em] text-ink-3">{e.tag} · {e.lang}</span>
                  <span className="block mt-1 text-[14px] text-ink-2 group-hover:text-ink">{e.q}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-6 pt-4" aria-live="polite">
          {msgs.map((m) => (
            <div key={m.id} className="space-y-4">
              <div className="flex justify-end pl-10">
                <div className="max-w-[85%] rounded-[18px] rounded-br-[6px] bg-brand text-white px-4 py-2.5 text-[15px] leading-[1.5] whitespace-pre-wrap break-words">{m.q}</div>
              </div>
              <Answer m={m} last={m.id === lastDone} busy={pending} onRetry={() => void send(m.q, m.id)} onAsk={(q) => void send(q)} />
            </div>
          ))}
        </div>
        <div ref={endRef} className="h-2" />
      </div>

      <form onSubmit={onSubmit} className="chat-composer sticky bottom-0 z-30 pt-3 pb-3 bg-gradient-to-t from-canvas via-canvas to-canvas/0">
        <div className="w-full max-w-[760px] mx-auto">
          <div className="card flex items-end gap-2 p-1.5 pl-2 rounded-2xl shadow-sm focus-within:outline focus-within:outline-2 focus-within:outline-brand focus-within:-outline-offset-1">
            <textarea ref={taRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} rows={1} maxLength={MAX_LEN}
              placeholder="Savol yozing… / Напишите вопрос…" aria-label="Savol / Вопрос"
              className="flex-1 resize-none bg-transparent outline-none px-2 py-2 text-[15px] leading-[1.5] max-h-[168px] text-ink placeholder:text-ink-3" />
            <button type="submit" disabled={pending || !input.trim()} aria-label="Yuborish"
              className="w-10 h-10 shrink-0 rounded-xl bg-brand text-white grid place-items-center disabled:opacity-35 disabled:cursor-not-allowed">
              {pending
                ? <span className="w-3 h-3 rounded-[3px] bg-white" aria-hidden="true" />
                : <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" /></svg>}
            </button>
          </div>
          <div className="mt-1 px-2 text-[11.5px] text-ink-3 flex justify-between gap-3">
            <span className="hidden sm:inline">Enter — yuborish · Shift+Enter — yangi qator</span>
            <span className="num ml-auto">{input.length}/{MAX_LEN}</span>
          </div>
        </div>
      </form>
    </section>
  );
}
