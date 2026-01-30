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

# Comprehensive lookalike character map for Russian, English, and Kazakh
# Maps each character to a regex character class with visually similar alternatives
LOOKALIKE_MAP = {
    # Latin/Cyrillic/Kazakh lookalikes with leet speak
    'a': '[aаӑӓӓӓ@4]',
    'b': '[bбвЬ6]',
    'c': '[cсϲⅽ]',
    'd': '[dԁ]',
    'e': '[eеёӗӗ3€]',
    'g': '[gԍ]',
    'h': '[hһҺ]',
    'i': '[iіїӏ1!|]',
    'j': '[jјј]',
    'k': '[kкқҚ]',
    'l': '[lӏ1|]',
    'm': '[mмӎ]',
    'n': '[nпҥҢ]',
    'o': '[oоөӨ0]',
    'p': '[pрр]',
    'q': '[qԛ]',
    'r': '[rгr]',
    's': '[sѕs5$]',
    't': '[tтҭ]',
    'u': '[uүұӯ]',
    'v': '[vѵν]',
    'w': '[wԝ]',
    'x': '[xхҳ×]',
    'y': '[yуўӱ]',
    'z': '[z3]',
    # Cyrillic characters
    'а': '[aаӑӓӓӓ@4]',
    'б': '[б6bв]',
    'в': '[вb]',
    'г': '[гr]',
    'д': '[дg]',
    'е': '[eеёӗӗ3€]',
    'ё': '[eеёӗӗ3€]',
    'ж': '[ж]',
    'з': '[з3z]',
    'и': '[иuiі1]',
    'й': '[йuiі]',
    'к': '[кkқҚ]',
    'л': '[л]',
    'м': '[мm]',
    'н': '[нn]',
    'о': '[oоөӨ0]',
    'п': '[пnp]',
    'р': '[рp]',
    'с': '[сc]',
    'т': '[тt]',
    'у': '[уy]',
    'ф': '[ф]',
    'х': '[хx×]',
    'ц': '[ц]',
    'ч': '[ч4]',
    'ш': '[ш]',
    'щ': '[щ]',
    'ъ': '[ъ]',
    'ы': '[ы]',
    'ь': '[ьb]',
    'э': '[э3e]',
    'ю': '[ю]',
    'я': '[я]',
    # Kazakh-specific
    'ә': '[ә]',
    'ғ': '[ғ]',
    'қ': '[қkкk]',
    'ң': '[ңn]',
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
    2. Spaced/separated characters (e.g., "w o r d")
    3. Zero-width character injection
    4. Unicode normalization variants
    """
    word = word.lower().strip()
    if len(word) < 3:
        return []  # Too short for regex variants
    
    variants = []
    
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
    
    return variants


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
