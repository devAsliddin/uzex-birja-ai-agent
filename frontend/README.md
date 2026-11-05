# Birja reyestri - frontend

Next.js 14 (App Router, TypeScript) + Tailwind + TanStack Query + Recharts.

## Ishga tushirish
```
cd frontend
copy .env.example .env.local     # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
npm install
npm run dev                      # http://localhost:3000
```
Yoki ildiz papkadan: `powershell -File run_frontend.ps1`.

Tekshiruv: `npm run lint`, `npm run build`.

## Tuzilma
- `src/lib/api.ts` - tipli API klient (barcha endpointlar shu yerda)
- `src/app/page.tsx` - Dashboard; `src/app/deals` - bitimlar; `src/app/brokers` - brokerlar
- Dashboard ixtiyoriy `status_counts` maydonini, `/deals` esa `status_counts` (holat chiplaridagi sonlar) ni ko'rsatadi, agar backend qaytarsa.
