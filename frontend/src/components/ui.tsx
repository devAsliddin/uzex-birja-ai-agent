"use client";
import { useEffect, type ReactNode } from "react";
import { statusColor } from "@/lib/status";

export const Badge = ({ status }: { status: string }) => (
  <span className="badge" style={{ ["--c" as string]: statusColor(status) }}>{status}</span>
);

export const Skel = ({ className = "" }: { className?: string }) => <div className={`skel ${className}`} aria-hidden="true" />;

export function ErrorBox({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="p-8 text-center text-[13.5px] text-[#B42318]">
      <div>{message ?? "Ma'lumotni yuklab bo'lmadi"}</div>
      {onRetry && <button className="btn mt-3" onClick={onRetry}>Qayta urinish</button>}
    </div>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="p-10 text-center text-[13.5px] text-ink-3">{children}</div>
);

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/40" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="bg-white w-full max-w-[560px] h-full overflow-y-auto overflow-x-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-line px-5 py-4 flex items-center justify-between gap-3">
          <h2 className="text-[16px] font-semibold truncate">{title}</h2>
          <button onClick={onClose} aria-label="Yopish" className="pg px-2 text-lg leading-none">×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export const Row = ({ k, children }: { k: string; children: ReactNode }) => (
  <div className="flex justify-between gap-4 py-2 border-b border-[#EEF0F3] text-[13.5px]">
    <dt className="text-ink-3 shrink-0">{k}</dt>
    <dd className="text-right min-w-0 break-words">{children ?? "—"}</dd>
  </div>
);

const f = (n: number) => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

export function Pagination({ page, pages, total, limit, onPage }: { page: number; pages: number; total: number; limit: number; onPage: (p: number) => void }) {
  const from = total === 0 ? 0 : (page - 1) * limit + 1;
  const to = Math.min(page * limit, total);
  const nums = new Set<number>([1, pages, page - 1, page, page + 1]);
  const list = Array.from(nums).filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-line text-[13px] text-ink-2">
      <div><span className="num">{f(from)}–{f(to)}</span> / <span className="num">{f(total)}</span> ta</div>
      <nav className="flex items-center gap-1" aria-label="Sahifalar">
        <button className="pg px-2" aria-label="Oldingi" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</button>
        {list.map((n, i) => (
          <span key={n} className="flex items-center gap-1">
            {i > 0 && n - list[i - 1] > 1 && <span className="px-1 text-ink-3">…</span>}
            <button className="pg num px-1.5" aria-current={n === page ? "page" : undefined} onClick={() => onPage(n)}>{f(n)}</button>
          </span>
        ))}
        <button className="pg px-2" aria-label="Keyingi" disabled={page >= pages} onClick={() => onPage(page + 1)}>›</button>
      </nav>
    </div>
  );
}
