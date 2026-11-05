"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { abbrev, fmtInt } from "@/lib/format";
import { Badge, Empty, ErrorBox, Modal, Pagination, Row, Skel } from "@/components/ui";

const LIMIT = 25;

function useDebounced<T>(v: T, ms = 400): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

const money = (n: number) => { const a = abbrev(n); return `${a.value} ${a.unit} so'm`; };

function BrokerModal({ code, onClose }: { code: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["broker", code], queryFn: () => api.broker(code) });
  const b = q.data;
  return (
    <Modal title={b ? b.name : code} onClose={onClose}>
      {q.isLoading ? <div className="space-y-3">{[0, 1, 2, 3, 4].map((i) => <Skel key={i} className="h-5" />)}</div>
        : q.isError || !b ? <ErrorBox onRetry={() => q.refetch()} />
        : (
          <div>
            <dl>
              <Row k="Kod"><span className="bk">{b.broker_code}</span></Row>
              <Row k="STIR"><span className="num">{b.inn}</span></Row>
              <Row k="Region">{b.region}</Row>
              <Row k="Reyting">{b.rating.rank} / {b.rating.of}</Row>
              <Row k="Bitimlar soni"><span className="num">{fmtInt(b.stats.deals_count)}</span></Row>
              <Row k="Sotuvchi brokeri sifatida"><span className="num">{fmtInt(b.stats.deals_as_seller_broker)}</span></Row>
              <Row k="Xaridor brokeri sifatida"><span className="num">{fmtInt(b.stats.deals_as_buyer_broker)}</span></Row>
              <Row k="Aylanma"><span className="num">{money(b.stats.turnover_uzs)}</span></Row>
              <Row k="O'rtacha bitim"><span className="num">{money(b.stats.avg_deal_uzs)}</span></Row>
            </dl>
            <h3 className="eyebrow mt-6 mb-2">Holatlar bo&apos;yicha</h3>
            <table className="reg w-full border-collapse">
              <thead><tr><th>Holat</th><th className="!text-right">Bitimlar</th><th className="!text-right">Aylanma</th></tr></thead>
              <tbody>
                {b.stats.by_status.map((s) => (
                  <tr key={s.status}><td><Badge status={s.status} /></td><td className="num text-right">{fmtInt(s.deals_count)}</td><td className="num text-right">{money(s.turnover_uzs)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </Modal>
  );
}

export default function BrokersPage() {
  const [search, setSearch] = useState("");
  const [region, setRegion] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const dSearch = useDebounced(search.trim());
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
  const q = useQuery({
    queryKey: ["brokers", dSearch, region, page],
    queryFn: () => api.brokers({ page, limit: LIMIT, search: dSearch || undefined, region: region || undefined }),
    placeholderData: (p) => p,
  });
  useEffect(() => { setPage(1); }, [dSearch, region]);

  return (
    <section>
      <header>
        <div className="eyebrow">Reyestr</div>
        <h1 className="text-[26px] font-semibold tracking-tight mt-1">Brokerlar reyestri</h1>
      </header>
      <div className="card mt-4 overflow-hidden">
        <div className="p-4 flex flex-wrap items-center gap-3 border-b border-line">
          <label className="field flex items-center gap-2 flex-1 min-w-[200px] max-w-[360px]">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#6B7685" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nomi, kodi yoki STIR" className="bg-transparent outline-none w-full" aria-label="Qidiruv" />
          </label>
          <select className="field max-w-full" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
            <option value="">Barcha regionlar</option>
            {meta.data?.broker_regions.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto">
          {q.isError ? <ErrorBox message="Brokerlarni yuklab bo'lmadi" onRetry={() => q.refetch()} /> : (
            <table className="reg w-full border-collapse">
              <thead>
                <tr><th>#</th><th>Kod</th><th>Nomi</th><th>Region</th><th className="!text-right">Bitimlar</th><th className="!text-right">Aylanma, so&apos;m</th></tr>
              </thead>
              <tbody>
                {q.isLoading && Array.from({ length: 10 }).map((_, i) => <tr key={i}><td colSpan={6}><Skel className="h-5" /></td></tr>)}
                {q.data?.items.map((b) => (
                  <tr key={b.broker_code} data-click tabIndex={0} onClick={() => setOpen(b.broker_code)} onKeyDown={(e) => e.key === "Enter" && setOpen(b.broker_code)}>
                    <td className="num text-ink-3">{b.rating}</td>
                    <td><span className="bk">{b.broker_code}</span></td>
                    <td className="max-w-[280px]"><div className="truncate" title={b.name}>{b.name}</div></td>
                    <td className="text-ink-2">{b.region}</td>
                    <td className="num text-right">{fmtInt(b.deals_count)}</td>
                    <td className="num text-right font-medium">{money(b.turnover_uzs).replace(" so'm", "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!q.isLoading && q.data?.items.length === 0 && <Empty>Broker topilmadi. Qidiruv yoki regionni o&apos;zgartiring.</Empty>}
        </div>
        {q.data && q.data.total > 0 && <Pagination page={page} pages={q.data.pages} total={q.data.total} limit={LIMIT} onPage={setPage} />}
      </div>
      {open && <BrokerModal code={open} onClose={() => setOpen(null)} />}
    </section>
  );
}
