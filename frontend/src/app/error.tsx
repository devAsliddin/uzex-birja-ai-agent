"use client";
import { ErrorBox } from "@/components/ui";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="card">
      <ErrorBox message="Kutilmagan xatolik" onRetry={reset} />
    </div>
  );
}
