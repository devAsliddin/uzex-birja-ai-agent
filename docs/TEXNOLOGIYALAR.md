# Texnologiyalar va usullar (forma maydoni uchun)

Quyidagi matnni formaga to'g'ridan-to'g'ri qo'ying. `<...>` belgilarini eval natijasi bilan almashtiring.

---

Stek: Python, FastAPI, SQLite (WAL, Alembic migratsiyalari), Telegram-bot aiogram 3, veb-ilova Next.js 14 + Tailwind, LLM — Gemini API, tekshiruv — pandas va pytest.

Ma'lumot: 9 ta CSV (500 000 bitim) ETL orqali bazaga yuklandi: sanalar ISO formatga, mingliklar bo'shlig'i tozalandi, bo'sh qiymatlar NULL, regionlarning rus va lotin yozuvlari bitta kalitga keltirildi. Dollar shartnomalari bitim sanasidagi kurs bo'yicha so'mga o'giriladi, "Аннулирован" bitimlar aylanmaga qo'shilmaydi.

Usul: text-to-SQL. LLM savolni (RU/UZ, lotin yoki kirill) bitta SELECT so'roviga aylantiradi. So'rov faqat o'qish rejimidagi bazada bajariladi (bitta SELECT tekshiruvi, timeout, xato bo'lsa qayta urinish). Barcha hisoblar SQL ichida, LLM faqat natija qatorlaridan javob yozadi. Keyin kod bilan grounding tekshiruvi: javobdagi har bir raqam, broker kodi va nom natija qatorlarida bo'lishi shart, aks holda javob rad etiladi. Ma'lumotda javob yo'q bo'lsa agent "Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q." / "Не знаю — в данных нет такой информации." deydi.

Manba: har javob ostida asos (jadval, filtr, holat, valyuta), bajarilgan SQL va natija qatorlari ko'rsatiladi — javobni qayta tekshirish mumkin. Javob savol tilida.

Tekshiruv: backend kodidan mustaqil "oltin" to'plam — <GOLDEN_COUNT> ta RU/UZ savol, to'g'ri javoblar pandas bilan to'g'ridan-to'g'ri CSV dan hisoblangan, javobi yo'q "tuzoq" savollar ham bor. Natija: aniqlik <ACCURACY>%, gallyutsinatsiya <HALLUCINATIONS>, o'rtacha javob <AGENT_LATENCY> s. Bot smoke va stress (2 000 parallel so'rov) testlardan o'tgan.
