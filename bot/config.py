"""
Bot configuration: default trigger words and regex patterns.
Triggers are stored per-chat in the database and can be managed via commands.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Pattern
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db")

# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT TRIGGER LEMMAS (used for new chat initialization)
# ═══════════════════════════════════════════════════════════════════════════════
# Lemmas are normalized word forms (nominative case, singular, infinitive).
# pymorphy3 converts any word form to its lemma for comparison.
# These are used as defaults when a chat is first initialized.

TRIGGER_LEMMAS: set[str] = {
    # Default examples (customize for your needs):
    "test",
}

# ═══════════════════════════════════════════════════════════════════════════════
# REGEX PATTERN GENERATORS (for enhanced detection of trigger words)
# ═══════════════════════════════════════════════════════════════════════════════

# Transliteration map: Russian ↔ English phonetic equivalents
# Used to detect words written in alternate scripts (e.g., "привет" as "privet")
TRANSLIT_RU_TO_EN = {
    'а': 'a',
    'б': 'b',
    'в': 'v',
    'г': 'g',
    'д': 'd',
    'е': ['e', 'ye'],
    'ё': ['yo', 'e'],
    'ж': 'zh',
    'з': 'z',
    'и': 'i',
    'й': ['y', 'i', 'j'],
    'к': 'k',
    'л': 'l',
    'м': 'm',
    'н': 'n',
    'о': 'o',
    'п': 'p',
    'р': 'r',
    'с': 's',
    'т': 't',
    'у': 'u',
    'ф': 'f',
    'х': ['kh', 'h'],
    'ц': ['ts', 'c'],
    'ч': 'ch',
    'ш': 'sh',
    'щ': ['shch', 'sch'],
    'ъ': ['', "'"],
    'ы': 'y',
    'ь': ['', "'"],
    'э': 'e',
    'ю': ['yu', 'u'],
    'я': ['ya', 'ia'],
    # Kazakh-specific
    'ә': 'a',
    'ғ': 'g',
    'қ': 'q',
    'ң': 'ng',
    'ө': 'o',
    'ұ': 'u',
    'ү': 'u',
    'һ': 'h',
    'і': 'i',
}

TRANSLIT_EN_TO_RU = {
    'a': 'а',
    'b': 'б',
    'c': ['ц', 'к', 'с'],
    'd': 'д',
    'e': ['е', 'э'],
    'f': 'ф',
    'g': 'г',
    'h': 'х',
    'i': ['и', 'і'],
    'j': 'й',
    'k': 'к',
    'l': 'л',
    'm': 'м',
    'n': 'н',
    'o': 'о',
    'p': 'п',
    'q': 'к',
    'r': 'р',
    's': 'с',
    't': 'т',
    'u': 'у',
    'v': 'в',
    'w': 'в',
    'x': 'кс',
    'y': ['й', 'ы', 'и'],
    'z': 'з',
    # Multi-character transliterations
    'zh': 'ж',
    'kh': 'х',
    'ts': 'ц',
    'ch': 'ч',
    'sh': 'ш',
    'shch': 'щ',
    'sch': 'щ',
    'yu': 'ю',
    'ya': 'я',
    'yo': 'ё',
    'ye': 'е',
    'ia': 'я',
}

# Comprehensive lookalike character map for Russian, English, and Kazakh
# Maps each character to a regex character class with visually similar alternatives
# AND phonetically similar alternatives (for multi-modal detection)
LOOKALIKE_MAP = {
    # Latin/Cyrillic/Kazakh lookalikes with leet speak and phonetic mappings
    'a': '[aаӑӓӓӓ@4]',
    'b': '[bбвЬ6]',
    'c': '[cсϲⅽ]',
    'd': '[dԁд]',
    'e': '[eеёӗӗ3€]',
    'g': '[gԍг]',
    'h': '[hһҺ]',
    'i': '[iіїӏ1!|иі]',
    'j': '[jјј]',
    'k': '[kкқҚ]',
    'l': '[lӏ1|л]',
    'm': '[mмӎ]',
    'n': '[nпҥҢ]',
    'o': '[oоөӨ0]',
    'p': '[pрр]',
    'q': '[qԛ]',
    'r': '[rгrр]',
    's': '[sѕs5$с]',
    't': '[tтҭ]',
    'u': '[uүұӯу]',
    'v': '[vѵνв]',
    'w': '[wԝ]',
    'x': '[xхҳ×]',
    'y': '[yуўӱ]',
    'z': '[z3з]',
    # Cyrillic characters (with phonetic Latin equivalents)
    'а': '[aаӑӓӓӓ@4]',
    'б': '[б6bв]',
    'в': '[вbv]',
    'г': '[гrg]',
    'д': '[дgd]',
    'е': '[eеёӗӗ3€]',
    'ё': '[eеёӗӗ3€yo]',
    'ж': '[жzh]',
    'з': '[з3z]',
    'и': '[иuiі1]',
    'й': '[ийyij]',
    'к': '[кkқҚ]',
    'л': '[лl]',
    'м': '[мm]',
    'н': '[нn]',
    'о': '[oоөӨ0]',
    'п': '[пnp]',
    'р': '[рpr]',
    'с': '[сcs]',
    'т': '[тt]',
    'у': '[уuy]',
    'ф': '[фf]',
    'х': '[хxh]',
    'ц': '[цtsc]',
    'ч': '[ч4ch]',
    'ш': '[шsh]',
    'щ': '[щshch]',
    'ъ': '[ъ]',
    'ы': '[ыy]',
    'ь': '[ьb]',
    'э': '[э3e]',
    'ю': '[юyu]',
    'я': '[яyaia]',
    # Kazakh-specific
    'ә': '[ә]',
    'ғ': '[ғg]',
    'қ': '[қkкkq]',
    'ң': '[ңnng]',
    'ө': '[өoо0]',
    'ұ': '[ұu]',
    'ү': '[үu]',
    'һ': '[һh]',
    'і': '[іi1|]',
}

@dataclass
class RegexRule:
    """Regex detection rule."""
    name: str                          # Unique rule name
    pattern: Pattern[str]              # Compiled regex pattern
    description: str = ""              # Description for /triggers command
    examples: list[str] = field(default_factory=list)  # Example matches
    enabled: bool = True               # Whether rule is active


def _compile_rules(rules_data: list[dict]) -> list[RegexRule]:
    """Compiles regex rules from configuration."""
    result = []
    for r in rules_data:
        try:
            pattern = re.compile(r["pattern"], re.IGNORECASE | re.UNICODE)
            result.append(RegexRule(
                name=r["name"],
                pattern=pattern,
                description=r.get("description", ""),
                examples=r.get("examples", []),
                enabled=r.get("enabled", True),
            ))
        except re.error as e:
            print(f"Regex compilation error '{r['name']}': {e}")
    return result


def generate_regex_variants_for_word(word: str) -> list[dict]:
    """
    Generates regex pattern variants for a given word to catch common evasion techniques.
    Returns list of rule dicts that can be added to database.
    
    Generated patterns:
    1. Multi-language lookalikes (Russian/English/Kazakh character substitution)
    2. Transliteration (Russian ↔ English phonetic equivalents)
    3. Spaced/separated characters (e.g., "w o r d")
    4. Zero-width character injection
    5. Unicode normalization variants
    6. MULTI-MODAL: Combinations (transliteration + spacing, transliteration + lookalikes)
    """
    word = word.lower().strip()
    if len(word) < 3:
        return []  # Too short for regex variants
    
    variants = []
    
    # Determine if word is primarily Cyrillic or Latin
    is_cyrillic = any('\u0400' <= c <= '\u04FF' for c in word)
    
    # Get transliterated version for multi-modal patterns
    translit_word = None
    if is_cyrillic:
        translit_word = _transliterate_word(word, TRANSLIT_RU_TO_EN)
    else:
        translit_word = _transliterate_word(word, TRANSLIT_EN_TO_RU)
    
    # Pattern 0: Transliteration variants (exact match only)
    # Convert Russian words to Latin equivalents and vice versa
    if is_cyrillic:
        # Russian word → English transliteration
        translit_pattern = _generate_translit_pattern(word, TRANSLIT_RU_TO_EN)
        if translit_pattern:
            variants.append({
                "name": f"{word}_translit_en",
                "pattern": r"\b" + translit_pattern + r"\b",
                "description": f"Транслитерация '{word}' латиницей",
                "examples": [word, translit_word],
                "enabled": True,
            })
    else:
        # English word → Russian transliteration
        translit_pattern = _generate_translit_pattern(word, TRANSLIT_EN_TO_RU)
        if translit_pattern:
            variants.append({
                "name": f"{word}_translit_ru",
                "pattern": r"\b" + translit_pattern + r"\b",
                "description": f"Транслитерация '{word}' кириллицей",
                "examples": [word, translit_word],
                "enabled": True,
            })
    
    # Pattern 1: Multi-language lookalike substitution
    # Catches: mixed scripts, leet speak, homoglyphs
    # Example: "привет" catches "privet", "пpивeт", "pr1vet", etc.
    lookalike_pattern = ""
    has_substitutions = False
    
    for char in word:
        char_lower = char.lower()
        if char_lower in LOOKALIKE_MAP:
            lookalike_pattern += LOOKALIKE_MAP[char_lower]
            has_substitutions = True
        else:
            # Escape special regex characters
            lookalike_pattern += re.escape(char)
    
    if has_substitutions:
        variants.append({
            "name": f"{word}_lookalike",
            "pattern": r"\b" + lookalike_pattern + r"\b",
            "description": f"Обход '{word}' через замену букв (RU/EN/KZ/leet)",
            "examples": [word, _generate_lookalike_example(word)],
            "enabled": True,
        })
    
    # Pattern 2: Spaced/separated characters (bypass technique)
    # Example: "word" -> "w\s*o\s*r\s*d"
    # Allow 0-3 spaces/separators between characters
    spaced_chars = []
    for char in word:
        char_lower = char.lower()
        if char_lower in LOOKALIKE_MAP:
            spaced_chars.append(LOOKALIKE_MAP[char_lower])
        else:
            spaced_chars.append(re.escape(char))
    
    spaced_pattern = r"[\s\.\-_]{0,3}".join(spaced_chars)
    variants.append({
        "name": f"{word}_spaced",
        "pattern": spaced_pattern,
        "description": f"Обход '{word}' через пробелы/разделители",
        "examples": [" ".join(word), "".join(word)],
        "enabled": True,
    })
    
    # Pattern 3: Zero-width character injection
    # Example: "word" with invisible Unicode characters between letters
    zw_chars = r"[\u200B\u200C\u200D\u2060\uFEFF]"  # Zero-width space, ZWNJ, ZWJ, word joiner, BOM
    zw_pattern_parts = []
    for char in word:
        char_lower = char.lower()
        if char_lower in LOOKALIKE_MAP:
            zw_pattern_parts.append(LOOKALIKE_MAP[char_lower])
        else:
            zw_pattern_parts.append(re.escape(char))
    
    zw_pattern = f"{zw_chars}{{0,2}}".join(zw_pattern_parts)
    variants.append({
        "name": f"{word}_zerowidth",
        "pattern": r"\b" + zw_pattern + r"\b",
        "description": f"Обход '{word}' через невидимые символы",
        "examples": [word],
        "enabled": True,
    })
    
    # Pattern 4: Unicode normalization variants (diacritics)
    # Normalize to NFD (decomposed form) and create pattern ignoring combining marks
    normalized = unicodedata.normalize('NFD', word)
    base_chars = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    if base_chars != word and len(base_chars) >= 3:
        # Create pattern that optionally matches combining diacritics after each base char
        diacritic_pattern = ""
        for char in base_chars:
            char_lower = char.lower()
            if char_lower in LOOKALIKE_MAP:
                diacritic_pattern += LOOKALIKE_MAP[char_lower]
            else:
                diacritic_pattern += re.escape(char)
            # Optionally match any combining diacritical marks
            diacritic_pattern += r"[\u0300-\u036f]{0,3}"
        
        variants.append({
            "name": f"{word}_diacritics",
            "pattern": r"\b" + diacritic_pattern + r"\b",
            "description": f"Обход '{word}' через диакритические знаки",
            "examples": [word, base_chars],
            "enabled": True,
        })
    
    # Pattern 5: MULTI-MODAL - Transliteration + Spacing/Lookalikes
    # This catches "pr i vet", "pr1vet", "p r 1 v e t" for word "привет"
    if translit_word and len(translit_word) >= 3 and translit_word != word:
        # Build pattern with lookalike + spacing for transliterated word
        multimodal_chars = []
        for char in translit_word:
            char_lower = char.lower()
            if char_lower in LOOKALIKE_MAP:
                multimodal_chars.append(LOOKALIKE_MAP[char_lower])
            else:
                multimodal_chars.append(re.escape(char))
        
        # Add spacing between characters
        multimodal_pattern = r"[\s\.\-_]{0,3}".join(multimodal_chars)
        
        variants.append({
            "name": f"{word}_translit_spaced",
            "pattern": multimodal_pattern,
            "description": f"Транслитерация '{word}' с пробелами/заменами",
            "examples": [translit_word, " ".join(translit_word)],
            "enabled": True,
        })
        
        # Also create zero-width variant for transliteration
        zw_chars = r"[\u200B\u200C\u200D\u2060\uFEFF]"
        multimodal_zw = f"{zw_chars}{{0,2}}".join(multimodal_chars)
        
        variants.append({
            "name": f"{word}_translit_zerowidth",
            "pattern": r"\b" + multimodal_zw + r"\b",
            "description": f"Транслитерация '{word}' с невидимыми символами",
            "examples": [translit_word],
            "enabled": True,
        })
    
    return variants


def _generate_translit_pattern(word: str, translit_map: dict) -> str:
    """Generate regex pattern for transliteration variants."""
    pattern = ""
    i = 0
    
    while i < len(word):
        matched = False
        
        # Try to match multi-character sequences first (e.g., "sh", "zh", "ch")
        for length in [4, 3, 2]:  # Try longer sequences first
            if i + length <= len(word):
                substr = word[i:i+length].lower()
                if substr in translit_map:
                    options = translit_map[substr]
                    if isinstance(options, list):
                        # Multiple options: create character class
                        filtered_options = [opt for opt in options if opt]  # Remove empty strings
                        if filtered_options:
                            if len(filtered_options) == 1:
                                pattern += re.escape(filtered_options[0])
                            else:
                                pattern += f"(?:{'|'.join(re.escape(opt) for opt in filtered_options)})"
                    elif options:  # Single option, not empty
                        pattern += re.escape(options)
                    i += length
                    matched = True
                    break
        
        # If no multi-char match, try single character
        if not matched:
            char = word[i].lower()
            if char in translit_map:
                options = translit_map[char]
                if isinstance(options, list):
                    filtered_options = [opt for opt in options if opt]
                    if filtered_options:
                        if len(filtered_options) == 1:
                            pattern += re.escape(filtered_options[0])
                        else:
                            pattern += f"(?:{'|'.join(re.escape(opt) for opt in filtered_options)})"
                    else:
                        # All options were empty (like ъ, ь) - skip
                        pass
                elif options:
                    pattern += re.escape(options)
                else:
                    # Empty string mapping (like ъ, ь) - skip
                    pass
            else:
                # Character not in map, keep as-is
                pattern += re.escape(char)
            i += 1
    
    return pattern if pattern else ""


def _transliterate_word(word: str, translit_map: dict) -> str:
    """Simple transliteration for example generation (takes first option)."""
    result = ""
    i = 0
    
    while i < len(word):
        matched = False
        
        # Try multi-character sequences
        for length in [4, 3, 2]:
            if i + length <= len(word):
                substr = word[i:i+length].lower()
                if substr in translit_map:
                    options = translit_map[substr]
                    if isinstance(options, list):
                        result += options[0] if options and options[0] else ''
                    else:
                        result += options if options else ''
                    i += length
                    matched = True
                    break
        
        if not matched:
            char = word[i].lower()
            if char in translit_map:
                options = translit_map[char]
                if isinstance(options, list):
                    result += options[0] if options and options[0] else ''
                else:
                    result += options if options else ''
            else:
                result += char
            i += 1
    
    return result


def _generate_lookalike_example(word: str) -> str:
    """Generate an example with character substitutions for display."""
    example = ""
    substitutions = {
        'a': '@', 'e': '3', 'i': '1', 'o': '0', 's': '5',
        'а': 'a', 'е': 'e', 'о': 'o', 'с': 'c', 'р': 'p',
        'к': 'k', 'х': 'x', 'у': 'y', 'в': 'b', 'н': 'n',
    }
    
    for i, char in enumerate(word):
        char_lower = char.lower()
        # Substitute every 2nd character for variety
        if i % 2 == 1 and char_lower in substitutions:
            example += substitutions[char_lower]
        else:
            example += char
    
    return example if example != word else word.replace('o', '0').replace('е', 'e')


# Static regex rules (generic patterns not tied to specific words)
_REGEX_RULES_DATA = [
    # Add generic patterns here if needed (e.g., URL patterns, markdown patterns, etc.)
]

REGEX_RULES: list[RegexRule] = _compile_rules(_REGEX_RULES_DATA)

# ═══════════════════════════════════════════════════════════════════════════════
# EXCLUSION PATTERNS (don't count as triggers even if matched)
# ═══════════════════════════════════════════════════════════════════════════════

_EXCLUSION_PATTERNS_DATA = [
    {
        "name": "quotation",
        "pattern": r'["\'\«\»].{0,100}\b\w+\b.{0,100}["\'\«\»]',
        "description": "Word in quotes (quoting/citing)",
    },
    {
        "name": "url",
        "pattern": r"https?://\S+",
        "description": "Part of URL",
    },
    {
        "name": "command_mention",
        "pattern": r"^/(triggers|words|help|counter|leaderboard)\b",
        "description": "Bot command context",
    },
]

EXCLUSION_PATTERNS: list[RegexRule] = _compile_rules(_EXCLUSION_PATTERNS_DATA)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_active_regex_rules() -> list[RegexRule]:
    """Returns only active regex rules from static configuration."""
    return [r for r in REGEX_RULES if r.enabled]


def get_all_triggers_info() -> dict:
    """Returns information about all default triggers for /triggers command display."""
    return {
        "lemmas": sorted(TRIGGER_LEMMAS),
        "regex_rules": [
            {
                "name": r.name,
                "description": r.description,
                "examples": r.examples,
                "enabled": r.enabled,
            }
            for r in REGEX_RULES
        ],
        "exclusions": [
            {
                "name": r.name,
                "description": r.description,
            }
            for r in EXCLUSION_PATTERNS
        ],
    }
