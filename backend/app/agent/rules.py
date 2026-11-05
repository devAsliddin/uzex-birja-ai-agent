"""Rule-based NL -> SQL engine (zero LLM calls) for Russian and Uzbek (Latin + Cyrillic).

Pipeline: normalize -> extract slots (period, region, status, product, ids, metric, grouping) ->
parameter-free SQL template over the read-only ``v_deals`` view -> deterministic answer text.
Anything not parsed with confidence returns ``None`` (caller answers "don't know").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.agent.grounding import fmt_number

ANN = "Аннулирован(Не оплачен)"
DATA_START, DATA_END = "2022-01-03", "2026-10-30"


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------
_APOS = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "´": "'", "ё": "е", "Ё": "Е"})


def norm(text: str) -> str:
    t = text.translate(_APOS).lower()
    t = t.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    return " ".join(t.split())


def esc(s: str) -> str:
    return s.replace("'", "''")


# ---------------------------------------------------------------------------
# dictionaries
# ---------------------------------------------------------------------------
MONTHS = [
    (1, r"январ|yanvar"), (2, r"феврал|fevral"), (3, r"март|mart\b|marta?\b"), (4, r"апрел|aprel"),
    (5, r"\bма[йяюе]\b|\bmay\b|\bmayda\b|\bmay oy"), (6, r"июн|iyun"), (7, r"июл|iyul"), (8, r"август|avgust"),
    (9, r"сентябр|sentabr|sentyabr"), (10, r"октябр|oktabr|oktyabr"), (11, r"ноябр|noyabr"),
    (12, r"декабр|dekabr"),
]
MONTH_NAMES = {
    "ru": ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
           "ноябрь", "декабрь"],
    "uz": ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr",
           "dekabr"],
}

REGIONS = [  # (value in deals/participants/brokers, regex)
    ("Toshkent viloyati", r"ташкентск\w* обл|toshkent viloyat|тошкент вилоят|ташкентской области|tashkent region"),
    ("Toshkent shahri", r"toshkent shahr|тошкент шаҳр|тошкент шахр|г\.? ?ташкент|город\w* ташкент|ташкент\w*|toshkent"),
    ("Andijon viloyati", r"андижан|andijon|андижон"),
    ("Buxoro viloyati", r"бухар|buxoro|бухоро"),
    ("Farg‘ona viloyati", r"ферган|farg'?ona|фарғона|фаргона"),
    ("Jizzax viloyati", r"джизак|jizzax|жиззах"),
    ("Xorazm viloyati", r"хорезм|xorazm|хоразм"),
    ("Namangan viloyati", r"наманган|namangan"),
    ("Navoiy viloyati", r"навои|navoiy|навоий"),
    ("Qashqadaryo viloyati", r"кашкадар|qashqadaryo|қашқадарё|кашкадарё"),
    ("Qoraqalpog‘iston Respublikasi", r"каракалпак|qoraqalpog|қорақалпоғ|коракалпог"),
    ("Samarqand viloyati", r"самарканд|samarqand|самарқанд"),
    ("Sirdaryo viloyati", r"сырдар|sirdaryo|сирдарё"),
    ("Surxondaryo viloyati", r"сурхандар|surxondaryo|сурхондарё"),
]

# product key -> (regex in question, contract product LIKE patterns (lowercase), label ru, label uz)
PRODUCTS = [
    ("copper", r"катод|katod|mis katod|мис катод|медн\w* катод|copper", ["%катод%"], "медный катод", "mis katod"),
    ("cotton_oil", r"хлопков\w* масл|масл\w* хлопков|paxta yog'|пахта ёғ", ["%масло хлопков%", "%хлопковое масло%"],
     "хлопковое масло", "paxta yog'i"),
    ("cotton", r"хлоп\w*[- ]сырц|хлопок[- ]сырец|хлоп(ок|ка|ку|ком|ке)\b|paxta xom|paxta\b|пахта\b", ["%хлопок%сырец%"],
     "хлопок-сырец", "paxta xomashyosi"),
    ("sunoil", r"подсолнеч|kungaboqar|кунгабоқар", ["%подсолнечн%"], "подсолнечное масло", "kungaboqar yog'i"),
    ("flour", r"\bмук[аиуе]?\b|\bun\b|\bунни\b|\bун\b", ["мука%"], "мука", "un"),
    ("wheat", r"пшениц|bug'doy|bugdoy|буғдой|бугдой", ["%пшениц%"], "пшеница", "bug'doy"),
    ("sugar", r"сахар|shakar|шакар", ["%сахар%"], "сахар", "shakar"),
    ("urea", r"карбамид|мочевин|karbamid", ["%карбамид%", "%мочевин%"], "карбамид", "karbamid"),
    ("nitrate", r"селитр|selitra", ["%селитр%"], "аммиачная селитра", "ammiakli selitra"),
    ("petrol", r"бензин|benzin|\bаи[- ]?\d\d|\bai[- ]?\d\d", ["%бензин%"], "бензин", "benzin"),
    ("diesel", r"дизел|dizel|солярк", ["%дизел%"], "дизельное топливо", "dizel yoqilg'isi"),
    ("cement", r"цемент|sement|семент", ["%цемент%"], "цемент", "sement"),
    ("lpg", r"сжижен|suyultirilgan|суюлтирилган|пропан|propan", ["%сжижен%"], "сжиженный газ", "suyultirilgan gaz"),
    ("meal", r"шрот|shrot|kunjara|кунжара", ["%шрот%"], "шрот хлопковый", "paxta shroti"),
    ("rebar", r"арматур|armatura", ["%арматур%"], "арматура", "armatura"),
    ("pe_pipe", r"труб|quvur|қувур", ["%труб%"], "трубы ПЭ", "PE quvurlar"),
    ("pe", r"полиэтилен|polietilen", ["%полиэтилен%"], "полиэтилен", "polietilen"),
    ("pp", r"полипропилен|polipropilen", ["%полипропилен%"], "полипропилен", "polipropilen"),
    ("alu", r"алюмин|alyumin|алюмин", ["%алюмин%"], "алюминиевый профиль", "alyuminiy profil"),
    ("bitumen", r"битум|bitum", ["%битум%"], "битум", "bitum"),
    ("brick", r"кирпич|g'isht|гишт|ғишт", ["%кирпич%"], "кирпич", "g'isht"),
    ("glass", r"стекл|shisha|шиша", ["%стекл%"], "стекло", "shisha"),
    ("rice", r"\bрис\w*|guruch|гуруч", ["рис%"], "рис", "guruch"),
    ("salt", r"\bсол[ьи]\b|\btuz\b|\bтуз\b", ["%соль%"], "соль", "tuz"),
    ("lumber", r"пиломатериал|yog'och|ёғоч|taxta", ["%пиломатериал%"], "пиломатериалы", "yog'och-taxta"),
    ("yarn", r"пряж|kalava|ip-kalava|калава", ["%пряж%"], "пряжа", "kalava ip"),
    ("mazut", r"мазут|mazut", ["%мазут%"], "мазут", "mazut"),
    ("gypsum", r"гипс|gips", ["%гипс%"], "гипс", "gips"),
    ("lime", r"извест|ohak|оҳак|охак", ["%извест%"], "известь", "ohak"),
    ("acid", r"серн\w* кислот|кислот\w* серн|sulfat kislota|oltingugurt kislota", ["%кислот%"], "серная кислота",
     "sulfat kislota"),
    ("soda", r"каустич|kaustik", ["%каустич%"], "каустическая сода", "kaustik soda"),
    ("water", r"вод[аы]\b|питьев|ichimlik suv|\bsuv\b", ["%вода%"], "питьевая вода", "ichimlik suvi"),
    ("feed", r"комбикорм|кормосмес|\byem\b|ozuqa", ["%корм%"], "комбикорм", "yem"),
    ("cable", r"кабел|kabel", ["%кабел%"], "кабель", "kabel"),
    ("bearing", r"подшипник|podshipnik", ["%подшипник%"], "подшипник", "podshipnik"),
    ("pvc", r"поливинилхлорид|пвх|pvx", ["%поливинилхлорид%"], "поливинилхлорид", "polivinilxlorid"),
    ("enamel", r"эмал|emal", ["%эмаль%"], "эмаль", "emal"),
    ("steel_sheet", r"лист\w* сталь|стальн\w* лист|po'lat list", ["%лист стальн%"], "лист стальной", "po'lat list"),
    ("nitrogen", r"\bазот|\bazot", ["азот%"], "азот", "azot"),
    ("argon", r"аргон|argon", ["%аргон%"], "аргон", "argon"),
]
# commodities that do NOT exist in the registry -> "don't know"
FOREIGN_GOODS = re.compile(
    r"золот|oltin|олтин|серебр|kumush|кумуш|платин|\bнефт[ьи]\b|\bneft\b|сырой нефт|xom neft|уголь|ko'mir|кўмир|"
    r"кофе|kofe|coffee|qahva|қаҳва|\bчай\b|\bchoy\b|мяс[оа]|go'sht|гўшт|молок|\bsut\b|картоф|kartoshka|природн\w* газ|tabiiy gaz|"
    r"хлопков\w* волокн|paxta tolasi|автомобил[ьяей]\b|avtomobil\b|iphone|телефон\w* аппарат|уран|uran\b|алмаз|olmos|"
    r"виноград|uzum|яблок|olma\b|лук\b|piyoz"
)
RELATIVE_TIME = re.compile(
    r"\bвчера|\bсегодня|\bзавтра|послезавтра|на прошлой неделе|на этой неделе|в этом году|в прошлом году|в следующем|"
    r"\bkecha\b|\bbugun|\bertaga|o'tgan hafta|shu hafta|joriy yil|o'tgan yil|keyingi|кеча\b|бугун|эртага|"
    r"прогноз|bashorat|kelgusi|в будущем|следующ\w* (год|месяц|недел)|keyingi (yil|oy|hafta)"
)
NO_DATA_TOPICS = re.compile(
    r"телефон|директор|руководител|rahbar|direktor|bank|банк|hisob raqam|счет[ау]? в банк|расчетн\w* сч|email|почт[аы]|"
    r"сайт|veb-?sayt|evro|euro|евро|yevro|рубл|rubl|юан|yuan|тенге|фунт|lme|london|лондон|чикаг|nyse|nasdaq|"
    r"биткоин|bitcoin|крипт|kripto|погод|ob-?havo|прогноз|prognoz|bashorat|будущ|kelajak|зарплат|maosh|прибыл|foyda|"
    r"налог|soliq|адрес компан|manzil|паспорт|pasport|возраст|yosh\w* necha|акци[ия] |dividend|дивиденд|"
    r"почему|nega|nima uchun|причин|sabab"
)

CATEGORIES = [
    ("Сельскохозяйственная продукция", r"сельскохоз|qishloq xo'jalik|қишлоқ хўжалик"),
    ("Продовольственные товары", r"продовольств|oziq-ovqat|озиқ-овқат"),
    ("Нефтепродукты", r"нефтепродукт|neft mahsulot|нефт маҳсулот"),
    ("Строительные материалы", r"строительн\w* материал|qurilish material|қурилиш материал"),
    ("Химическая продукция", r"химическ\w* продук|kimyo|кимё"),
    ("Металлопродукция", r"металлопродук|metall mahsulot|металл маҳсулот"),
    ("Полимерная продукция", r"полимер|polimer"),
    ("Промышленные товары", r"промышленн\w* товар|sanoat tovar|саноат товар"),
]
UNITS = [("тонна", r"тонн|tonna|тонна"), ("литр", r"литр|litr"), ("килограмм", r"килограмм|\bкг\b|kilogramm|\bkg\b"),
         ("метр", r"\bметр|\bmetr\b"), ("штука", r"штук|\bdona\b"), ("куб.метр", r"куб|kub"),
         ("кв.метр", r"кв\.? ?м|kvadrat")]


@dataclass
class Slots:
    years: list[int] = field(default_factory=list)
    month: int | None = None
    day: str | None = None  # ISO date
    region: str | None = None
    statuses: list[str] | None = None
    exclude_ann: bool = False
    product: str | None = None
    grade: str | None = None
    exact_name: str | None = None
    contract_type: str | None = None
    currency: str | None = None  # 'UZS'/'USD' contract filter
    out_usd: bool = False
    form: str | None = None
    trade_type: str | None = None
    category: str | None = None
    unit: str | None = None
    metric: str | None = None
    group: str | None = None
    order: str = "desc"
    top_n: int = 1
    rank_by: str = "count"
    deal_no: int | None = None
    contract_no: str | None = None
    broker: str | None = None
    inn: str | None = None
    side: str | None = None  # seller / buyer
    entity: str = "deal"
    role: str | None = None
    vat: bool = False
    reason: str = ""
    quarter: int | None = None
    share: bool = False
    vat_neg: bool = False


@dataclass
class RuleResult:
    sql: str
    basis: str
    builder: Any  # callable(columns, rows) -> answer text
    slots: Slots
    extra_sql: str | None = None


def _has(p: str, t: str) -> bool:
    return re.search(p, t) is not None


# ---------------------------------------------------------------------------
# slot extraction
# ---------------------------------------------------------------------------
def extract(q: str) -> Slots:
    t = norm(q)
    s = Slots()
    # quoted exact names
    m = re.search(r'"([^"]{2,80})"', t)
    quoted = q[m.start() + 1: m.end() - 1] if m else None
    # ids
    m = re.search(r"\bbk ?(\d{1,4})\b", t)
    if m:
        s.broker = f"BK{int(m.group(1)):03d}" if len(m.group(1)) <= 3 else f"BK{m.group(1)}"
    m = re.search(r"(?:сдел(?:к|ок)\w*|bitim\w*|битим\w*|deal)\s*(?:№|n|no\.?|номер|raqami)?\s*(\d{5,7})\b|(\d{5,7})\s*-?\s*(?:raqamli |sonli |рақамли |сонли )?(?:bitim|битим)|№\s*(\d{5,7})(?!\S*\s*(?:контракт|shartnoma))", t)
    if m:
        s.deal_no = int(next(g for g in m.groups() if g))
    m = re.search(r"(?:контракт\w*|kontrakt\w*|shartnoma\w*|шартнома\w*|договор\w*|карточк\w* контракт\w*)\s*(?:№|n|номер|raqami|raqamli)?\s*(\d{5,7})\b|(\d{5,7})\s*-?\s*(?:raqamli |sonli |рақамли )?(?:shartnoma|шартнома|kontrakt|контракт)|№\s*(\d{5,7})\s*(?:контракт|shartnoma|kontrakt)", t)
    if m:
        s.contract_no = next(g for g in m.groups() if g)
        if s.deal_no and str(s.deal_no) == s.contract_no:
            s.deal_no = None
    m = re.search(r"(?<!\d)(\d{9})(?!\d)", t)
    if m:
        s.inn = m.group(1)
    # dates ("по состоянию на 30.10.2026" / "30.10.2026 holatiga" = as-of, not a filter)
    t_dates = re.sub(r"по состоянию на \S+|на конец \S+|\S+ (holatiga|ҳолатига)( ko'ra)?", " ", t)
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", t_dates)
    if m:
        s.day = f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    else:
        for num, pat in MONTHS:
            m = re.search(r"\b(\d{1,2})[- ]?(?:" + pat + r")\w*,?\s*(\d{4})|(\d{4})[- ]?(?:йил|yil|год|г\.?)?\w*\s*(\d{1,2})[- ]?(?:" + pat + r")", t_dates)
            if m:
                if m.group(1):
                    s.day = f"{int(m.group(2)):04d}-{num:02d}-{int(m.group(1)):02d}"
                else:
                    s.day = f"{int(m.group(3)):04d}-{num:02d}-{int(m.group(4)):02d}"
                break
    if not s.day:
        for num, pat in MONTHS:
            if _has(pat, t):
                s.month = num
                break
    mq = re.search(r"\b(1|2|3|4|i{1,3}|iv|перв\w*|втор\w*|трет\w*|четв[её]рт\w*|birinchi|ikkinchi|uchinchi|to'rtinchi)"
                   r"[- ]?(?:й|ий|ый|-?chi)?\s*(?:квартал\w*|chorak\w*|чорак\w*|kvartal\w*)", t_dates)
    if mq and not s.day:
        w = mq.group(1)
        s.quarter = {"1": 1, "i": 1, "2": 2, "ii": 2, "3": 3, "iii": 3, "4": 4, "iv": 4}.get(w) or (
            1 if w.startswith(("перв", "birin")) else 2 if w.startswith(("втор", "ikki")) else
            3 if w.startswith(("трет", "uchin")) else 4)
        s.month = None
    if _has(r"дол[яию]\b|процент|\b%|foiz|ulush|улуш|фоиз", t):
        s.share = True
    years = [int(y) for y in re.findall(r"(?<![\d.])((?:19|20)\d\d)(?![\d])", t_dates)]
    years += [2000 + int(y) for y in re.findall(r"(?<![\d.])(\d\d)\s*-?\s*(?:год\w*|г\.|yil\w*|йил\w*)", t_dates)]
    if s.day:
        years = [int(s.day[:4])]
    s.years = sorted(set(years))
    # region
    for val, pat in REGIONS:
        if _has(pat, t):
            s.region = val
            break
    # statuses
    if _has(r"без (уч[её]та )?аннул|кроме аннул|исключ\w* аннул|не (были |был )?аннулир|за вычетом аннул|"
            r"bekor qilinganlar(siz|ni hisobga olmaganda|dan tashqari)|bekor qilinmagan|бекор қилинганлар(сиз|ни)|"
            r"без отмен|состоявш|amalga oshgan|hisobga olinmasin|hisobga olinmagan|hisobga olmasdan|"
            r"аннулир\w*\)?\s*(не считать|не учитыв)|не считая аннул|бекор қилинганларсиз", t):
        s.exclude_ann = True
    if _has(r"(не оплачен\w*|to'lanmagan|тўланмаган).*(не аннул|не отмен|bekor (ham )?qilinmagan)", t):
        s.statuses = ["Ждёт оплату", "Заключен", "Новый", "Не подписан"]
        s.exclude_ann = False
    elif _has(r"частичн|qisman|қисман", t):
        s.statuses = ["Исполнен(Частично)"]
    elif _has(r"жд[её]т оплат|ожида\w* оплат|to'lov(ni)? kut|тўлов(ни)? кут", t):
        s.statuses = ["Ждёт оплату"]
    elif _has(r"(оплачен|to'langan|тўланган)\w*,? ?(но|lekin|ammo)?.{0,25}(не постав|yetkazilmagan|етказилмаган)|статус\w* \"?оплачен", t):
        s.statuses = ["Оплачен"]
    elif not s.exclude_ann and _has(r"аннулир|bekor qilin|бекор қилин|отмен[её]н", t):
        s.statuses = [ANN]
    elif _has(r"не подписан|imzolanmagan|имзоланмаган", t):
        s.statuses = ["Не подписан"]
    elif _has(r"статус\w* \"?нов|\"новый\"|\byangi\b (holat|статус)", t):
        s.statuses = ["Новый"]
    elif _has(r"\"заключен\"|статус\w* \"?заключен", t):
        s.statuses = ["Заключен"]
    elif _has(r"(полностью )?исполнен\w*(?! \(?частич)|to'liq bajarilgan|bajarilgan|бажарилган", t) and not _has(
            r"сдел(?:к|ок)\w* исполн\w* с нарушен", t):
        if _has(r"исполнен|bajarilgan|бажарилган", t) and not _has(r"срок|muddat", t):
            s.statuses = ["Исполнен"]
    # contract type / currency
    if _has(r"экспорт|eksport|экспорт", t):
        s.contract_type = "Экспортный"
    elif _has(r"внутренн|ichki|ички", t):
        s.contract_type = "Внутренний"
    if _has(r"so'mdagi|сумов(ых|ые|ой|ым)|в узбекских сум|сўмдаги|сумдаги", t) and not s.contract_type:
        s.currency = "UZS"
    if _has(r"в долларах|в usd|в долл|dollarda|долларда|\busd\b|aqsh dollar|долл\.? сша|dollar", t):
        s.out_usd = True
    if _has(r"(контракт|shartnoma|шартнома)\w* (в )?(доллар|aqsh|usd)|(доллар|dollar|usd)\w* .{0,20}(контракт|shartnoma)", t):
        s.currency = "USD"
    # form / trade type
    if _has(r"\bспот|\bspot", t) and _has(r"форвард|forvard|forward", t):
        s.form = None
    elif _has(r"\bспот|\bspot", t):
        s.form = "Спот"
    elif _has(r"форвард|forvard|forward", t):
        s.form = "Форвард"
    elif _has(r"фьюч|fyuch|futures|fyuchrs|фючерс", t):
        s.form = "Фьючерс"
    if _has(r"английск|ingliz", t):
        s.trade_type = "Английский аукцион"
    elif _has(r"обратн\w* аукцион|teskari auksion", t):
        s.trade_type = "Обратный аукцион"
    elif _has(r"двусторон|ikki tomonlama", t):
        s.trade_type = "Двусторонний аукцион"
    for val, pat in CATEGORIES:
        if _has(pat, t):
            s.category = val
            break
    # product
    if quoted and not _has(r"ждёт|ждет|оплачен|исполнен|заключен|новый|подписан", norm(quoted)):
        s.exact_name = quoted.strip()
    for key, pat, *_ in PRODUCTS:
        if _has(pat, t):
            s.product = key
            break
    m = re.search(r"(?:аи|ai)[- ]?(80|92|95|98)", t)
    if m:
        s.grade = f"аи-{m.group(1)}"
        s.product = s.product or "petrol"
    for val, pat in UNITS:
        if _has(pat, t):
            s.unit = val
            break
    # side
    if _has(r"на стороне продав|продав\w* стороне|sotuvchi tomon|sotuvchi brokerlari|сотувчи томон|брокер\w* продав|sotuvchining brokeri|"
            r"сотувчининг брокери", t):
        s.side = "seller"
    elif _has(r"на стороне покуп|покуп\w* стороне|xaridor tomon|харидор томон|брокер\w* покуп|xaridorning brokeri|xaridor brokerlari|"
            r"xaridor brokeri|харидор брокер", t):
        s.side = "buyer"
    return s


def _metric(t: str, s: Slots) -> None:
    """Decide metric / grouping from the normalized question."""
    count_w = (r"сколько|скок|skolko|nechta|нечта|количеств|число|qancha bitim|қанча битим|канча битим|necha|неча\b|\bsoni\b|"
               r"\bсони\b")
    sum_w = (r"оборот|сумм|aylanma|айланма|summa|сумма|savdo hajmi|савдо ҳажми|объ[её]м торгов|на какую сумму|"
             r"потратил|выручк|savdo summasi|qancha pul|so'mda qancha|qiymat|so'mlik|сўмлик|qancha so'm|necha so'm|"
             r"dollarda qancha|в долларах|сколько сум")
    top_w = (r"какой|какая|какое|какие|кто|qaysi|қайси|kim\b|ким\b|назов|топ|\btop\b|eng ko'p|энг кўп|больше всего|лидер|"
             r"наибольш|eng katta|eng yirik|энг йирик|крупнейш|самы[йм]|самая|eng kam|меньше всего|наименьш|eng kichik")
    groups = [
        ("broker", r"брокер|broker"),
        ("region", r"регион|област|viloyat|вилоят|hudud|ҳудуд|склад"),
        ("category", r"категори|kategoriya|toifa|тоифа"),
        ("industry", r"отрасл|soha\b|тармоқ"),
        ("product", r"наименовани|как(ой|ие|ая|ого) товар|товар\w* (с наибольш|лидер)|qaysi (tovar|mahsulot)|"
                    r"tovar nomi|топ.{0,12}товар|eng ko'p sotilgan (tovar|mahsulot)"),
        ("seller", r"продав|sotuvchi|сотувчи|поставщик|кто прода|продал\w*|eng ko'p sotgan|ko'p sotgan|sotgan kompaniya"),
        ("buyer", r"покупател|xaridor|харидор|клиент|купил\w*|закупил\w*|потратил|sotib olgan|xarid qilgan|харид қилган"),
        ("trade_type", r"тип\w* торг|вид\w* торг|savdo turi|auksion turi"),
        ("contract_form", r"форм\w* контракт|shartnoma shakli"),
        ("year", r"в каком году|qaysi yil|қайси йил|по годам|yillar bo'yicha"),
        ("month", r"в каком месяце|qaysi oy|қайси ой|по месяцам|oylar bo'yicha"),
    ]
    asc = _has(r"eng kam|меньше всего|наименьш|eng kichik|самый маленьк|minimal", t)
    # explicit special metrics first
    if (_has(r"курс|kurs", t) and _has(r"доллар|dollar|usd|\$", t) or _has(r"^(какой )?курс|kursi? qancha", t)) and not _has(
            r"сдел(?:к|ок)|bitim|битим|оборот|aylanma|summa|сумм|по курсу|kurs bo'yicha|kursi bo'yicha", t):
        s.metric = "rate"
        return
    if _has(r"ни разу не|ни в одной сдел(?:к|ок)|hech (qanday|bir) bitim|hech qachon", t):
        s.metric = "never_traded"
        s.entity = "participant"
        return
    if _has(r"нарушени\w* срок|просроч|с опозданием|позже срок|kechik|muddatidan kech|кечик|сверх срок|с задержк", t):
        s.metric = "late"
        return
    if _has(r"недопостав|не допостав|yetkazilmagan lot|yetkazib berilmagan lot|недопоставлен|yetkazilmay qolgan|"
            r"етказилмай қолган|не поставлен\w* лот", t):
        s.metric = "undelivered_lots"
        return
    if _has(r"(дн(ей|я|ях)|день|kun)\b.*(оплат|to'lov|to'la)|(оплат|to'lov|to'la).*\b(дн(ей|я|ях)|день|kun)\b", t):
        s.metric = "pay_days_max" if _has(r"долг|максим|eng uzoq|eng ko'p|наибольш", t) else "pay_days_avg"
        return
    if _has(r"один и тот же брокер|тот же брокер|bir xil broker|одинаков\w* брокер|бир хил брокер|same broker", t):
        s.metric = "same_broker"
        return
    if s.inn and not s.side:
        if _has(r"потрат|купил|закупил|sotib ol|xarid qil|как покупател|xaridor sifatida", t):
            s.side = "buyer"
        elif _has(r"продал|sotgan|как продав|sotuvchi sifatida", t):
            s.side = "seller"
    if s.share and _has(sum_w, t):
        s.rank_by = "sum"
    if s.share and (s.statuses or s.contract_type or s.form or s.trade_type or s.region or s.product or s.category
                    or s.currency or s.exclude_ann):
        s.metric = "share"
        return
    # entity counts
    if _has(r"брокер\w* (контор|идор)|брокерлик|broker(lik)? idora|сколько брокер|nechta broker|brokerlar soni|"
            r"количество брокер", t) and _has(count_w, t):
        s.entity, s.metric = "broker", "count_entity"
        return
    if _has(r"(контракт|shartnoma|шартнома|карточ)", t) and _has(count_w, t) and not s.contract_no and not _has(
            r"сдел(?:к|ок)|bitim|битим", t):
        s.entity, s.metric = "contract", "count_entity"
        return
    if _has(r"участник|ishtirokchi|иштирокчи|компани|kompaniya|компания|плательщик|to'lovchi|продавц|sotuvchi korxona|"
            r"sotuvchi kompaniya|покупател", t) and _has(count_w + r"|ro'yxatda", t) and not _has(
            r"сдел(?:к|ок)|bitim|битим|оборот|aylanma", t) and not s.inn and not _has(sum_w, t):
        s.entity, s.metric = "participant", "count_entity"
        if _has(r"ндс|qqs|ққс|nds", t):
            s.vat = True
            if _has(r"не являю|не плат|не явл|to'lovchisi emas|to'lamaydi|тўловчиси эмас|emas", t):
                s.role = s.role or None
                s.vat_neg = True
        if _has(r"продав|sotuvchi|сотувчи", t):
            s.role = "Продавец"
        elif _has(r"покупател|xaridor|харидор", t):
            s.role = "Покупатель"
        return
    if s.deal_no or s.contract_no or (s.broker and not _has(count_w + "|" + sum_w, t)) or (
            s.inn and not _has(count_w + "|" + sum_w, t)):
        s.metric = "lookup"
        return
    # price / volume
    if _has(r"цен\w* за|за (одну |1 )?(тонн|кг|литр|единиц|метр)|стоит\w*|стоил\w*|narx|нарх|средневзвеш|o'rtacha tortilgan|bir tonna|"
            r"бир тонна|стоил\w* (тонн|литр|кг)|стоимост\w* (тонн|литр)", t):
        s.metric = "unit_price"
        return
    if _has(r"медиан|mediana|медиана", t):
        s.metric = "median"
        return
    if _has(r"средн\w* (количеств|числ)\w* лот|в среднем.{0,30}лот|o'rtacha.{0,30}lot|лот\w*.{0,20}в среднем", t):
        s.metric = "avg_lots"
        return
    if s.unit and _has(r"сколько|necha|nechta|неча|қанча|qancha|объ[её]м|hajm|продано|sotilgan|сотилган|jami", t) and not _has(
            r"сдел(?:к|ок)|bitim|битим", t.split(s.unit[:4])[0][-25:] if False else "zz"):
        if _has(r"тонн|tonna|литр|litr|килограмм|kilogramm|\bкг\b|куб|kub|метр|metr", t) and not _has(
                r"сколько сделок|nechta bitim", t):
            s.metric = "volume"
            return
    if _has(r"средн|o'rtacha|ўртача|в среднем", t) and _has(sum_w + r"|сдел(?:к|ок)|bitim", t):
        s.metric = "avg_amount"
        return
    # extreme single deal
    deal_ext = _has(r"(крупн|наибольш|максимальн|самая больш|eng (katta|yirik)|энг (катта|йирик)|самая мелк|наименьш|"
                    r"минимальн|eng kichik|энг кичик)\w*.{0,30}(сдел(?:к|ок)|bitim|битим)|(сдел(?:к|ок)|bitim)\w*.{0,30}(крупн|eng katta|eng kichik)|"
                    r"(сдел(?:к|ок)|bitim)\w* .{0,30}(максимал|минимал)", t)
    grp = None
    for g, pat in groups:
        if _has(pat, t):
            grp = g
            break
    if deal_ext and grp in (None, "product") and not _has(
            r"какой (брокер|покупател|продав|регион)|числ\w* сдел|количеств\w* сдел|eng ko'p bitim|nechta|назов|"
            r"наименовани|популярн|\bтри\b|uchta|топ|top", t):
        s.metric = "min_deal" if _has(r"мелк|наименьш|минимал|kichik|кичик", t) else "max_deal"
        return
    if (grp == "broker" and s.broker) or (grp in ("seller", "buyer") and s.inn):
        grp = None  # the named broker/company is a filter, not a ranking
    is_top = _has(top_w, t)
    if grp == "year" or grp == "month":
        is_top = True
    if grp and is_top and not (grp in ("seller", "buyer") and _has(count_w, t) and not _has(
            r"больше всего|eng ko'p|лидер|qaysi|какой|кто|kim", t)):
        s.metric = "top"
        s.group = grp
        s.order = "asc" if asc else "desc"
        m = re.search(r"\b(\d{1,2})\b\s*(?:наименован|товар|брокер|регион|компан|ta\b|та\b|tovar|kompaniya)|топ[- ]?(\d{1,2})|top[- ]?(\d{1,2})", t)
        if m:
            s.top_n = int(next(g for g in m.groups() if g))
        elif _has(r"\bтри\b|uchta|учта|\bтр[её]х\b", t):
            s.top_n = 3
        elif _has(r"\bпять\b|beshta|бешта", t):
            s.top_n = 5
        elif _has(r"десят|o'nta", t):
            s.top_n = 10
        if _has(r"больше всего сделок|eng ko'p bitim|по количеству|по числу|числу сделок|популярн|eng ko'p.{0,20}bitim|"
                r"энг кўп битим|nechta bitim|most deals|частот|ko'p sotilgan", t) and not _has(sum_w, t.replace("сделок", "")):
            s.rank_by = "count"
        elif _has(sum_w + r"|eng yirik|крупнейш|потрат|купил\w* больше|продал\w* больше|ko'p sotib olgan|ko'p sotgan|"
                  r"ko'p xarid", t):
            s.rank_by = "sum"
        else:
            s.rank_by = "count"
        if grp == "seller" and not _has(r"брокер|broker", t):
            s.group = "seller"
        return
    if _has(sum_w, t) and not _has(r"сколько сделок|nechta bitim", t):
        s.metric = "sum"
        return
    if _has(count_w + r"|прошло|было|bo'lgan|tuzilgan|тузилган|бўлган", t) or s.day:
        s.metric = "count"
        return


def parse(question: str, prev: Slots | None = None) -> tuple[Slots | None, str]:
    """Return (slots, reason). slots None => don't know."""
    t = norm(question)
    if NO_DATA_TOPICS.search(t) and not _has(r"курс|kurs", t) or (
            _has(r"курс|kurs", t) and _has(r"евро|evro|euro|yevro|рубл|rubl|юан|yuan", t)):
        return None, "topic"
    if FOREIGN_GOODS.search(t):
        return None, "unknown_product"
    if RELATIVE_TIME.search(t):
        return None, "future" if _has(r"завтра|ertaga|эртага|прогноз|bashorat|следующ|keyingi|kelgusi|будущ", t) \
            else "relative"
    s = extract(question)
    _metric(t, s)
    if s.metric is None and prev is not None:
        # follow-up: carry over previous slots, replace what the new question mentions
        merged = replace(prev)
        for f in ("years", "month", "day", "region", "statuses", "product", "grade", "contract_type", "currency",
                  "form", "category", "unit", "side", "broker", "inn", "exact_name"):
            v = getattr(s, f)
            if v:
                setattr(merged, f, v)
                if f == "years":
                    merged.month = s.month
                    merged.day = s.day
        if _has(r"eng kam|меньше|наименьш|eng kichik|минимал|kami", t):
            merged.order = "asc"
            if merged.metric == "max_deal":
                merged.metric = "min_deal"
        elif _has(r"eng ko'p|больше|наибольш|eng katta|максимал", t):
            merged.order = "desc"
            if merged.metric == "min_deal":
                merged.metric = "max_deal"
        if _has(r"без учета аннул|bekor qilinganlarsiz", t):
            merged.exclude_ann = True
        s = merged
    if s.metric is None:
        return None, "no_metric"
    if s.quarter and s.years:
        s.month = None
    if not supported(s):
        return None, "unused_slot"
    used = {str(x) for x in (s.deal_no, s.contract_no, s.inn) if x}
    for num in re.findall(r"(?<![\d.])\d{5,}(?![\d.])", t.replace(" ", "")):
        if num not in used and not any(num in u or u in num for u in used):
            return None, "unused_slot"
    # validity of the period
    for y in s.years:
        if y < 2022 or y > 2026:
            return None, "period"
    if s.day and (s.day < "2022-01-01" or s.day > "2026-10-31"):
        return None, "period"
    if s.years and s.month and (s.years[-1], s.month) > (2026, 10):
        return None, "period"
    if s.metric != "rate" and s.day and s.day > DATA_END:
        return None, "period"
    return s, ""


# filters each template can honour; a slot present in the question but not honoured => refuse
_DEAL_FILTERS = {"years", "month", "day", "quarter", "region", "statuses", "exclude_ann", "product", "grade",
                 "exact_name", "contract_type", "currency", "form", "trade_type", "category", "broker", "inn", "side",
                 "unit", "out_usd"}
_SUPPORTED = {
    "count_entity:broker": {"region"},
    "count_entity:participant": {"region"},
    "count_entity:contract": {"currency", "contract_type", "form", "years", "region", "product", "out_usd"},
    "rate": {"years", "month", "day", "out_usd", "currency"},
    "never_traded": set(),
    "lookup": _DEAL_FILTERS,
}


def present_slots(s: Slots) -> set[str]:
    out = set()
    for f in _DEAL_FILTERS:
        v = getattr(s, f)
        if v not in (None, False, [], ""):
            out.add(f)
    return out


def supported(s: Slots) -> bool:
    key = s.metric if s.metric != "count_entity" else f"count_entity:{s.entity}"
    allowed = _SUPPORTED.get(key)
    if allowed is None:
        if s.metric == "top" and s.group in ("year",) and s.years and len(s.years) == 1:
            return False  # "which year" with one year fixed is contradictory
        return True
    extra = present_slots(s) - allowed - {"unit", "side", "out_usd"}
    return not extra
