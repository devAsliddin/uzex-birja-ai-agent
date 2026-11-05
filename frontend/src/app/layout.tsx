import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";
import Sidebar from "@/components/Sidebar";
import TelegramShell from "@/components/TelegramShell";

const sans = IBM_Plex_Sans({ subsets: ["latin", "cyrillic"], weight: ["400", "500", "600", "700"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin", "cyrillic"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = { title: "Birja reyestri", description: "Tovar-xomashyo birjasi bitimlari reyestri" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, maximumScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uz" className={`${sans.variable} ${mono.variable}`}>
      <body className="font-sans text-ink">
        {/* Telegram Mini App SDK: harmless in a normal browser (initData is empty there). */}
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
        <Providers>
          <TelegramShell>
            <div className="min-h-screen lg:flex">
              <Sidebar />
              <main className="app-main flex-1 min-w-0 px-4 sm:px-6 lg:px-8 py-6 lg:py-8 max-w-[1400px]">{children}</main>
            </div>
          </TelegramShell>
        </Providers>
      </body>
    </html>
  );
}
