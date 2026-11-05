export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

export type Currency = "UZS" | "USD";

export interface YearStat { year: number; deals_count: number; turnover: number }
export interface MonthStat { month: number; deals_count: number; turnover: number }
export interface RegionStat { region: string; deals_count: number; turnover: number; share_pct: number }
export interface CategoryStat { category: string; deals_count: number; turnover: number }
export interface Summary {
  year: number | null;
  currency: Currency;
  total_turnover: number;
  deals_count: number;
  broker_count: number;
  usd_rate: { date: string; rate: number } | null;
  yearly: YearStat[];
  monthly: MonthStat[];
  regions: RegionStat[];
  top_categories: CategoryStat[];
  status_counts?: Record<string, number>;
}
export interface Deal {
  deal_no: number; deal_date: string; deal_time: string | null; trade_type: string | null;
  quantity: number; amount: number; start_price: number | null; currency: string | null; amount_uzs: number | null;
  product_name: string; lot_size: number | null; unit: string | null; region: string | null;
  contract_no: string | null; contract_type: string | null; contract_form: string | null;
  status: string; seller_inn: string | null; seller_name: string | null;
  buyer_inn: string | null; buyer_name: string | null;
  seller_broker: string | null; buyer_broker: string | null;
  payment_date: string | null; delivery_date: string | null; delivered_lots: number | null;
}
export interface Party { inn: string; name: string; region: string | null; activity: string | null; role?: string | null; vat_payer?: boolean | null }
export interface BrokerRef { code: string; name: string; inn: string | null; region: string | null }
export interface DealCard extends Omit<Deal, "seller_broker" | "buyer_broker"> {
  volume: number | null;
  usd_rate: { requested_date: string; rate_date: string; rate: number; exact: boolean } | null;
  contract: {
    contract_number: string; product_group: string | null; product_category: string | null; industry: string | null;
    tn_ved_code: string | null; base_price: number | null; deposit_percent: number | null;
    delivery_basis: string | null; packaging: string | null; warehouse_address: string | null;
    payment_term_days: number | null; delivery_term_days: number | null;
    registration_date: string | null; valid_until: string | null;
  } | null;
  seller: Party | null; buyer: Party | null;
  seller_broker: BrokerRef | null; buyer_broker: BrokerRef | null;
}
export interface Paged<T> { items: T[]; total: number; page: number; limit: number; pages: number; status_counts?: Record<string, number> }
export interface Broker { broker_code: string; name: string; inn: string | null; region: string | null; deals_count: number; turnover_uzs: number; rating: number }
export interface BrokerProfile {
  broker_code: string; name: string; inn: string | null; region: string | null;
  rating: { rank: number; of: number };
  stats: {
    deals_count: number; deals_as_seller_broker: number; deals_as_buyer_broker: number;
    turnover_uzs: number; avg_deal_uzs: number;
    by_status: { status: string; deals_count: number; turnover_uzs: number }[];
  };
}
export interface MetaFilters { statuses: string[]; regions: string[]; broker_regions: string[]; trade_types: string[]; years: number[] }

export interface DealFilters {
  start_date?: string; end_date?: string; status?: string[]; broker?: string; search?: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Params = Record<string, string | number | string[] | undefined | null>;
function qs(p: Params): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function get<T>(path: string, p: Params = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}${qs(p)}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, "Serverga ulanib bo'lmadi");
  }
  if (!res.ok) throw new ApiError(res.status, `Xatolik ${res.status}`);
  return (await res.json()) as T;
}

const dealParams = (f: DealFilters): Params => ({
  start_date: f.start_date, end_date: f.end_date, status: f.status, broker: f.broker, search: f.search,
});

export const api = {
  summary: (year: number | null, currency: Currency) => get<Summary>("/analytics/summary", { year: year ?? undefined, currency }),
  meta: () => get<MetaFilters>("/meta/filters"),
  deals: (f: DealFilters, page: number, limit: number) => get<Paged<Deal>>("/deals", { ...dealParams(f), page, limit, with_status_counts: "true" }),
  deal: (no: number) => get<DealCard>(`/deals/${no}`),
  brokers: (p: { page: number; limit: number; region?: string; search?: string }) => get<Paged<Broker>>("/brokers", p),
  broker: (code: string) => get<BrokerProfile>(`/brokers/${encodeURIComponent(code)}`),
  exportUrl: (f: DealFilters, format: "csv" | "xlsx") => `${API_URL}/export/deals${qs({ ...dealParams(f), format })}`,
};
