export const STATUS_COLORS: Record<string, string> = {
  "Исполнен": "#10B981",
  "Ждёт оплату": "#F59E0B",
  "Аннулирован": "#EF4444",
  "Аннулирован(Не оплачен)": "#EF4444",
  "Новый": "#06B6D4",
  "Оплачен": "#3B82F6",
  "Исполнен(Частично)": "#84CC16",
  "Заключен": "#8B5CF6",
  "Не подписан": "#94A3B8",
  "Ждёт поставку": "#3B82F6",
};
export const statusColor = (s: string): string => STATUS_COLORS[s] ?? "#94A3B8";
