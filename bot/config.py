"""
Bot configuration: default trigger words and regex patterns.
Triggers are stored per-chat in the database and can be managed via commands.
"""

import os
import re
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
    1. Spaced characters (e.g., "w o r d")
    2. L33t speak variants (e.g., "w0rd")
    3. Mixed case Unicode tricks
    """
    word = word.lower().strip()
    if len(word) < 3:
        return []  # Too short for regex variants
    
    variants = []
    
    # Pattern 1: Spaced/separated characters (bypass technique)
    # Example: "word" -> "w\s*o\s*r\s*d"
    spaced_pattern = r"\s{0,2}".join(list(word))
    variants.append({
        "name": f"{word}_spaced",
        "pattern": spaced_pattern,
        "description": f"Обход '{word}' через пробелы/символы",
        "examples": [" ".join(word), word],
        "enabled": True,
    })
    
    # Pattern 2: L33t speak (if applicable)
    # Common substitutions: a->@, e->3, i->1, o->0, s->5
    leet_map = {'a': '[a@а]', 'e': '[e3е]', 'i': '[i1іі]', 'o': '[o0о]', 's': '[s5ѕ]'}
    leet_pattern = ""
    has_leet = False
    for char in word:
        if char in leet_map:
            leet_pattern += leet_map[char]
            has_leet = True
        else:
            leet_pattern += char
    
    if has_leet:
        variants.append({
            "name": f"{word}_leet",
            "pattern": r"\b" + leet_pattern + r"\b",
            "description": f"L33t-speak варианты '{word}'",
            "examples": [word, word.replace('a', '@').replace('o', '0')],
            "enabled": True,
        })
    
    return variants


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
