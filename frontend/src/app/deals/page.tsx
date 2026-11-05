"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Deal, type DealCard, type DealFilters } from "@/lib/api";
import { fmtInt, fmtMoney, isoToUi, uiToIso } from "@/lib/format";
import { statusColor } from "@/lib/status";
import { Badge, Empty, ErrorBox, Modal, Pagination, Row, Skel } from "@/components/ui";

const LIMIT = 25;

function useDebounced<T>(v: T, ms = 400): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

function DealDrawer({ no, onClose }: { no: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["deal", no], queryFn: () => api.deal(no) });
  return (
    <Modal title={`Bitim № ${no}`} onClose={onClose}>
      {q.isLoading ? <div className="space-y-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skel key={i} className="h-5" />)}</div>
        : q.isError || !q.data ? <ErrorBox onRetry={() => q.refetch()} />
        : <DealBody d={q.data} />}
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="mt-6 first:mt-0"><h3 className="eyebrow mb-1">{title}</h3><dl>{children}</dl></section>;
}

function DealBody({ d }: { d: DealCard }) {
  const c = d.contract;
  const rate = d.usd_rate;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Badge status={d.status} />
        <span className="num text-ink-3 text-[13px]">{isoToUi(d.deal_date)} {d.deal_time?.slice(0, 5)}</span>
      </div>
      <div className="mt-3 text-[15px] font-semibold break-words">{d.product_name}</div>
      <div className="num text-[22px] font-semibold mt-1">{fmtMoney(d.amount)} <span className="text-[13px] text-ink-2 font-normal">{d.currency ?? ""}</span></div>
      {d.currency && d.currency !== "Узбекский сум" && d.amount_uzs != null && (
        <div className="num text-[12.5px] text-ink-3">≈ {fmtMoney(d.amount_uzs)} so&apos;m</div>
      )}

      <div className="mt-6" />
      <Section title="Bitim">
        <Row k="Miqdor">{fmtInt(d.quantity)} lot{d.volume != null && <> · <span className="num">{fmtInt(d.volume)}</span> {d.unit}</>}</Row>
        <Row k="Boshlang'ich narx"><span className="num">{d.start_price != null ? fmtMoney(d.start_price) : "—"}</span></Row>
        <Row k="Savdo turi">{d.trade_type}</Row>
        <Row k="Shartnoma turi / shakli">{d.contract_type} · {d.contract_form}</Row>
        <Row k="Region">{d.region}</Row>
        <Row k="USD kursi">{rate ? <><span className="num">{fmtMoney(rate.rate)}</span> <span className="text-ink-3">({isoToUi(rate.rate_date)}{rate.exact ? "" : ", eng yaqin sana"})</span></> : "—"}</Row>
      </Section>
      <Section title="Shartnoma">
        <Row k="Raqam"><span className="font-mono text-[12.5px]">{d.contract_no}</span></Row>
        <Row k="Guruh / kategoriya">{c?.product_group} / {c?.product_category}</Row>
        <Row k="TN VED"><span className="font-mono text-[12.5px]">{c?.tn_ved_code}</span></Row>
        <Row k="Yetkazib berish bazisi">{c?.delivery_basis}</Row>
        <Row k="Ombor">{c?.warehouse_address}</Row>
        <Row k="Garov">{c?.deposit_percent != null ? `${c.deposit_percent}%` : "—"}</Row>
      </Section>
      <Section title="Sotuvchi va xaridor">
        <Row k="Sotuvchi">{d.seller?.name}<div className="text-[12px] text-ink-3 num">STIR {d.seller?.inn}</div></Row>
        <Row k="Xaridor">{d.buyer?.name}<div className="text-[12px] text-ink-3 num">STIR {d.buyer?.inn}</div></Row>
        <Row k="Sotuvchi brokeri">{d.seller_broker ? <><span className="bk">{d.seller_broker.code}</span> {d.seller_broker.name}</> : "—"}</Row>
        <Row k="Xaridor brokeri">{d.buyer_broker ? <><span className="bk">{d.buyer_broker.code}</span> {d.buyer_broker.name}</> : "—"}</Row>
      </Section>
      <Section title="To'lov va yetkazib berish">
        <Row k="To'lov muddati">{c?.payment_term_days != null ? `${c.payment_term_days} kun` : "—"}</Row>
        <Row k="To'langan sana"><span className="num">{isoToUi(d.payment_date)}</span></Row>
        <Row k="Yetkazish muddati">{c?.delivery_term_days != null ? `${c.delivery_term_days} kun` : "—"}</Row>
        <Row k="Yetkazilgan sana"><span className="num">{isoToUi(d.delivery_date)}</span></Row>
        <Row k="Yetkazilgan lotlar">{d.delivered_lots != null ? `${fmtInt(d.delivered_lots)} / ${fmtInt(d.quantity)}` : "—"}</Row>
      </Section>
    </div>
  );
}

export default function DealsPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [search, setSearch] = useState("");
  const [broker, setBroker] = useState("");
  const [statuses, setStatuses] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const dSearch = useDebounced(search.trim());
  const isoFrom = uiToIso(from);
  const isoTo = uiToIso(to);
  const badFrom = from !== "" && !isoFrom;
  const badTo = to !== "" && !isoTo;

  const filters: DealFilters = useMemo(() => ({
    start_date: isoFrom ?? undefined, end_date: isoTo ?? undefined,
    status: statuses.length ? statuses : undefined, broker: broker || undefined, search: dSearch || undefined,
  }), [isoFrom, isoTo, statuses, broker, dSearch]);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
  const brokers = useQuery({ queryKey: ["broker-options"], queryFn: () => api.brokers({ page: 1, limit: 200 }), staleTime: Infinity });
  const q = useQuery({ queryKey: ["deals", filters, page], queryFn: () => api.deals(filters, page, LIMIT), placeholderData: (p) => p });

  useEffect(() => { setPage(1); }, [filters]);

  const toggle = (s: string) => setStatuses((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  const counts = q.data?.status_counts;
  const allStatuses = meta.data?.statuses ?? [];

  return (
    <section>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow">Reyestr</div>
          <h1 className="text-[26px] font-semibold tracking-tight mt-1">Bitimlar reyestri</h1>
        </div>
        <a className="btn" href={api.exportUrl(filters, "xlsx")} download>
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M8 2v8m0 0 3-3m-3 3L5 7M2.5 11.5v1.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1.5" /></svg>
          Excel&apos;ga yuklash
        </a>
      </header>

      <div className="card mt-4 overflow-hidden">
        <div className="p-4 flex flex-col gap-3 border-b border-line">
          <div className="flex flex-wrap items-center gap-3">
            <label className="field flex items-center gap-2" aria-invalid={badFrom || badTo}>
              <input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="DD.MM.YYYY" inputMode="numeric" maxLength={10} className={`num bg-transparent outline-none w-[92px] ${badFrom ? "text-[#B42318]" : ""}`} aria-label="Boshlanish sanasi" />
              <span className="text-ink-3">—</span>
              <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="DD.MM.YYYY" inputMode="numeric" maxLength={10} className={`num bg-transparent outline-none w-[92px] ${badTo ? "text-[#B42318]" : ""}`} aria-label="Tugash sanasi" />
            </label>
            <label className="field flex items-center gap-2 flex-1 min-w-[200px] max-w-[360px]">
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#6B7685" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Bitim raqami yoki tovar" className="bg-transparent outline-none w-full" aria-label="Qidiruv" />
            </label>
            <select className="field" value={broker} onChange={(e) => setBroker(e.target.value)} aria-label="Broker">
              <option value="">Barcha brokerlar</option>
              {brokers.data?.items.map((b) => <option key={b.broker_code} value={b.broker_code}>{b.broker_code} · {b.name}</option>)}
            </select>
          </div>
          {(badFrom || badTo) && <div role="alert" className="text-[12.5px] text-[#B42318]">Sana formati: DD.MM.YYYY</div>}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] text-ink-3 mr-1">Holat:</span>
            {allStatuses.map((s) => (
              <button key={s} className="chip" style={{ ["--c" as string]: statusColor(s) }} aria-pressed={statuses.includes(s)} onClick={() => toggle(s)}>
                <span className="dot" />{s}
                {counts?.[s] !== undefined && <span className="num text-ink-3 text-[12px]">{fmtInt(counts[s])}</span>}
              </button>
            ))}
            {statuses.length > 0 && <button className="text-[12.5px] text-brand underline ml-1" onClick={() => setStatuses([])}>Tozalash</button>}
          </div>
        </div>

        <div className="overflow-x-auto">
          <DealsTable rows={q.data?.items} loading={q.isLoading} error={q.isError} onRetry={() => q.refetch()} onOpen={setOpen} />
        </div>
        {q.data && q.data.total > 0 && <Pagination page={page} pages={q.data.pages} total={q.data.total} limit={LIMIT} onPage={setPage} />}
      </div>
      {open !== null && <DealDrawer no={open} onClose={() => setOpen(null)} />}
    </section>
  );
}

function DealsTable({ rows, loading, error, onRetry, onOpen }: { rows?: Deal[]; loading: boolean; error: boolean; onRetry: () => void; onOpen: (n: number) => void }) {
  if (error) return <ErrorBox message="Bitimlarni yuklab bo'lmadi" onRetry={onRetry} />;
  return (
    <>
      <table className="reg w-full border-collapse">
        <thead>
          <tr>
            <th>Bitim №</th><th>Sana, vaqt</th><th>Tovar / region</th>
            <th className="!text-right">Miqdor</th><th className="!text-right">Summa</th>
            <th title="Sotuvchi brokeri → xaridor brokeri">Brokerlar</th><th>Holat</th>
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: 10 }).map((_, i) => <tr key={i}><td colSpan={7}><Skel className="h-5" /></td></tr>)}
          {rows?.map((d) => (
            <tr key={d.deal_no} data-click tabIndex={0} onClick={() => onOpen(d.deal_no)} onKeyDown={(e) => e.key === "Enter" && onOpen(d.deal_no)}>
              <td className="num font-mono text-[12.5px] text-ink-2">{d.deal_no}</td>
              <td><span className="num">{isoToUi(d.deal_date)}</span> <span className="num text-ink-3 ml-1">{d.deal_time?.slice(0, 5)}</span></td>
              <td className="max-w-[260px]"><div className="truncate" title={d.product_name}>{d.product_name}</div><div className="text-[12px] text-ink-3 mt-0.5">{d.region}</div></td>
              <td className="num text-right">{fmtInt(d.quantity * (d.lot_size ?? 1))} <span className="text-ink-3 text-[12px]">{d.unit}</span></td>
              <td className="num text-right font-medium">{fmtMoney(d.amount)} <span className="text-ink-3 text-[12px] font-normal">{d.currency === "Доллар США" ? "$" : "so'm"}</span></td>
              <td><span className="bk">{d.seller_broker}</span> <span className="text-ink-3">→</span> <span className="bk">{d.buyer_broker}</span></td>
              <td><Badge status={d.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && rows?.length === 0 && <Empty>Tanlangan filtrlar bo&apos;yicha bitim topilmadi. Holat filtrini yoki sanalarni o&apos;zgartiring.</Empty>}
    </>
  );
}
