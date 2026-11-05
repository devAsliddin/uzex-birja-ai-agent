"""Region normalisation.

Brokers/participants/deals use Uzbek Latin names ("Toshkent viloyati"), while
contracts use Russian ones ("Ташкентская область"). Values are stored as-is;
this module maps both forms to one canonical Uzbek Latin key for filtering and
analytics.
"""

from __future__ import annotations

RU_TO_UZ: dict[str, str] = {
    "г. Ташкент": "Toshkent shahri",
    "Ташкентская область": "Toshkent viloyati",
    "Самаркандская область": "Samarqand viloyati",
    "Наманганская область": "Namangan viloyati",
    "Бухарская область": "Buxoro viloyati",
    "Ферганская область": "Farg‘ona viloyati",
    "Хорезмская область": "Xorazm viloyati",
    "Кашкадарьинская область": "Qashqadaryo viloyati",
    "Навоийская область": "Navoiy viloyati",
    "Сырдарьинская область": "Sirdaryo viloyati",
    "Андижанская область": "Andijon viloyati",
    "Сурхандарьинская область": "Surxondaryo viloyati",
    "Джизакская область": "Jizzax viloyati",
    "Республика Каракалпакстан": "Qoraqalpog‘iston Respublikasi",
}
UZ_TO_RU = {v: k for k, v in RU_TO_UZ.items()}

_APOS = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "´": "'"})


def _key(value: str) -> str:
    return " ".join(value.translate(_APOS).casefold().split())


_LOOKUP: dict[str, str] = {}
for _ru, _uz in RU_TO_UZ.items():
    _LOOKUP[_key(_ru)] = _uz
    _LOOKUP[_key(_uz)] = _uz


def canonical_region(value: str | None) -> str | None:
    """Return the canonical Uzbek Latin region name (unknown values unchanged)."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return _LOOKUP.get(_key(v), v)


def region_variants(value: str | None) -> list[str]:
    """All stored spellings (Latin, Russian, apostrophe variants) of a region."""
    canon = canonical_region(value)
    if canon is None:
        return []
    out = {canon, value.strip() if value else canon}
    ru = UZ_TO_RU.get(canon)
    if ru:
        out.add(ru)
    for ch in ("'", "ʻ", "’", "`"):
        out.add(canon.replace("‘", ch))
    return sorted(out)
