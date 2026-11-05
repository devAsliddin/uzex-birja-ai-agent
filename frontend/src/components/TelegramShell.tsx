"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Minimal typing of the Telegram WebApp object we use (telegram-web-app.js). */
type TgTheme = Partial<Record<
  "bg_color" | "text_color" | "hint_color" | "link_color" | "button_color" | "button_text_color" | "secondary_bg_color",
  string
>>;
interface TgWebApp {
  initData: string;
  colorScheme?: "light" | "dark";
  themeParams?: TgTheme;
  ready(): void;
  expand(): void;
  platform?: string;
  requestFullscreen?(): void;
  isVersionAtLeast?(v: string): boolean;
  onEvent?(e: "themeChanged", cb: () => void): void;
  offEvent?(e: "themeChanged", cb: () => void): void;
}
declare global {
  interface Window { Telegram?: { WebApp?: TgWebApp } }
}

const HEX = /^#[0-9a-fA-F]{3,8}$/;

/** Copy Telegram theme colours into our own CSS variables (only valid hex values). */
function applyTheme(wa: TgWebApp) {
  const root = document.documentElement;
  const t = wa.themeParams ?? {};
  const map: [keyof TgTheme, string][] = [
    ["bg_color", "--tg-bg"], ["secondary_bg_color", "--tg-bg2"], ["text_color", "--tg-text"],
    ["hint_color", "--tg-hint"], ["link_color", "--tg-link"], ["button_color", "--tg-btn"], ["button_text_color", "--tg-btn-text"],
  ];
  for (const [k, v] of map) {
    const c = t[k];
    if (c && HEX.test(c)) root.style.setProperty(v, c);
  }
  root.classList.toggle("tg-dark", wa.colorScheme === "dark");
}

const TABS = [
  { href: "/chat", label: "AI chat", icon: <><path d="M2.5 4.5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H7l-3 2.5v-2.5a1.5 1.5 0 0 1-1.5-1.5z" /><path d="M5.5 6.5h5M5.5 8.5h3" /></> },
  { href: "/", label: "Dashboard", icon: <><rect x="2" y="2" width="5" height="6" rx="1" /><rect x="9" y="2" width="5" height="3" rx="1" /><rect x="9" y="7" width="5" height="7" rx="1" /><rect x="2" y="10" width="5" height="4" rx="1" /></> },
  { href: "/deals", label: "Bitimlar", icon: <path d="M2.5 4h11M2.5 8h11M2.5 12h7" /> },
  { href: "/brokers", label: "Brokerlar", icon: <><circle cx="6" cy="5.5" r="2.5" /><path d="M1.5 13.5c.6-2.4 2.4-3.6 4.5-3.6s3.9 1.2 4.5 3.6M11 3.2a2.4 2.4 0 0 1 0 4.6M12.6 10.2c1 .6 1.6 1.7 1.9 3.3" /></> },
];

function TabBar() {
  const path = usePathname();
  return (
    <nav className="tg-tabbar fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-line bg-white" aria-label="Menyu">
      {TABS.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
        return (
          <Link key={t.href} href={t.href} aria-current={active ? "page" : undefined}
            className={`flex flex-col items-center justify-center gap-0.5 h-14 text-[11px] ${active ? "tg-tab-active font-semibold" : "text-ink-3"}`}>
            <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">{t.icon}</svg>
            <span>{t.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Inside Telegram (WebApp.initData present): ready()+expand(), Telegram theme -> CSS vars, sidebar hidden
 * (CSS on html.tg), bottom tab bar, and the first screen is /chat.
 */
export default function TelegramShell({ children }: { children: ReactNode }) {
  const [tg, setTg] = useState(false);
  const router = useRouter();
  const path = usePathname();
  const redirected = useRef(false);

  useEffect(() => {
    let wa: TgWebApp | undefined;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onTheme = () => wa && applyTheme(wa);
    const init = () => {
      wa = window.Telegram?.WebApp;
      if (!wa) {
        if (tries++ < 20) timer = setTimeout(init, 100); // script may still be loading
        return;
      }
      if (!wa.initData) return; // opened in a normal browser
      try { wa.ready(); wa.expand(); } catch { /* old clients */ }
      // Desktop / web Telegram: open the Mini App full screen (Bot API 8.0+)
      try {
        const desktop = ["tdesktop", "macos", "web", "weba", "webk", "unigram"].includes(wa.platform ?? "");
        if (desktop && wa.requestFullscreen) wa.requestFullscreen();
      } catch { /* not supported */ }
      applyTheme(wa);
      wa.onEvent?.("themeChanged", onTheme);
      document.documentElement.classList.add("tg");
      setTg(true);
    };
    init();
    return () => { if (timer) clearTimeout(timer); wa?.offEvent?.("themeChanged", onTheme); };
  }, []);

  useEffect(() => {
    if (tg && !redirected.current) {
      redirected.current = true;
      if (path === "/") router.replace("/chat"); // start screen inside Telegram
    }
  }, [tg, path, router]);

  return (
    <>
      {children}
      {tg && <TabBar />}
    </>
  );
}
