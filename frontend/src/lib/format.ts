const NB = " ";
export const fmtInt = (n: number): string => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, NB);
export const fmtDec = (n: number, d = 1): string => n.toFixed(d).replace(".", ",");
export const fmtMoney = (n: number): string => {
  const [i, d] = n.toFixed(2).split(".");
  return fmtInt(Number(i)) + "," + d;
};
/** Abbreviate big numbers: trln / mlrd / mln. */
export function abbrev(n: number): { value: string; unit: string } {
  const a = Math.abs(n);
  if (a >= 1e12) return { value: fmtDec(n / 1e12), unit: "trln" };
  if (a >= 1e9) return { value: fmtDec(n / 1e9), unit: "mlrd" };
  if (a >= 1e6) return { value: fmtDec(n / 1e6), unit: "mln" };
  return { value: fmtInt(n), unit: "" };
}
export const isoToUi = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
};
/** DD.MM.YYYY -> YYYY-MM-DD, or null if invalid/empty. */
export const uiToIso = (s: string): string | null => {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s.trim());
  if (!m) return null;
  const dt = new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
  if (dt.getUTCDate() !== +m[1] || dt.getUTCMonth() !== +m[2] - 1) return null;
  return `${m[3]}-${m[2]}-${m[1]}`;
};
