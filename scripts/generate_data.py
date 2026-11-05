"""Synthetic dataset generator for the UZEX deals/brokers registry.

Produces the 9 CSV files described in the TZ (section 1) with the exact
headers expected by backend/app/services/import_service.py. Raw formats are
intentionally "dirty" the way the TZ describes (section 2.1):
  * dates DD.MM.YYYY, times HH:MM:SS
  * money with thousand spaces: 1 250 000.00
  * UTF-8, comma separator, quoted fields where needed
  * payment/delivery date and delivered lots empty for unfinished deals

Stdlib only, fully deterministic for a given --seed / --scale.

    python scripts/generate_data.py               # full size (~500k deals)
    python scripts/generate_data.py --scale 0.02  # quick test
"""

from __future__ import annotations

import argparse
import bisect
import csv
import math
import random
import time
from datetime import date, timedelta
from itertools import accumulate
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data"

# --- Spec counts (TZ section 1) ---------------------------------------------
N_BROKERS = 120
N_PARTICIPANTS = 14_392
N_CONTRACTS = 6_616
DEALS_PER_YEAR = {2022: 84_299, 2023: 93_985, 2024: 106_647, 2025: 115_763, 2026: 99_306}

RATES_START = date(2022, 1, 1)
RATES_END = date(2026, 10, 31)   # 1 765 calendar days, as in the TZ table
DATA_CUTOFF = date(2026, 10, 30)  # last deal date / "today" for statuses

# --- Headers: must match ImportService.*_COLUMNS ---------------------------
BROKERS_COLUMNS = ["Код брокера", "Наименование", "ИНН", "Регион"]
PARTICIPANTS_COLUMNS = ["ИНН", "Наименование", "Регион", "Вид деятельности", "Роль", "Плательщик НДС"]
USD_RATES_COLUMNS = ["Дата", "Курс"]
CONTRACTS_COLUMNS = [
    "Номер контракта", "Наименование продукта", "Марка товара", "Размер товара",
    "Сорт товара", "Тип товара", "Класс товара", "Код ТН ВЭД", "Группа товара",
    "Категория товара", "Отрасль промышленности", "Единица измерения", "Лот",
    "Валюта", "Базисная цена", "Сумма залога", "Базис поставки", "Регион",
    "Адрес склада", "Тип торгов", "Тип контракта", "Форма контракта", "Срок оплаты",
    "Срок поставки", "Упаковка", "ИНН продавца", "Дата регистрации", "Действует до",
]
DEALS_COLUMNS = [
    "Номер сделки", "Дата сделки", "Время сделки", "Тип торгов", "Количество",
    "Сумма сделки", "Стартовая цена", "Номер контракта", "Наименование товара",
    "Лот", "Единица измерения", "Регион", "Тип контракта", "Форма контракта",
    "Состояние сделки", "ИНН продавца", "ИНН покупателя", "Брокер продавца",
    "Брокер покупателя", "Дата оплаты", "Дата поставки", "Поставлено",
]

# --- Reference data ----------------------------------------------------------
REGIONS = [
    ("г. Ташкент", 22), ("Ташкентская область", 12), ("Самаркандская область", 8),
    ("Ферганская область", 8), ("Андижанская область", 7), ("Наманганская область", 6),
    ("Кашкадарьинская область", 6), ("Бухарская область", 6), ("Навоийская область", 5),
    ("Сурхандарьинская область", 5), ("Хорезмская область", 5), ("Джизакская область", 4),
    ("Сырдарьинская область", 3), ("Республика Каракалпакстан", 3),
]
REGION_CITY = {
    "г. Ташкент": "г. Ташкент", "Ташкентская область": "г. Чирчик",
    "Самаркандская область": "г. Самарканд", "Ферганская область": "г. Фергана",
    "Андижанская область": "г. Андижан", "Наманганская область": "г. Наманган",
    "Кашкадарьинская область": "г. Карши", "Бухарская область": "г. Бухара",
    "Навоийская область": "г. Навои", "Сурхандарьинская область": "г. Термез",
    "Хорезмская область": "г. Ургенч", "Джизакская область": "г. Джизак",
    "Сырдарьинская область": "г. Гулистан", "Республика Каракалпакстан": "г. Нукус",
}
STREETS = [
    "ул. Амира Темура", "ул. Навои", "ул. Мустакиллик", "ул. Бобура", "ул. Фуркат",
    "ул. Промышленная", "ул. Заводская", "ул. Узбекистанская", "ул. Шота Руставели",
    "ул. Бунёдкор", "ул. Тараккиёт", "ул. Саноат", "ул. Ипак йули", "ул. Дустлик",
    "Промзона", "ул. Мирзо Улугбека", "ул. Алишера Навои", "ул. Беруни",
]

# Commodity catalogue:
# (product, tn_ved, group, category, industry, unit, lots, uzs_price_2022,
#  weight, export_share, brands, sizes, grades, types, classes, packaging)
COMMODITIES = [
    ("Хлопковое волокно", "5201000000", "Сельскохозяйственная продукция", "Хлопок", "Сельское хозяйство",
     "тонна", [5, 10, 20], 19_500_000, 6, 0.35, ["", ""], ["", ""], ["I сорт", "II сорт", "III сорт"],
     ["Средневолокнистый", "Тонковолокнистый"], ["Высший", "Отборный", "Хороший"], ["Кипы", "Кипы в обвязке"]),
    ("Пряжа хлопчатобумажная", "5205120000", "Текстильная продукция", "Пряжа", "Лёгкая промышленность",
     "тонна", [1, 5, 10], 34_000_000, 3, 0.45, ["Ne 20/1", "Ne 30/1", "Ne 40/1"], ["", ""], ["", ""],
     ["Кардная", "Гребенная", "Пневмопрядения"], ["", ""], ["Бобины в мешках", "Картонные коробки"]),
    ("Пшеница продовольственная", "1001990000", "Сельскохозяйственная продукция", "Зерно", "Сельское хозяйство",
     "тонна", [20, 60, 65], 3_400_000, 9, 0.02, ["", ""], ["", ""], ["", ""],
     ["Мягкая", "Твердая"], ["3 класс", "4 класс", "5 класс"], ["Насыпью", "Мешки 50 кг"]),
    ("Мука пшеничная", "1101001500", "Продовольственные товары", "Мука", "Пищевая промышленность",
     "тонна", [10, 20], 4_600_000, 6, 0.05, ["", ""], ["", ""], ["Высший сорт", "Первый сорт", "Второй сорт"],
     ["", ""], ["", ""], ["Мешки 50 кг", "Мешки 25 кг"]),
    ("Сахар белый", "1701991000", "Продовольственные товары", "Сахар", "Пищевая промышленность",
     "тонна", [10, 20], 9_800_000, 4, 0.0, ["ТС2", "ТС1"], ["", ""], ["", ""], ["Кристаллический", ""],
     ["", ""], ["Мешки 50 кг"]),
    ("Масло хлопковое рафинированное", "1512290000", "Продовольственные товары", "Растительное масло",
     "Пищевая промышленность", "тонна", [5, 20], 17_500_000, 4, 0.0, ["", ""], ["", ""],
     ["Высший сорт", "Первый сорт"], ["Дезодорированное", "Недезодорированное"], ["", ""],
     ["Наливом", "ПЭТ бутылки 5 л"]),
    ("Цемент ПЦ 400-Д20", "2523290000", "Строительные материалы", "Цемент", "Строительная индустрия",
     "тонна", [20, 40, 60], 760_000, 10, 0.08, ["М400", "ЦЕМ II/А-Ш 32,5Н"], ["", ""], ["", ""],
     ["Портландцемент", "Шлакопортландцемент"], ["", ""], ["Навалом", "Мешки 50 кг", "Биг-бэги"]),
    ("Цемент ПЦ 500-Д0", "2523290000", "Строительные материалы", "Цемент", "Строительная индустрия",
     "тонна", [20, 40, 60], 880_000, 6, 0.08, ["М500", "ЦЕМ I 42,5Н"], ["", ""], ["", ""],
     ["Портландцемент", ""], ["", ""], ["Навалом", "Мешки 50 кг"]),
    ("Арматура стальная А500С", "7214200000", "Металлопрокат", "Сортовой прокат", "Металлургия",
     "тонна", [5, 20, 25], 9_400_000, 6, 0.05, ["А500С", "А400"], ["d10 мм", "d12 мм", "d14 мм", "d16 мм", "d20 мм"],
     ["", ""], ["Горячекатаная", ""], ["", ""], ["Пачки", "Бунты"]),
    ("Лист стальной горячекатаный", "7208510000", "Металлопрокат", "Листовой прокат", "Металлургия",
     "тонна", [5, 20], 11_200_000, 3, 0.05, ["Ст3сп", "09Г2С"], ["2x1250x2500", "4x1500x6000", "10x1500x6000"],
     ["", ""], ["", ""], ["", ""], ["Пачки"]),
    ("Катод медный", "7403110000", "Цветные металлы", "Медь", "Металлургия",
     "тонна", [5, 25], 108_000_000, 2, 0.7, ["М00к", "М0к"], ["", ""], ["", ""], ["", ""], ["", ""], ["Пачки"]),
    ("Дизельное топливо", "2710194200", "Нефтепродукты", "Топливо", "Нефтегазовая промышленность",
     "тонна", [20, 60], 11_300_000, 7, 0.0, ["ДТ-Л-К5", "ДТ-З-К5", "Евро-5"], ["", ""], ["", ""],
     ["Летнее", "Зимнее", "Межсезонное"], ["К5", "К4"], ["Ж/д цистерны", "Автоцистерны"]),
    ("Бензин автомобильный АИ-92", "2710124500", "Нефтепродукты", "Топливо", "Нефтегазовая промышленность",
     "тонна", [20, 60], 11_900_000, 6, 0.0, ["АИ-92-К4", "АИ-92-К5"], ["", ""], ["", ""], ["", ""],
     ["К4", "К5"], ["Ж/д цистерны", "Автоцистерны"]),
    ("Газ сжиженный пропан-бутан", "2711129400", "Нефтепродукты", "Сжиженный газ",
     "Нефтегазовая промышленность", "тонна", [10, 20], 6_100_000, 5, 0.1, ["СПБТ", "ПБА"], ["", ""], ["", ""],
     ["", ""], ["", ""], ["Газовозы"]),
    ("Битум нефтяной дорожный", "2713200000", "Нефтепродукты", "Битум", "Нефтегазовая промышленность",
     "тонна", [20, 60], 5_600_000, 2, 0.0, ["БНД 60/90", "БНД 90/130"], ["", ""], ["", ""], ["", ""], ["", ""],
     ["Наливом", "Бочки"]),
    ("Карбамид (мочевина)", "3102101000", "Минеральные удобрения", "Азотные удобрения", "Химическая промышленность",
     "тонна", [20, 60], 4_100_000, 5, 0.25, ["Марка Б", "Марка А"], ["", ""], ["Высший сорт", "Первый сорт"],
     ["Гранулированный", "Приллированный"], ["", ""], ["Мешки 50 кг", "Биг-бэги", "Навалом"]),
    ("Селитра аммиачная", "3102300000", "Минеральные удобрения", "Азотные удобрения", "Химическая промышленность",
     "тонна", [20, 60], 3_000_000, 5, 0.2, ["Марка Б", ""], ["", ""], ["", ""], ["Гранулированная", ""],
     ["", ""], ["Мешки 50 кг", "Биг-бэги"]),
    ("Аммофос", "3105300000", "Минеральные удобрения", "Фосфорные удобрения", "Химическая промышленность",
     "тонна", [20, 60], 6_600_000, 3, 0.2, ["NP 11:46", "NP 12:52"], ["", ""], ["", ""], ["Гранулированный", ""],
     ["", ""], ["Мешки 50 кг", "Биг-бэги"]),
    ("Полиэтилен высокого давления", "3901100000", "Химическая продукция", "Полимеры", "Химическая промышленность",
     "тонна", [5, 20], 15_200_000, 3, 0.5, ["15803-020", "LDPE FB3003"], ["", ""], ["Высший сорт", "Первый сорт"],
     ["Гранулы", ""], ["", ""], ["Мешки 25 кг"]),
    ("Полипропилен", "3902100000", "Химическая продукция", "Полимеры", "Химическая промышленность",
     "тонна", [5, 20], 14_600_000, 2, 0.5, ["J350", "PP H030"], ["", ""], ["", ""], ["Гомополимер", ""],
     ["", ""], ["Мешки 25 кг"]),
    ("Уголь бурый", "2702100000", "Твёрдое топливо", "Уголь", "Угольная промышленность",
     "тонна", [20, 60, 70], 620_000, 4, 0.0, ["2БР", "2БПК"], ["0-300 мм", "0-50 мм"], ["", ""], ["", ""],
     ["", ""], ["Навалом"]),
    ("Пиломатериалы хвойных пород", "4407109100", "Лесоматериалы", "Пиломатериалы", "Деревообработка",
     "м3", [10, 20, 40], 3_600_000, 2, 0.0, ["", ""], ["50x150x6000", "25x100x6000", "100x100x6000"],
     ["1 сорт", "2 сорт", "3 сорт"], ["Обрезные", "Необрезные"], ["", ""], ["Пачки"]),
    ("Стекло листовое флоат", "7005290000", "Строительные материалы", "Стекло", "Строительная индустрия",
     "м2", [500, 1000, 2000], 78_000, 2, 0.15, ["М1", "М4"], ["4 мм", "5 мм", "6 мм"], ["", ""], ["", ""],
     ["", ""], ["Пирамиды"]),
    ("Кирпич керамический", "6904100000", "Строительные материалы", "Кирпич", "Строительная индустрия",
     "шт", [5000, 10000], 950, 2, 0.0, ["М100", "М125", "М150"], ["250x120x65", ""], ["", ""],
     ["Полнотелый", "Пустотелый"], ["", ""], ["Поддоны"]),
    ("Хлопковый шрот", "2306100000", "Сельскохозяйственная продукция", "Корма", "Пищевая промышленность",
     "тонна", [20, 60], 2_900_000, 3, 0.1, ["", ""], ["", ""], ["", ""], ["Тостированный", ""], ["", ""],
     ["Навалом", "Мешки 40 кг"]),
    ("Рис шлифованный", "1006309800", "Продовольственные товары", "Крупы", "Пищевая промышленность",
     "тонна", [5, 20], 12_000_000, 2, 0.0, ["Лазер", "Девзира"], ["", ""], ["Высший сорт", "Первый сорт"],
     ["Шлифованный", ""], ["", ""], ["Мешки 25 кг", "Мешки 50 кг"]),
]

AUCTION_TYPES = [("Аукцион", 60), ("Двойной встречный аукцион", 25), ("Закрытый аукцион", 8),
                 ("Биржевая котировка", 7)]
CONTRACT_FORMS = [("Спот", 82), ("Форвард", 15), ("Фьючерс", 3)]
DELIVERY_BASES_DOM = ["FCA склад продавца", "EXW склад продавца", "CPT станция назначения",
                      "DAP склад покупателя", "Франко-вагон станция отправления"]
DELIVERY_BASES_EXP = ["FCA ст. Келес", "DAP граница РУз", "CPT ст. Сарыагач", "FCA ст. Хайратон"]
CURRENCY_UZS = "Узбекский сум"
CURRENCY_USD = "Доллар США"

COMPANY_FORMS = [("ООО", 62), ("АО", 6), ("ЧП", 14), ("СП ООО", 4), ("ФХ", 8), ("ИП ООО", 3),
                 ("ДП", 2), ("МЧЖ", 1)]
NAME_WORDS_1 = [
    "Agro", "Oltin", "Vodiy", "Navro'z", "Sharq", "Ziyo", "Buston", "Yulduz", "Samarqand", "Farg'ona",
    "Do'stlik", "Istiqlol", "Kamolot", "Nur", "Zarafshon", "Orzu", "Bunyodkor", "Temir", "Paxta",
    "G'alla", "Baraka", "Turon", "Mega", "Grand", "Euro", "Asia", "Silk Road", "Universal", "Prime",
    "Golden", "Green", "Steel", "Imkon", "Yangi", "Ulugbek", "Afrosiyob", "Registon", "Chorsu",
    "Shohona", "Sarbon", "Durdona", "Saodat", "Iqbol", "Omad", "Mehr", "Bahor", "Tong", "Quyosh",
    "Lazzat", "Diyor", "Azamat", "Javohir", "Elita", "Max", "Star", "Alfa", "Atlas", "Optima", "Delta",
]
NAME_WORDS_2 = [
    "Trade", "Invest", "Group", "Servis", "Savdo", "Qurilish", "Tekstil", "Logistik", "Agro", "Industry",
    "Metall", "Neft", "Kimyo", "Sement", "Plast", "Food", "Export", "Holding", "Market", "Build",
    "Energy", "Textile", "Partners", "Development", "Distribution", "Supply", "Stroy", "Ko'mir",
    "Don Mahsulotlari", "Ta'minot", "Biznes", "Sanoat",
]
ACTIVITIES = [
    ("Оптовая торговля", 30), ("Строительство", 14), ("Производство строительных материалов", 7),
    ("Сельское хозяйство", 9), ("Производство пищевых продуктов", 8), ("Текстильное производство", 6),
    ("Металлургическое производство", 3), ("Производство химической продукции", 3),
    ("Транспорт и логистика", 5), ("Розничная торговля", 7), ("Переработка нефтепродуктов", 2),
    ("Добыча полезных ископаемых", 1), ("Деревообработка", 2), ("Производство мебели", 2),
]
BROKER_WORDS = [
    "Birja", "Broker", "Invest", "Capital", "Market", "Trade", "Finance", "Savdo", "Partner", "Consult",
]

# Monthly seasonality of exchange activity (Jan..Dec)
MONTH_FACTOR = [0.80, 0.86, 1.00, 1.05, 1.04, 1.00, 0.96, 1.02, 1.10, 1.16, 1.12, 1.08]
WEEKDAY_FACTOR = [1.05, 1.08, 1.06, 1.04, 0.97, 0.0, 0.0]  # Mon..Sun, exchange closed on weekends

# USD/UZS anchor points (piecewise-linear trend; noise added on top)
RATE_ANCHORS = [
    (date(2022, 1, 1), 10_835.0), (date(2022, 7, 1), 10_930.0), (date(2022, 12, 31), 11_225.0),
    (date(2023, 6, 30), 11_450.0), (date(2023, 12, 31), 12_340.0), (date(2024, 6, 30), 12_610.0),
    (date(2024, 12, 31), 12_920.0), (date(2025, 6, 30), 12_760.0), (date(2025, 12, 31), 12_520.0),
    (date(2026, 6, 30), 12_660.0), (date(2026, 10, 31), 12_810.0),
]


# --- Helpers -----------------------------------------------------------------
def fmt_date(d: date | None) -> str:
    return "" if d is None else d.strftime("%d.%m.%Y")


def fmt_money(x: float) -> str:
    """1250000.0 -> '1 250 000.00' (thousand spaces, as in the source registry)."""
    return f"{x:,.2f}".replace(",", " ")


def fmt_int_spaced(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def weighted(rng: random.Random, pairs):
    vals, w = zip(*pairs)
    return rng.choices(vals, weights=w, k=1)[0]


def daterange(a: date, b: date):
    d = a
    one = timedelta(days=1)
    while d <= b:
        yield d
        d += one


def scaled(n: int, scale: float, minimum: int = 1) -> int:
    return max(minimum, int(round(n * scale)))


def heavy_tail_weights(rng: random.Random, n: int, alpha: float = 1.3) -> list[float]:
    """Pareto-like activity weights so some entities dominate (realistic ratings)."""
    return [rng.paretovariate(alpha) for _ in range(n)]


def price_index(d: date, usd: bool) -> float:
    """Price level relative to 2022-01-01 (UZS inflation ~11%/yr, USD ~3%/yr)."""
    years = (d - RATES_START).days / 365.25
    return (1.03 if usd else 1.11) ** years


def write_csv(path: Path, header: list[str], rows) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
            n += 1
    return n


class InnFactory:
    """Unique 9-digit INNs (legal entities start with 2 or 3)."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.used: set[str] = set()

    def new(self) -> str:
        while True:
            inn = str(self.rng.choice((2, 3))) + f"{self.rng.randrange(0, 10**8):08d}"
            if inn not in self.used:
                self.used.add(inn)
                return inn


def company_name(rng: random.Random, used: set[str]) -> str:
    for _ in range(50):
        form = weighted(rng, COMPANY_FORMS)
        w1 = rng.choice(NAME_WORDS_1)
        style = rng.random()
        if style < 0.55:
            core = f"{w1} {rng.choice(NAME_WORDS_2)}"
        elif style < 0.75:
            core = f"{w1}{rng.choice(NAME_WORDS_2).lower()}"
        elif style < 0.9:
            core = f"{w1} {rng.choice(NAME_WORDS_2)} {rng.choice(NAME_WORDS_2)}"
        else:
            core = f"{w1}-{rng.randint(1, 99)}"
        name = f'{form} "{core}"'
        if name not in used:
            used.add(name)
            return name
    name = f'{form} "{core} {len(used)}"'
    used.add(name)
    return name


# --- Generators --------------------------------------------------------------
def gen_brokers(rng: random.Random, inns: InnFactory):
    rows = []
    used: set[str] = set()
    for i in range(1, N_BROKERS + 1):
        while True:
            name = f'ООО "{rng.choice(NAME_WORDS_1)} {rng.choice(BROKER_WORDS)}"'
            if name not in used:
                used.add(name)
                break
        rows.append([f"BK{i:03d}", name, inns.new(), weighted(rng, REGIONS)])
    return rows


def gen_participants(rng: random.Random, inns: InnFactory, n: int):
    rows = []
    used: set[str] = set()
    n_sellers = max(2, int(n * 0.24))
    for i in range(n):
        role = "Продавец" if i < n_sellers else "Покупатель"
        name = company_name(rng, used)
        if name.startswith("ФХ"):
            activity = "Сельское хозяйство"
        else:
            activity = weighted(rng, ACTIVITIES)
        vat = "Да" if rng.random() < (0.78 if role == "Продавец" else 0.55) else "Нет"
        rows.append([inns.new(), name, weighted(rng, REGIONS), activity, role, vat])
    rng.shuffle(rows)
    return rows


def gen_usd_rates(rng: random.Random):
    anchors = RATE_ANCHORS
    rates: dict[date, float] = {}
    noise = 0.0
    last = None
    for d in daterange(RATES_START, RATES_END):
        k = bisect.bisect_right([a[0] for a in anchors], d) - 1
        k = min(max(k, 0), len(anchors) - 2)
        (d0, r0), (d1, r1) = anchors[k], anchors[k + 1]
        t = (d - d0).days / max(1, (d1 - d0).days)
        trend = r0 + (r1 - r0) * min(max(t, 0.0), 1.0)
        if d.weekday() >= 5 and last is not None:
            rate = last  # CBU rate is not changed over the weekend
        else:
            noise = noise * 0.92 + rng.gauss(0, 9.0)  # mean-reverting daily noise
            rate = round(trend + noise, 2)
        rates[d] = rate
        last = rate
    return rates


def gen_contracts(rng: random.Random, n: int, participants, rates: dict[date, float]):
    sellers = [p for p in participants if p[4] == "Продавец"]
    seller_w = list(accumulate(heavy_tail_weights(rng, len(sellers), 1.2)))
    comm_w = list(accumulate(c[8] for c in COMMODITIES))

    reg_start = date(2021, 6, 1)
    reg_end = date(2026, 10, 15)
    span = (reg_end - reg_start).days
    contracts = []
    for i in range(n):
        # registration skewed toward later years (exchange growth)
        u = rng.random() ** 0.85
        reg = reg_start + timedelta(days=int(u * span))
        valid = reg + timedelta(days=rng.choice((365, 365, 540, 730, 730, 1095)))
        c = rng.choices(COMMODITIES, cum_weights=comm_w, k=1)[0]
        (product, tnved, group, category, industry, unit, lots, p2022, _w, exp_share,
         brands, sizes, grades, types, classes, packs) = c
        seller = rng.choices(sellers, cum_weights=seller_w, k=1)[0]
        export = rng.random() < exp_share
        usd = export and rng.random() < 0.6 or (not export and rng.random() < 0.015)
        base_uzs = p2022 * price_index(reg, False) * rng.uniform(0.9, 1.1)
        if usd:
            base = round(p2022 / RATE_ANCHORS[0][1] * price_index(reg, True) * rng.uniform(0.92, 1.08), 2)
        else:
            base = round(base_uzs / 100) * 100 if base_uzs > 10_000 else round(base_uzs, 2)
        region = seller[2] if rng.random() < 0.8 else weighted(rng, REGIONS)
        address = f"{region}, {REGION_CITY[region]}, {rng.choice(STREETS)}, {rng.randint(1, 180)}"
        form = weighted(rng, CONTRACT_FORMS)
        cn = f"UZX-{reg.year}-{i + 1:05d}"
        contracts.append({
            "row": [
                cn, product, rng.choice(brands), rng.choice(sizes), rng.choice(grades), rng.choice(types),
                rng.choice(classes), tnved, group, category, industry, unit, fmt_int_spaced(rng.choice(lots)),
                CURRENCY_USD if usd else CURRENCY_UZS, fmt_money(base),
                rng.choice(("3", "5", "10", "10", "15", "20")),
                rng.choice(DELIVERY_BASES_EXP if export else DELIVERY_BASES_DOM), region, address,
                weighted(rng, AUCTION_TYPES), "Экспортный" if export else "Внутренний", form,
                str(rng.choice((3, 5, 5, 10, 10, 15, 30))),
                str(rng.choice((10, 15, 20, 30, 30, 45, 60)) + (30 if form != "Спот" else 0)),
                rng.choice(packs), seller[0], fmt_date(reg), fmt_date(valid),
            ],
            "cn": cn, "reg": reg, "valid": valid, "usd": usd, "base": base,
            "lot": None, "seller": seller[0],
            "pay_days": None, "del_days": None, "weight": min(1.0, rng.paretovariate(1.1) / 6),
        })
        # keep parsed copies of fields used for deals
        row = contracts[-1]["row"]
        contracts[-1]["lot"] = int(row[12].replace(" ", ""))
        contracts[-1]["pay_days"] = int(row[22])
        contracts[-1]["del_days"] = int(row[23])
    contracts.sort(key=lambda c: (c["reg"], c["cn"]))
    return contracts


def allocate_days(rng: random.Random, year: int, total: int) -> list[tuple[date, int]]:
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), DATA_CUTOFF)
    days = [d for d in daterange(start, end) if WEEKDAY_FACTOR[d.weekday()] > 0]
    # holidays: Jan 1, Mar 8, Mar 21 (Navruz), Sep 1, Dec 8
    holidays = {(1, 1), (3, 8), (3, 21), (5, 9), (9, 1), (10, 1), (12, 8)}
    days = [d for d in days if (d.month, d.day) not in holidays]
    n = len(days)
    weights = []
    for i, d in enumerate(days):
        trend = 0.9 + 0.2 * (i / max(1, n - 1))  # within-year growth
        weights.append(MONTH_FACTOR[d.month - 1] * WEEKDAY_FACTOR[d.weekday()] * trend
                       * rng.uniform(0.85, 1.15))
    s = sum(weights)
    raw = [w / s * total for w in weights]
    counts = [int(x) for x in raw]
    rest = total - sum(counts)
    order = sorted(range(n), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[:rest]:
        counts[i] += 1
    return list(zip(days, counts))


def pick_contract(rng: random.Random, contracts, reg_ord: list[int], d: date):
    o = d.toordinal()
    hi = bisect.bisect_right(reg_ord, o)
    lo = bisect.bisect_left(reg_ord, o - 1100)
    if hi <= lo:
        return None
    for _ in range(60):
        c = contracts[rng.randrange(lo, hi)]
        if c["valid"] >= d and rng.random() < c["weight"]:
            return c
    for _ in range(200):
        c = contracts[rng.randrange(lo, hi)]
        if c["valid"] >= d:
            return c
    for c in contracts[lo:hi]:
        if c["valid"] >= d:
            return c
    return None


def deal_time(rng: random.Random) -> str:
    # trading session 10:00-17:00 with a late-morning peak
    m = int(min(max(rng.gauss(60 * 12.3, 85), 600), 1019))
    return f"{m // 60:02d}:{m % 60:02d}:{rng.randrange(60):02d}"


def gen_deals_year(rng, year, total, contracts, reg_ord, buyers, buyer_cw, part_broker, broker_codes,
                   broker_cw, next_no):
    rows = []
    for d, cnt in allocate_days(rng, year, total):
        days_to_cutoff = (DATA_CUTOFF - d).days
        times = sorted(deal_time(rng) for _ in range(cnt))
        buyer_pick = rng.choices(buyers, cum_weights=buyer_cw, k=cnt) if cnt else []
        for j in range(cnt):
            c = pick_contract(rng, contracts, reg_ord, d)
            row = c["row"]
            usd = c["usd"]
            lot = c["lot"]
            qty = min(250, 1 + int(rng.lognormvariate(0.9, 0.95)))
            start_price = c["base"] * price_index(d, usd) / price_index(c["reg"], usd) * rng.uniform(0.96, 1.04)
            start_price = round(start_price, 2)
            auction = row[19] if rng.random() < 0.9 else weighted(rng, AUCTION_TYPES)
            if auction in ("Аукцион", "Закрытый аукцион"):
                bid = min(0.35, rng.expovariate(1 / 0.035))  # bidding increment over start price
            elif auction == "Двойной встречный аукцион":
                bid = rng.uniform(-0.03, 0.04)
            else:
                bid = rng.uniform(-0.01, 0.01)
            amount = round(qty * lot * start_price * (1 + bid), 2)

            # --- status & lifecycle dates --------------------------------
            pay_days, del_days = c["pay_days"], c["del_days"]
            r = rng.random()
            pay_date = del_date = delivered = None
            if days_to_cutoff <= 7 and r < 0.45:
                status = "Новый"
            elif r < 0.065:
                status = "Аннулирован"
            elif r < 0.085:
                status = "Ждёт оплату"  # overdue receivable
            else:
                pay_date = d + timedelta(days=rng.randint(0, pay_days))
                del_date = pay_date + timedelta(days=rng.randint(1, del_days))
                if pay_date > DATA_CUTOFF:
                    status, pay_date, del_date = "Ждёт оплату", None, None
                elif del_date > DATA_CUTOFF or r < 0.10:
                    status, del_date = "Ждёт поставку", None
                else:
                    status = "Исполнен"
                    delivered = qty
            seller = c["seller"]
            buyer = buyer_pick[j]
            sb = part_broker[seller] if rng.random() < 0.8 else rng.choices(broker_codes, cum_weights=broker_cw)[0]
            bb = part_broker[buyer] if rng.random() < 0.8 else rng.choices(broker_codes, cum_weights=broker_cw)[0]
            rows.append([
                str(next_no), fmt_date(d), times[j], auction, str(qty), fmt_money(amount), fmt_money(start_price),
                c["cn"], row[1], row[12], row[11], row[17], row[20], row[21], status, seller, buyer, sb, bb,
                fmt_date(pay_date), fmt_date(del_date), "" if delivered is None else str(delivered),
            ])
            next_no += 1
    return rows, next_no


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, default=1.0, help="row-count multiplier (e.g. 0.02 for a quick test)")
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rng = random.Random(args.seed)
    inns = InnFactory(rng)

    def done(name: str, n: int) -> None:
        p = out / name
        print(f"  {name:<18} {n:>8} rows  {p.stat().st_size / 1e6:8.2f} MB  ({time.perf_counter() - t0:5.1f}s)")

    print(f"Generating into {out} (scale={args.scale}, seed={args.seed})")
    brokers = gen_brokers(rng, inns)
    done("brokers.csv", write_csv(out / "brokers.csv", BROKERS_COLUMNS, brokers))

    participants = gen_participants(rng, inns, scaled(N_PARTICIPANTS, args.scale, 10))
    done("participants.csv", write_csv(out / "participants.csv", PARTICIPANTS_COLUMNS, participants))

    rates = gen_usd_rates(rng)
    done("usd_rates.csv", write_csv(out / "usd_rates.csv", USD_RATES_COLUMNS,
                                   ([fmt_date(d), f"{r:.2f}"] for d, r in rates.items())))

    contracts = gen_contracts(rng, scaled(N_CONTRACTS, args.scale, 20), participants, rates)
    done("contracts.csv", write_csv(out / "contracts.csv", CONTRACTS_COLUMNS, (c["row"] for c in contracts)))

    reg_ord = [c["reg"].toordinal() for c in contracts]
    broker_codes = [b[0] for b in brokers]
    broker_cw = list(accumulate(heavy_tail_weights(rng, len(broker_codes), 1.4)))
    part_broker = {p[0]: rng.choices(broker_codes, cum_weights=broker_cw)[0] for p in participants}
    buyers = [p[0] for p in participants if p[4] == "Покупатель"]
    buyer_cw = list(accumulate(heavy_tail_weights(rng, len(buyers), 1.25)))

    next_no = 1_000_001
    for year, n in DEALS_PER_YEAR.items():
        rows, next_no = gen_deals_year(rng, year, scaled(n, args.scale, 10), contracts, reg_ord, buyers,
                                       buyer_cw, part_broker, broker_codes, broker_cw, next_no)
        done(f"deals_{year}.csv", write_csv(out / f"deals_{year}.csv", DEALS_COLUMNS, rows))
    print(f"Done in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
