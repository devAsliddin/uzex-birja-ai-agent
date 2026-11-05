# Texnologiyalar va usullar (forma maydoni uchun)

Quyidagi matnni formaga to'g'ridan-to'g'ri qo'ying.

---

Stek: Python, FastAPI, SQLite (faqat o'qish), Telegram-bot aiogram 3 + Mini App, veb Next.js 14 + Tailwind, Gemini API, pandas, pytest.

Ma'lumot: 9 ta CSV (500 000 bitim) ETL bilan bazaga: sana ISO, mingliklar bo'shlig'i tozalandi, bo'sh qiymat NULL, regionlarning rus/lotin yozuvi bitta kalitga. Dollar bitimlar sanadagi kurs bilan so'mga o'giriladi, "Аннулирован" aylanmaga kirmaydi.

Usul — gibrid agent. 1) Qoida asosidagi parser savolni (RU/UZ, lotin/kirill) tushunadi va parametrli SQL shablonini bajaradi — LLM chaqiruvisiz. 2) Tushunilmagan savol Gemini ga boradi: bitta so'rovda SQL va javob shabloni, raqamlar natija qatorlaridan kod bilan qo'yiladi. SQL faqat o'qish rejimida (bitta SELECT, timeout). 3) Grounding: javobdagi har raqam, kod va nom natijada bo'lishi shart. Javob yo'q yoki LLM xato bersa: "Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q." / "Не знаю — в данных нет такой информации."

Manba: har javob ostida asos (jadval, filtr, holat, valyuta), SQL va natija qatorlari. Javob savol tilida.

Tekshiruv: to'g'ri javoblar backenddan mustaqil, pandas bilan CSV dan hisoblangan. Oltin to'plam 78 savol: 76/78 (97,4%; 2 tasi oltin to'plamdagi AI-92 yozilishi xatosi, tekshirilgan), javobsiz tuzoqlar 12/12. Yangi parafraz to'plam 60 savol: 60/60. Gallyutsinatsiya 0. Javob p50 ~75 ms, p95 ~0,5 s; 20 parallel so'rov xatosiz.
