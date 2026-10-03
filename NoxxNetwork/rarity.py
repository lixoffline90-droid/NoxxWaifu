"""Central rarity configuration for the Waifu catcher.

Rarity probabilities are global: every group uses the same probability table.
The event system is intentionally not included here yet.
"""

from NoxxNetwork import db

RARITIES = {
    1: ("⚪", "Common"),
    2: ("🌟", "Galaxies"),
    3: ("🌤️", "Summer"),
    4: ("🍬", "Galactic"),
    5: ("🎄", "Christmas"),
    6: ("🎨", "Holi edition"),
    7: ("🐦‍🔥", "Marvelous"),
    8: ("💮", "Exclusive"),
    9: ("🔖", "Manga rush"),
    10: ("🔮", "Mythical"),
    11: ("🛖", "Tribe"),
    12: ("🛷", "X-Mas"),
    13: ("🟡", "Legendary"),
    14: ("🟢", "Medium"),
    15: ("🟣", "Rare"),
    16: ("🧣", "Winters"),
    17: ("🪁", "Skyrise"),
    18: ("🪔", "Diwali edition"),
    19: ("🪢", "Corrupted"),
    20: ("🪼", "Exotic"),
    21: ("🫧", "Special"),
}

# Distinct defaults. They are weights, so they do not have to total exactly 100.
# Owners can change any one with /setrarity <number> <probability>.
DEFAULT_PROBABILITIES = {
    1: 34.0,
    2: 8.0,
    3: 3.0,
    4: 2.0,
    5: 1.5,
    6: 1.5,
    7: 1.0,
    8: 4.0,
    9: 1.0,
    10: 3.0,
    11: 1.0,
    12: 1.0,
    13: 10.0,
    14: 12.0,
    15: 10.0,
    16: 1.0,
    17: 1.0,
    18: 1.0,
    19: 0.5,
    20: 1.0,
    21: 2.5,
}

# Compatibility aliases for characters uploaded before the 21-rarity system.
LEGACY_TO_NEW = {
    "⚪ Common": "⚪ Common",
    "🟣 Rare": "🟣 Rare",
    "🟡 Legendary": "🟡 Legendary",
    "🟢 Medium": "🟢 Medium",
    "💮 special edition": "💮 Exclusive",
    "💮 Special edition": "💮 Exclusive",
    "🔮 premium edition": "🔮 Mythical",
    "🔮 Premium edition": "🔮 Mythical",
    "🎗️ Supreme": "🐦‍🔥 Marvelous",
}


def rarity_text(number: int) -> str:
    emoji, name = RARITIES[int(number)]
    return f"{emoji} {name}"


def rarity_symbol(value) -> str:
    """Return only the rarity emoji for a stored rarity string or number."""
    if value is None:
        return "⚪"
    text = str(value).strip()
    for emoji, name in RARITIES.values():
        if text == f"{emoji} {name}" or text == name:
            return emoji
    if text in LEGACY_TO_NEW:
        return LEGACY_TO_NEW[text].split(" ", 1)[0]
    # Prefer a stored leading emoji for unknown/new custom values.
    return text.split()[0] if text and not text[0].isalnum() else "⚪"


def rarity_name(value) -> str:
    if value is None:
        return "Common"
    text = str(value).strip()
    if text in LEGACY_TO_NEW:
        text = LEGACY_TO_NEW[text]
    for emoji, name in RARITIES.values():
        if text == f"{emoji} {name}" or text == name:
            return name
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) == 2 else text


def normalize_rarity(value) -> str:
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        number = int(value)
        if number in RARITIES:
            return rarity_text(number)
    text = str(value).strip() if value is not None else ""
    return LEGACY_TO_NEW.get(text, text or rarity_text(1))


async def get_probability_table():
    doc = await db.rarity_settings.find_one({"_id": "global"})
    probabilities = dict(DEFAULT_PROBABILITIES)
    if doc:
        for key, value in doc.get("probabilities", {}).items():
            try:
                number = int(key)
                if number in RARITIES and float(value) >= 0:
                    probabilities[number] = float(value)
            except (TypeError, ValueError):
                continue
    return probabilities


async def set_probability(number: int, probability: float):
    await db.rarity_settings.update_one(
        {"_id": "global"},
        {"$set": {f"probabilities.{int(number)}": float(probability)}},
        upsert=True,
    )
