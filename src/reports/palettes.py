"""Rotating record-label color palettes for YTM-DL Editorial Zine HTML emails."""

import re
from typing import TypedDict

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ISO_WEEK_RE = re.compile(r"\b\d{4}-W(\d{2})\b")
_ISO_MONTH_RE = re.compile(r"\b\d{4}-(\d{2})\b")
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAME_RE = re.compile(r"\b(" + "|".join(_MONTH_NAMES) + r")\s+\d{4}\b", re.IGNORECASE)


class EmailTheme(TypedDict):
    """Color token schema for an Editorial Zine / Vinyl OBI email palette."""

    id: str
    name: str
    inspiration: str
    outer_bg: str
    card_bg: str
    obi_bg: str
    callout_bg: str
    footer_bg: str
    border: str
    primary: str
    cta_bg: str
    cta_text: str
    secondary: str
    link: str
    code_fg: str
    code_bg: str
    text_primary: str
    text_body: str
    text_italic: str
    text_muted: str
    callout_accents: list[str]


EMAIL_THEMES: list[EmailTheme] = [
    {
        "id": "crimson_wax",
        "name": "01 · Crimson Wax",
        "inspiration": "Impulse! / Red-Label Jazz",
        "outer_bg": "#090b10",
        "card_bg": "#0e1219",
        "obi_bg": "#131924",
        "callout_bg": "#151c28",
        "footer_bg": "#0a0d13",
        "border": "#262f3f",
        "primary": "#f43f5e",
        "cta_bg": "#e11d48",
        "cta_text": "#ffffff",
        "secondary": "#e3b341",
        "link": "#6cb6ff",
        "code_fg": "#79c0ff",
        "code_bg": "rgba(110,118,129,0.22)",
        "text_primary": "#f0f6fc",
        "text_body": "#d8e0e8",
        "text_italic": "#cbd5e1",
        "text_muted": "#94a3b8",
        "callout_accents": ["#e3b341", "#f43f5e", "#6cb6ff"],
    },
    {
        "id": "blue_note_midnight",
        "name": "02 · Blue Note Midnight",
        "inspiration": "1960s Reid Miles Cobalt & Ochre",
        "outer_bg": "#060c16",
        "card_bg": "#0b1524",
        "obi_bg": "#101e33",
        "callout_bg": "#122238",
        "footer_bg": "#08101c",
        "border": "#203552",
        "primary": "#38bdf8",
        "cta_bg": "#0284c7",
        "cta_text": "#ffffff",
        "secondary": "#fbbf24",
        "link": "#7dd3fc",
        "code_fg": "#bae6fd",
        "code_bg": "rgba(56,189,248,0.16)",
        "text_primary": "#f0f9ff",
        "text_body": "#d6e4f0",
        "text_italic": "#cbd5e1",
        "text_muted": "#93adc8",
        "callout_accents": ["#38bdf8", "#fbbf24", "#818cf8"],
    },
    {
        "id": "etiopiques_amber",
        "name": "03 · Éthiopiques Amber",
        "inspiration": "Addis Ababa Analog / Espresso & Honey Gold",
        "outer_bg": "#0e0a07",
        "card_bg": "#16110d",
        "obi_bg": "#1f1712",
        "callout_bg": "#221913",
        "footer_bg": "#110d0a",
        "border": "#382b20",
        "primary": "#f59e0b",
        "cta_bg": "#b45309",
        "cta_text": "#ffffff",
        "secondary": "#fb923c",
        "link": "#fcd34d",
        "code_fg": "#fde68a",
        "code_bg": "rgba(245,158,11,0.16)",
        "text_primary": "#fefce8",
        "text_body": "#e7dfd5",
        "text_italic": "#d6ccc2",
        "text_muted": "#a89988",
        "callout_accents": ["#f59e0b", "#fb7185", "#34d399"],
    },
    {
        "id": "dub_studio_forest",
        "name": "04 · Dub Studio Forest",
        "inspiration": "King Tubby / Krautrock Moss & VU Gold",
        "outer_bg": "#060e0b",
        "card_bg": "#0b1713",
        "obi_bg": "#10221c",
        "callout_bg": "#132720",
        "footer_bg": "#08120e",
        "border": "#213d33",
        "primary": "#34d399",
        "cta_bg": "#059669",
        "cta_text": "#ffffff",
        "secondary": "#eab308",
        "link": "#6ee7b7",
        "code_fg": "#a7f3d0",
        "code_bg": "rgba(52,211,153,0.15)",
        "text_primary": "#ecfdf5",
        "text_body": "#d3e5dd",
        "text_italic": "#c2d8ce",
        "text_muted": "#8da99d",
        "callout_accents": ["#34d399", "#eab308", "#38bdf8"],
    },
    {
        "id": "cosmic_plum",
        "name": "05 · Cosmic Plum",
        "inspiration": "Warp Records / Late-Night Modular Synth",
        "outer_bg": "#0b0813",
        "card_bg": "#130e20",
        "obi_bg": "#1b142d",
        "callout_bg": "#1f1733",
        "footer_bg": "#0e0a18",
        "border": "#32264d",
        "primary": "#c084fc",
        "cta_bg": "#7c3aed",
        "cta_text": "#ffffff",
        "secondary": "#f472b6",
        "link": "#d8b4fe",
        "code_fg": "#e9d5ff",
        "code_bg": "rgba(192,132,252,0.16)",
        "text_primary": "#faf5ff",
        "text_body": "#dfd7eb",
        "text_italic": "#d1c6e3",
        "text_muted": "#9f92b8",
        "callout_accents": ["#c084fc", "#f472b6", "#2dd4bf"],
    },
    {
        "id": "ecm_nordic_slate",
        "name": "06 · ECM Nordic Slate",
        "inspiration": "Oslo Studio Minimalist Graphite & Glacier Frost",
        "outer_bg": "#090b0d",
        "card_bg": "#111519",
        "obi_bg": "#171d23",
        "callout_bg": "#1a2128",
        "footer_bg": "#0c1014",
        "border": "#2b3642",
        "primary": "#67e8f9",
        "cta_bg": "#0e7490",
        "cta_text": "#ffffff",
        "secondary": "#cbd5e1",
        "link": "#a5f3fc",
        "code_fg": "#cffafe",
        "code_bg": "rgba(103,232,249,0.14)",
        "text_primary": "#f8fafc",
        "text_body": "#dce4ec",
        "text_italic": "#cbd5e1",
        "text_muted": "#94a3b8",
        "callout_accents": ["#67e8f9", "#cbd5e1", "#818cf8"],
    },
    {
        "id": "bordeaux_velvet",
        "name": "07 · Bordeaux Velvet",
        "inspiration": "1970s Stax Soul / Oxblood Lounge & Antique Brass",
        "outer_bg": "#110709",
        "card_bg": "#1b0d11",
        "obi_bg": "#251218",
        "callout_bg": "#29151c",
        "footer_bg": "#14090c",
        "border": "#45222d",
        "primary": "#fb7185",
        "cta_bg": "#be123c",
        "cta_text": "#ffffff",
        "secondary": "#facc15",
        "link": "#fda4af",
        "code_fg": "#fecdd3",
        "code_bg": "rgba(251,113,133,0.16)",
        "text_primary": "#fff1f2",
        "text_body": "#e8d5d8",
        "text_italic": "#d9c2c6",
        "text_muted": "#b2949a",
        "callout_accents": ["#fb7185", "#facc15", "#f97316"],
    },
    {
        "id": "pacific_cumbia_teal",
        "name": "08 · Pacific Cumbia Teal",
        "inspiration": "Soundway Tropical Crate / Lagoon & Mango",
        "outer_bg": "#050e11",
        "card_bg": "#09191f",
        "obi_bg": "#0e242c",
        "callout_bg": "#112932",
        "footer_bg": "#071317",
        "border": "#1e424f",
        "primary": "#2dd4bf",
        "cta_bg": "#0f766e",
        "cta_text": "#ffffff",
        "secondary": "#fb923c",
        "link": "#5eead4",
        "code_fg": "#99f6e4",
        "code_bg": "rgba(45,212,191,0.15)",
        "text_primary": "#f0fdfa",
        "text_body": "#cfe6e3",
        "text_italic": "#bddad6",
        "text_muted": "#88aba6",
        "callout_accents": ["#2dd4bf", "#fb923c", "#facc15"],
    },
    {
        "id": "desert_terracotta",
        "name": "09 · High Desert Terracotta",
        "inspiration": "Joshua Tree Cosmic Country / Canyon Clay & Sage",
        "outer_bg": "#110907",
        "card_bg": "#1c110d",
        "obi_bg": "#261712",
        "callout_bg": "#2b1b15",
        "footer_bg": "#150c09",
        "border": "#472e24",
        "primary": "#f97316",
        "cta_bg": "#c2410c",
        "cta_text": "#ffffff",
        "secondary": "#2dd4bf",
        "link": "#fdba74",
        "code_fg": "#fed7aa",
        "code_bg": "rgba(249,115,22,0.16)",
        "text_primary": "#fff7ed",
        "text_body": "#e7d8ce",
        "text_italic": "#d8c6ba",
        "text_muted": "#af998c",
        "callout_accents": ["#f97316", "#2dd4bf", "#facc15"],
    },
    {
        "id": "tokyo_kissaten_olive",
        "name": "10 · Tokyo Kissaten Olive",
        "inspiration": "1970s Shibuya Jazz-Kissa / Smoked Matcha & Copper",
        "outer_bg": "#0a0c08",
        "card_bg": "#13170e",
        "obi_bg": "#1a2014",
        "callout_bg": "#1e2517",
        "footer_bg": "#0d100a",
        "border": "#323d27",
        "primary": "#a3e635",
        "cta_bg": "#4d7c0f",
        "cta_text": "#ffffff",
        "secondary": "#f59e0b",
        "link": "#bef264",
        "code_fg": "#d9f99d",
        "code_bg": "rgba(163,230,53,0.15)",
        "text_primary": "#f7fee7",
        "text_body": "#dce4cf",
        "text_italic": "#cad5ba",
        "text_muted": "#97a686",
        "callout_accents": ["#a3e635", "#f59e0b", "#38bdf8"],
    },
]


def select_email_theme(
    period_hint: str = "",
    theme_index: int | None = None,
) -> EmailTheme:
    """
    Selects one of the rotating record-sleeve color themes via `(day_of_month - 1) % len(EMAIL_THEMES)`.
    Falls back to ISO week or month modulo for weekly/monthly logs, or index 0.
    """
    count = len(EMAIL_THEMES)
    if theme_index is not None:
        return EMAIL_THEMES[theme_index % count]

    m_date = _ISO_DATE_RE.search(period_hint)
    if m_date:
        day = int(m_date.group(3))
        return EMAIL_THEMES[(day - 1) % count]

    m_week = _ISO_WEEK_RE.search(period_hint)
    if m_week:
        week = int(m_week.group(1))
        return EMAIL_THEMES[(week - 1) % count]

    m_month = _ISO_MONTH_RE.search(period_hint)
    if m_month:
        month = int(m_month.group(1))
        return EMAIL_THEMES[(month - 1) % count]

    m_month_name = _MONTH_NAME_RE.search(period_hint)
    if m_month_name:
        month = _MONTH_NAMES[m_month_name.group(1).lower()]
        return EMAIL_THEMES[(month - 1) % count]

    return EMAIL_THEMES[0]
