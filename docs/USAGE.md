# Foydalanish qo'llanmasi

Bu qo'llanma uch kanalni tushuntiradi: Telegram-bot (asosiy, hakam savollari uchun), veb-ilova va REST API.
Barcha ma'lumotlar o'ylab topilgan (sintetik), davr: 2022-yil 3-yanvar — 2026-yil 30-oktabr. Bitim holatlari
2026-yil 30-oktabr kuni oxiridagi holat bo'yicha.

## 1. Telegram-bot

Havola: https://t.me/tiu_uzex_ai. Bot hamma uchun ochiq: ro'yxatdan o'tish, parol yoki admin ruxsati kerak emas.
`/start` ni bosing va savolni oddiy matn bilan yozing.

### 1.1. Savol berish

- Savolni **rus yoki o'zbek** tilida (lotin yoki kirill) yozing. Javob savol tilida qaytadi.
- Shaxsiy chatda har qanday matn savol hisoblanadi. Guruhda botni `@` bilan eslang yoki uning xabariga javob (reply) qiling.
- Javob odatda bir necha soniyada keladi; bot "yozmoqda..." holatini ko'rsatib turadi. Maksimal kutish — 80 soniya
  (hakam limiti 90 soniya).
- Savol 500 belgigacha qisqartiriladi. Bitta foydalanuvchi uchun: daqiqasiga 10 ta, kuniga 200 ta savol.

Aniq savol yaxshiroq javob beradi: davr (yil, oy, sana oralig'i), tovar, region, broker kodi (`BK001`),
kompaniya STIR (INN) yoki bitim raqamini ko'rsating.

### 1.2. Misol savollar

O'zbekcha:
- `2025-yilda jami nechta bitim tuzilgan?`
- `2024-yilda aylanma bo'yicha eng katta broker qaysi?`
- `2023-yil mart oyida qaysi tovar eng ko'p sotilgan?`
- `Farg'ona viloyatida 2026-yilda bitimlar summasi qancha?`
- `604082-raqamli bitim qachon to'langan?`
- `Eksport bitimlari dollarda jami qancha?`
- `Qancha bitim qisman yetkazilgan?`

Ruscha:
- `Какой брокер имел наибольший оборот в 2024 году?`
- `Сколько сделок было аннулировано в 2023 году?`
- `Средняя цена пшеницы за тонну в 2025 году?`
- `Топ-5 покупателей по сумме сделок за 2022 год`
- `Сколько сделок с опозданием поставки?`
- `Какой курс доллара был 15.03.2024?`

Ma'lumotda javobi yo'q savollar (agent "Bilmayman" deydi):
- `2021-yilda nechta bitim bo'lgan?` (davrdan tashqarida)
- `Какая прибыль у компании X?` (foyda ma'lumotlarda yo'q)
- `Ertaga paxta narxi qancha bo'ladi?` (prognoz)

### 1.3. Javobni o'qish va "Manba" bloki

Javob ikki qismdan iborat:

1. **Javob** — birinchi qatorda to'g'ridan-to'g'ri javob (asosiy raqam yoki nom), keyin 1–3 qisqa qatorda tafsilot
   (kim, nima, qachon, qancha, valyuta).
2. **Manba** (ruschada **Источник**) — javob nimaga asoslangani:
   - **Asos / Основание** — bir jumlada: qaysi jadval, qaysi filtrlar, qaysi holatlar hisobga olingan, valyuta, taxminlar
     (masalan, "Аннулирован(Не оплачен) holatidagi bitimlar aylanmadan chiqarilgan").
   - **SQL** — bazada aynan bajarilgan so'rov. Uni o'zingiz qayta ishga tushirib tekshirishingiz mumkin.
   - **N ta qator** — SQL qaytargan qatorlar soni.
   - **Jadval** — natija qatorlari (kichik natijalarda to'liq). Javobdagi har bir raqam shu jadvalda bor.

Javob topilmasa, Manba bloki chiqmaydi, faqat:

```
Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q.
Не знаю — в данных нет такой информации.
```

Bu xato emas: agent javobni o'ylab topishdan ko'ra ochiq aytishni tanlaydi.

Pul summalari: so'mda (`so'm` / `сум`) yoki dollarda (`USD`). Eksport (dollar) shartnomalari bitim sanasidagi kurs
bo'yicha so'mga o'giriladi. Aylanma (oborot) — `Аннулирован(Не оплачен)` holatidagi bitimlarsiz.

### 1.4. Buyruqlar

Buyruqlar LLM'siz, to'g'ridan-to'g'ri API'dan javob beradi.

| Buyruq | Natija |
|---|---|
| `/start`, `/help` | qisqa yo'riqnoma, misollar va buyruqlar ro'yxati |
| `/summary [yil]` | jami aylanma (so'm va USD), bitimlar soni, o'rtacha bitim, USD kursi, top-3 region va kategoriya |
| `/deal <raqam>` | bitim kartochkasi: summa, holat, tovar, hajm, sana, sotuvchi/xaridor (STIR), brokerlar, shartnoma, to'lov/yetkazish |
| `/broker <BK001>` | broker profili: reyting N/120, bitimlar, aylanma, region, sotuvchi/xaridor tomoni, holatlar bo'yicha taqsimot |
| `/top_brokers` | aylanma bo'yicha top-10 broker (butun davr) |
| `/export <DD.MM.YYYY> <DD.MM.YYYY> [holat] [xlsx]` | bitimlar fayli (CSV yoki Excel), 20 000 qatorgacha |

`/export` uchun holatlar: `yangi, imzolanmagan, tuzilgan, kutilmoqda, tolangan, bajarilgan, qisman, bekor`
(ruscha nomlar ham ishlaydi). Misol: `/export 01.03.2025 31.03.2025 bajarilgan xlsx`. Bitta chat uchun eksport
30 soniyada bir marta.

## 2. Veb-ilova

Manzil (lokal): http://localhost:3000. Login kerak emas.

| Sahifa | Nima bor |
|---|---|
| **Dashboard** (`/`) | jami aylanma (so'm/USD almashtirgich), bitimlar soni, brokerlar soni, USD kursi; yillar va oylar bo'yicha aylanma; regionlar ulushi; top kategoriyalar; holatlar taqsimoti; yil filtri |
| **Bitimlar** (`/deals`) | reyestr jadvali: sana oralig'i, holat (sonlari bilan chiplar), broker, region, tovar yoki bitim raqami bo'yicha qidiruv, saralash, sahifalash; qatorni bosganda bitim kartochkasi (shartnoma, sotuvchi, xaridor, brokerlar, kurs); CSV/Excel eksport |
| **Brokerlar** (`/brokers`) | 120 broker: reyting (aylanma bo'yicha o'rin), bitimlar soni, aylanma, region; qidiruv (kod, nom, STIR); profil oynasi |
| **AI chat** (`/chat`) | botdagi kabi erkin savol; javob ostida asos, SQL va natija jadvali |

## 3. REST API

Bazaviy manzil: `http://127.0.0.1:8000/api/v1`. Swagger: `http://127.0.0.1:8000/docs`. Barcha o'qish endpointlari
ochiq. Sanalar ISO formatda (`YYYY-MM-DD`), summalar so'mda (agar boshqasi ko'rsatilmagan bo'lsa). To'liq shartnoma:
[API_CONTRACT.md](../API_CONTRACT.md).

Xato formati: `{"error": "...", "code": "not_found|validation_error|rate_limit_exceeded|internal_error", "status_code": 404}`.

Quyidagi misollar Windows `curl.exe` uchun (PowerShell'da `curl` o'rniga `curl.exe` yozing). Kirill harflari bo'lgan
parametrlarni URL-kodlash kerak bo'lishi mumkin (`--data-urlencode` bilan `-G`).

### Holat

```powershell
curl.exe http://127.0.0.1:8000/health
```

### AI-agent: `POST /agent/ask`

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/agent/ask -H "Content-Type: application/json" `
  -d "{\"question\": \"2025-yilda nechta bitim tuzilgan?\", \"language\": \"auto\"}"
```

Javob maydonlari:

| Maydon | Ma'nosi |
|---|---|
| `answer` | tayyor matn (savol tilida) |
| `status` | `ok` — javob topildi; `no_data` — ma'lumotda javob yo'q ("Bilmayman ..."); `error` — qayta ishlab bo'lmadi |
| `language` | `uz` yoki `ru` |
| `sql` | bajarilgan SQL so'rov(lar) ro'yxati |
| `columns`, `rows`, `row_count` | natija ustunlari, qatorlari (cheklangan) va soni |
| `basis` | asos: jadval, filtr, holat, valyuta, taxminlar |
| `latency_ms` | javob vaqti |

### Bitimlar: `GET /deals`

```powershell
# 2025-yil mart, bajarilgan, summa bo'yicha kamayish tartibida
curl.exe -G http://127.0.0.1:8000/api/v1/deals --data-urlencode "start_date=2025-03-01" `
  --data-urlencode "end_date=2025-03-31" --data-urlencode "status=Исполнен" `
  --data-urlencode "sort=amount" --data-urlencode "order=desc" --data-urlencode "limit=20"

# broker bo'yicha (sotuvchi YOKI xaridor brokeri) va holatlar soni bilan
curl.exe "http://127.0.0.1:8000/api/v1/deals?broker=BK001&with_status_counts=true&limit=10"

# tovar nomi bo'yicha qidiruv yoki aniq bitim raqami
curl.exe -G http://127.0.0.1:8000/api/v1/deals --data-urlencode "search=пшеница"
```

Filtrlar: `start_date`, `end_date`, `status` (bir necha marta yoki vergul bilan), `broker`, `region` (lotin yoki rus
yozuvi), `search`, `seller_inn`, `buyer_inn`, `contract_no`, `sort`, `order`, `page`, `limit` (1..500).

### Bitim kartochkasi: `GET /deals/{deal_no}`

```powershell
curl.exe http://127.0.0.1:8000/api/v1/deals/604082
```

Shartnoma, sotuvchi, xaridor, brokerlar va bitim sanasidagi USD kursi bilan qaytadi. Noma'lum raqam — `404`.

### Brokerlar: `GET /brokers`, `GET /brokers/{code}`

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/brokers?sort=rating&limit=10"
curl.exe "http://127.0.0.1:8000/api/v1/brokers?search=Gucham"
curl.exe http://127.0.0.1:8000/api/v1/brokers/BK001
```

### Analitika: `GET /analytics/summary`

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/analytics/summary"                 # butun davr, so'm
curl.exe "http://127.0.0.1:8000/api/v1/analytics/summary?year=2025&currency=USD"
```

### Filtr qiymatlari: `GET /meta/filters`

```powershell
curl.exe http://127.0.0.1:8000/api/v1/meta/filters
```

Holatlar, regionlar (rus nomlari bilan), savdo turlari va yillar ro'yxati.

## 4. Eksport

- **Veb:** Bitimlar sahifasida filtrlarni qo'ying va "CSV" yoki "Excel" tugmasini bosing.
- **Bot:** `/export 01.01.2025 31.01.2025 [holat] [xlsx]`.
- **API:**
  ```powershell
  curl.exe -o deals.csv "http://127.0.0.1:8000/api/v1/export/deals?format=csv&start_date=2025-01-01&end_date=2025-01-31"
  curl.exe -o deals.xlsx "http://127.0.0.1:8000/api/v1/export/deals?format=xlsx&broker=BK001"
  ```

CSV — UTF-8 (BOM bilan, Excel to'g'ri ochadi). Maksimal 500 000 qator, IP uchun daqiqasiga 10 ta so'rov.
Formulaga o'xshash qiymatlar (`=`, `+`, `-`, `@` bilan boshlanuvchi) Excel'da bajarilmasligi uchun himoyalangan.
Katta davr (butun yil, xlsx) bir necha o'n soniya olishi mumkin.

## 5. Muammolarni hal qilish

| Belgisi | Sabab va yechim |
|---|---|
| Bot javob bermaydi | backend ishlayotganini tekshiring (`/health`); `bot\.env` dagi `BOT_TOKEN` va `BACKEND_URL`; `run_bot.ps1` oynasidagi xabarlar |
| "Kechirasiz, agent hozir javob bermayapti" | backend yoki Gemini API ga ulanib bo'lmadi; `backend\.env` da `GEMINI_API_KEY` borligini va internetni tekshiring |
| "Javob 80 soniyada tayyor bo'lmadi" | savolni soddaroq qiling (davr, tovar yoki regionni aniq ko'rsating) |
| Kutilgan savolga "Bilmayman" | savolni aniqroq yozing: yil/sana, tovar nomi (ruscha nomi yaxshiroq topiladi), STIR yoki broker kodi |
| `429 rate_limit_exceeded` | limitdan oshdi; bir daqiqa kuting |
| Dashboard bo'sh yoki `0` | ma'lumot import qilinmagan: `data\` da CSV borligini tekshirib, `import_data.ps1` ni ishga tushiring |
| Frontend API ga ulanmaydi | `frontend\.env.local` da `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1`; backend CORS faqat `localhost:3000` va `127.0.0.1:3000` ga ruxsat beradi |
| `run_*.ps1` ishlamaydi ("execution policy") | `powershell -ExecutionPolicy Bypass -File .\run_backend.ps1` ko'rinishida ishga tushiring |
| Import sekin | 500 000 bitim SQLite ga ~3 daqiqa; qayta ishga tushirish xavfsiz (mavjud yozuvlar takrorlanmaydi) |
