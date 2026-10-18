"""Bounded, explicit subtitle preferences shared by settings and playback."""

from __future__ import annotations

MAX_SUBTITLE_LANGUAGES = 3
SUBTITLE_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ne": "Nepali",
    "or": "Odia",
    "pa": "Punjabi",
    "ta": "Tamil",
    "te": "Telugu",
    "ur": "Urdu",
    "ar": "Arabic",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "nl": "Dutch",
    "en-GB": "English (UK)",
    "en-US": "English (US)",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "he": "Hebrew",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese",
    "pt-BR": "Portuguese (Brazil)",
    "ro": "Romanian",
    "ru": "Russian",
    "es": "Spanish",
    "si": "Sinhala",
    "sw": "Swahili",
    "sv": "Swedish",
    "tl": "Tagalog",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
}

# Media containers usually store ISO 639-2 language tags instead of web codes.
_CONTAINER_CODES = {
    "eng": "en",
    "hin": "hi",
    "ben": "bn",
    "guj": "gu",
    "kan": "kn",
    "mal": "ml",
    "mar": "mr",
    "nep": "ne",
    "ori": "or",
    "pan": "pa",
    "tam": "ta",
    "tel": "te",
    "urd": "ur",
    "ara": "ar",
    "zho": "zh",
    "chi": "zh",
    "nld": "nl",
    "dut": "nl",
    "fra": "fr",
    "fre": "fr",
    "deu": "de",
    "ger": "de",
    "ell": "el",
    "gre": "el",
    "heb": "he",
    "ind": "id",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "msa": "ms",
    "may": "ms",
    "fas": "fa",
    "per": "fa",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "rum": "ro",
    "rus": "ru",
    "spa": "es",
    "sin": "si",
    "swa": "sw",
    "swe": "sv",
    "tgl": "tl",
    "tha": "th",
    "tur": "tr",
    "ukr": "uk",
    "vie": "vi",
}


def normalize_subtitle_languages(value: object) -> list[str]:
    """Validate exact language codes; never accept yt-dlp's 'all' or regexes."""
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    if not isinstance(value, list) or not all(isinstance(code, str) for code in value):
        raise ValueError("Subtitle languages must be a list of language codes")
    canonical = {code.lower(): code for code in SUBTITLE_LANGUAGES}
    languages = []
    for raw in value:
        code = canonical.get(raw.strip().lower())
        if code is None:
            raise ValueError(f"Unsupported subtitle language: {raw}. Use /subs_lang list.")
        if code not in languages:
            languages.append(code)
    if not 1 <= len(languages) <= MAX_SUBTITLE_LANGUAGES:
        raise ValueError(f"Select between 1 and {MAX_SUBTITLE_LANGUAGES} subtitle languages.")
    return languages


def subtitle_language_name(code: str) -> str:
    """Readable labels for supported web codes and container language tags."""
    code = _CONTAINER_CODES.get(code.lower(), code)
    canonical = {key.lower(): label for key, label in SUBTITLE_LANGUAGES.items()}
    return canonical.get(code.lower(), code)
