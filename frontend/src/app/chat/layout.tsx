import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI agent — Birja reyestri",
  description: "Birja bitimlari bo'yicha savolga ma'lumotdan javob va uning manbasi (SQL, natija jadvali)",
};

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children;
}
