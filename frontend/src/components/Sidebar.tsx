"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Dashboard", icon: <><rect x="2" y="2" width="5" height="6" rx="1" /><rect x="9" y="2" width="5" height="3" rx="1" /><rect x="9" y="7" width="5" height="7" rx="1" /><rect x="2" y="10" width="5" height="4" rx="1" /></> },
  { href: "/deals", label: "Bitimlar reyestri", icon: <path d="M2.5 4h11M2.5 8h11M2.5 12h7" /> },
  { href: "/brokers", label: "Brokerlar reyestri", icon: <><circle cx="6" cy="5.5" r="2.5" /><path d="M1.5 13.5c.6-2.4 2.4-3.6 4.5-3.6s3.9 1.2 4.5 3.6M11 3.2a2.4 2.4 0 0 1 0 4.6M12.6 10.2c1 .6 1.6 1.7 1.9 3.3" /></> },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="lg:w-[232px] lg:shrink-0 lg:h-screen lg:sticky lg:top-0 border-b lg:border-b-0 lg:border-r border-line bg-canvas px-4 py-4 lg:py-6 flex lg:flex-col gap-4 items-center lg:items-stretch">
      <div className="flex items-center gap-2.5 px-1">
        <div className="w-8 h-8 rounded-md bg-ink text-white grid place-items-center text-[13px] font-semibold">TX</div>
        <div className="leading-tight">
          <div className="text-[14px] font-semibold">Birja reyestri</div>
          <div className="text-[11.5px] text-ink-3 hidden sm:block">Tovar-xomashyo birjasi</div>
        </div>
      </div>
      <nav className="flex lg:flex-col gap-1 lg:mt-6 ml-auto lg:ml-0 overflow-x-auto" aria-label="Asosiy menyu">
        {items.map((i) => {
          const active = i.href === "/" ? path === "/" : path.startsWith(i.href);
          return (
            <Link key={i.href} href={i.href} className={`nav-a ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{i.icon}</svg>
              <span>{i.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
