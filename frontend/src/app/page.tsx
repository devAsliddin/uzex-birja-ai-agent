"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from "recharts";
import { api, type Currency, type Summary } from "@/lib/api";
import { abbrev, fmtDec, fmtInt, isoToUi } from "@/lib/format";
import { ErrorBox, Skel } from "@/components/ui";

const YEARS: (number | null)[] = [null, 2022, 2023, 2024, 2025, 2026];

function Seg<T extends string | number | null>({ label, options, value, onChange, fmt }: {
  label: string; options: T[]; value: T; onChange: (v: T) => void; fmt: (v: T) => string;
}) {
  return (
    <div className="seg flex gap-0.5 p-[3px] rounded-lg bg-[#EBEDF0] max-w-full overflow-x-auto" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o)} aria-pressed={o === value} onClick={() => onChange(o)}>{fmt(o)}</button>
      ))}
    </div>
  );
}

function Kpi({ title, children, sub }: { title: string; children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="eyebrow">{title}</div>
      <div className="mt-3 flex items-baseline gap-1.5">{children}</div>
      <div className="mt-2 text-[12.5px] text-ink-3 min-h-[18px]">{sub}</div>
    </div>
  );
}
const Big = ({ children }: { children: React.ReactNode }) => <span className="num text-[30px] font-semibold tracking-tight">{children}</span>;
const Unit = ({ children }: { children: React.ReactNode }) => <span className="text-[14px] text-ink-2">{children}</span>;

function Dashboard({ s, cur, year }: { s: Summary; cur: Currency; year: number | null }) {
  const vol = abbrev(s.total_turnover);
  const unit = cur === "UZS" ? `${vol.unit} so'm` : `${vol.unit} $`;
  const maxRegion = Math.max(...s.regions.map((r) => r.share_pct), 1);
  const topRegions = s.regions.slice(0, 8);
  const rest = s.regions.slice(8);
  const restPct = rest.reduce((a, r) => a + r.share_pct, 0);
  const maxCat = Math.max(...s.top_categories.map((c) => c.turnover), 1);
  const done = s.status_counts?.["Исполнен"];
  const chartData = s.yearly.map((y) => ({ year: String(y.year), v: y.turnover, n: y.deals_count }));
  const chartUnit = abbrev(Math.max(...s.yearly.map((y) => y.turnover), 1));
  const div = chartUnit.unit === "trln" ? 1e12 : chartUnit.unit === "mlrd" ? 1e9 : chartUnit.unit === "mln" ? 1e6 : 1;
  const chartUnitLabel = cur === "UZS" ? `${chartUnit.unit} so'm` : `${chartUnit.unit} $`;
  const partial = Math.max(...s.yearly.map((y) => y.year));

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mt-6">
        <Kpi title="Jami bitimlar hajmi" sub={year ? `${year} yil` : "Butun davr"}>
          <Big>{vol.value}</Big><Unit>{unit}</Unit>
        </Kpi>
        <Kpi title="Bitimlar soni" sub={done !== undefined ? <>Ijro etilgan: <span className="num text-ink-2">{fmtInt(done)}</span> ({fmtDec((done / s.deals_count) * 100)}%)</> : undefined}>
          <Big>{fmtInt(s.deals_count)}</Big>
        </Kpi>
        <Kpi title={`USD kursi${s.usd_rate ? ` · ${isoToUi(s.usd_rate.date)}` : ""}`} sub="1 USD uchun, so&apos;m">
          <Big>{s.usd_rate ? fmtInt(s.usd_rate.rate).concat(",", s.usd_rate.rate.toFixed(2).split(".")[1]) : "—"}</Big><Unit>so&apos;m</Unit>
        </Kpi>
        <Kpi title="Brokerlar soni">
          <Big>{fmtInt(s.broker_count)}</Big>
        </Kpi>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.55fr_1fr] gap-4 mt-4">
        <div className="card p-5 flex flex-col min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-[15px] font-semibold">Aylanma dinamikasi</h2>
              <p className="text-[12.5px] text-ink-3 mt-0.5">Yillar bo&apos;yicha bitimlar summasi, {chartUnitLabel}</p>
            </div>
            <div className="flex items-center gap-4 text-[12px] text-ink-3">
              <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-sm bg-brand inline-block" />To&apos;liq yil</span>
              <span className="flex items-center gap-1.5"><i className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: "repeating-linear-gradient(135deg,#1F3B73 0 2px,#C9D3E8 2px 4px)" }} />{partial} (to&apos;liq emas)</span>
            </div>
          </div>
          <div className="relative min-h-[300px] mt-4 flex-1" role="img" aria-label="Yillar bo'yicha aylanma diagrammasi">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ top: 22, right: 8, left: 0, bottom: 18 }}>
                <defs>
                  <pattern id="hatch" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
                    <rect width="8" height="8" fill="#C9D3E8" />
                    <rect width="3" height="8" fill="#1F3B73" />
                  </pattern>
                </defs>
                <XAxis dataKey="year" axisLine={{ stroke: "#E4E7EC" }} tickLine={false} tick={{ fill: "#3B4757", fontSize: 12, fontWeight: 500 }} />
                <YAxis hide domain={[0, "dataMax"]} />
                <Tooltip cursor={{ fill: "rgba(31,59,115,.05)" }} contentStyle={{ background: "#0B1726", border: 0, borderRadius: 8, color: "#fff", fontSize: 12.5 }} itemStyle={{ color: "#fff" }} labelStyle={{ color: "#fff", fontWeight: 600 }}
                  formatter={(v: number, _n, p) => [`${fmtDec(v / div)} ${chartUnitLabel} · ${fmtInt((p.payload as { n: number }).n)} bitim`, ""]} separator="" />
                <Bar dataKey="v" radius={[4, 4, 0, 0]} barSize={56} isAnimationActive={false}>
                  {chartData.map((d) => (
                    <Cell key={d.year} fill={year && String(year) !== d.year ? "#D5DBE5" : Number(d.year) === partial ? "url(#hatch)" : "#1F3B73"} />
                  ))}
                  <LabelList dataKey="v" position="top" formatter={(v: number) => fmtDec(v / div)} style={{ fill: "#0B1726", fontSize: 12.5, fontWeight: 600 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="flex justify-around text-[11px] text-ink-3 -mt-3">
              {s.yearly.map((y) => <span key={y.year} className="num">{fmtInt(y.deals_count)} bitim</span>)}
            </div>
          </div>
        </div>

        <div className="card p-5 min-w-0">
          <h2 className="text-[15px] font-semibold">Regionlar ulushi</h2>
          <p className="text-[12.5px] text-ink-3 mt-0.5">Aylanmadagi ulush, sotuvchi regioni bo&apos;yicha</p>
          {topRegions.length === 0 ? <p className="mt-4 text-[13px] text-ink-3">Ma&apos;lumot yo&apos;q</p> : (
            <ul className="mt-4 space-y-3">
              {topRegions.map((r) => (
                <li key={r.region}>
                  <div className="flex items-baseline justify-between gap-2 text-[13px]"><span className="truncate">{r.region}</span><span className="num text-ink-2">{fmtDec(r.share_pct)}%</span></div>
                  <div className="bar-track mt-1.5"><div className="bar-fill" style={{ width: `${(r.share_pct / maxRegion) * 100}%` }} /></div>
                </li>
              ))}
              {rest.length > 0 && (
                <li className="pt-1 flex items-baseline justify-between text-[13px] text-ink-3"><span>Boshqa {rest.length} region</span><span className="num">{fmtDec(restPct)}%</span></li>
              )}
            </ul>
          )}
        </div>
      </div>

      <div className="card p-5 mt-4">
        <h2 className="text-[15px] font-semibold">Top tovar kategoriyalari</h2>
        <p className="text-[12.5px] text-ink-3 mt-0.5">Aylanma bo&apos;yicha, {cur === "UZS" ? "so'm" : "$"}</p>
        {s.top_categories.length === 0 ? <p className="mt-4 text-[13px] text-ink-3">Ma&apos;lumot yo&apos;q</p> : (
          <ul className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
            {s.top_categories.map((c) => {
              const a = abbrev(c.turnover);
              return (
                <li key={c.category} className="min-w-0">
                  <div className="flex items-baseline justify-between gap-2 text-[13px]">
                    <span className="truncate">{c.category}</span>
                    <span className="num text-ink-2 shrink-0">{a.value} {a.unit} <span className="text-ink-3">· {fmtInt(c.deals_count)} bitim</span></span>
                  </div>
                  <div className="bar-track mt-1.5"><div className="bar-fill" style={{ width: `${(c.turnover / maxCat) * 100}%` }} /></div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}

function DashSkeleton() {
  return (
    <div aria-busy="true">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mt-6">{[0, 1, 2, 3].map((i) => <div key={i} className="card p-5"><Skel className="h-3 w-28" /><Skel className="h-8 w-36 mt-4" /><Skel className="h-3 w-24 mt-3" /></div>)}</div>
      <div className="grid grid-cols-1 xl:grid-cols-[1.55fr_1fr] gap-4 mt-4"><div className="card p-5"><Skel className="h-[320px]" /></div><div className="card p-5"><Skel className="h-[320px]" /></div></div>
    </div>
  );
}

export default function Page() {
  const [year, setYear] = useState<number | null>(null);
  const [cur, setCur] = useState<Currency>("UZS");
  const q = useQuery({ queryKey: ["summary", year, cur], queryFn: () => api.summary(year, cur), placeholderData: (p) => p });
  return (
    <section>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow">Umumiy ko&apos;rinish</div>
          <h1 className="text-[26px] font-semibold tracking-tight mt-1">Dashboard</h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Seg label="Davr" options={YEARS} value={year} onChange={setYear} fmt={(v) => (v === null ? "Barchasi" : String(v))} />
          <Seg label="Valyuta" options={["UZS", "USD"] as Currency[]} value={cur} onChange={setCur} fmt={(v) => v} />
        </div>
      </header>
      {q.isLoading ? <DashSkeleton /> : q.isError ? <div className="card mt-6"><ErrorBox message="Dashboard ma'lumotini yuklab bo'lmadi" onRetry={() => q.refetch()} /></div> : q.data && <Dashboard s={q.data} cur={cur} year={year} />}
    </section>
  );
}
