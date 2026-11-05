import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card p-10 text-center">
      <div className="text-lg font-semibold">Sahifa topilmadi</div>
      <Link href="/" className="btn mt-4">Dashboard</Link>
    </div>
  );
}
