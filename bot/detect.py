"""
Trigger detection module.

Two-tier detection system:
1. Lemma-based detection (pymorphy3) - primary layer
2. Regex pattern detection - secondary layer for variants/evasion

Returns detailed match information for transparency.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum

import pymorphy3

from bot.config import (
    EXCLUSION_PATTERNS,
    RegexRule,
    generate_regex_variants_for_word,
)

morph = pymorphy3.MorphAnalyzer()

# Performance optimization: compiled regex patterns cached to avoid recompilation
_compiled_patterns_cache: dict[str, Optional[re.Pattern]] = {}


class MatchType(str, Enum):
    """Type of match."""
    LEMMA = "lemma"
    REGEX = "regex"


@dataclass
class MatchDetail:
    """Details of trigger match."""
    match_type: MatchType
    original_text: str      # Original text (as in message)
    matched_fragment: str   # Matched fragment
    lemma: Optional[str]    # Lemma (for LEMMA type)
    rule_name: Optional[str]  # Rule name (for REGEX type)
    position_start: int     # Start position in text
    position_end: int       # End position in text
    
    def to_dict(self) -> dict:
        return {
            "match_type": self.match_type.value,
            "original_text": self.original_text,
            "matched_fragment": self.matched_fragment,
            "lemma": self.lemma,
            "rule_name": self.rule_name,
            "position_start": self.position_start,
            "position_end": self.position_end,
        }
    
    def format_human(self) -> str:
        """Format match for display to user."""
        if self.match_type == MatchType.LEMMA:
            return f'«{self.matched_fragment}» (lemma: {self.lemma})'
        else:
            return f'«{self.matched_fragment}» (rule: {self.rule_name})'


@dataclass
class DetectionResult:
    """Detection result with match details."""
    triggered: bool
    matches: list[MatchDetail]
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "matches": [m.to_dict() for m in self.matches],
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
        }
    
    @property
    def first_match(self) -> Optional[MatchDetail]:
        """First match (primary trigger)."""
        return self.matches[0] if self.matches else None


# Tokenization regex: Cyrillic and Latin words
TOKEN_PATTERN = re.compile(r'[а-яёa-z]+', re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Normalize text: lowercase and trim whitespace."""
    return text.lower().strip()


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """
    Split text into tokens.
    Returns list of (token, start_pos, end_pos).
    """
    tokens = []
    for match in TOKEN_PATTERN.finditer(text.lower()):
        tokens.append((match.group(), match.start(), match.end()))
    return tokens


def get_lemma(word: str) -> str:
    """Get word lemma using pymorphy3 morphological analyzer."""
    try:
        parsed = morph.parse(word)
        if parsed:
            return parsed[0].normal_form
    except Exception:
        pass
    return word


def check_exclusions(text: str) -> tuple[bool, Optional[str]]:
    """
    Check if text matches exclusion patterns (quotes, URLs, commands).
    Returns (is_excluded, reason).
    """
    normalized = normalize_text(text)
    
    for rule in EXCLUSION_PATTERNS:
        if not rule.enabled:
            continue
        match = rule.pattern.search(normalized)
        if match:
            return True, rule.name
    
    return False, None


def detect_by_lemmas(text: str, trigger_lemmas: set[str]) -> list[MatchDetail]:
    """
    Lemma-based detection (primary layer).
    Returns list of matches.
    """
    matches = []
    tokens = tokenize(text)
    
    for token, start, end in tokens:
        lemma = get_lemma(token)
        
        if lemma in trigger_lemmas:
            matches.append(MatchDetail(
                match_type=MatchType.LEMMA,
                original_text=text[start:end],
                matched_fragment=token,
                lemma=lemma,
                rule_name=None,
                position_start=start,
                position_end=end,
            ))
    
    return matches

def get_compiled_pattern(rule_name: str) -> Optional[re.Pattern]:
    """
    Get compiled regex pattern for a rule (with caching).
    
    Performance optimization: Patterns are compiled once and cached.
    This avoids regenerating and recompiling patterns on every message.
    
    Args:
        rule_name: Name of the regex rule (e.g., "привет_spaced")
    
    Returns:
        Compiled regex pattern or None if invalid
    """
    # Check cache first
    if rule_name in _compiled_patterns_cache:
        return _compiled_patterns_cache[rule_name]
    
    # Cache miss - generate and compile pattern
    pattern = None
    
    # Extract base word from rule name (e.g., "привет" from "привет_spaced")
    if '_' in rule_name:
        base_word = rule_name.rsplit('_', 1)[0]
        variants = generate_regex_variants_for_word(base_word)
        
        for variant in variants:
            if variant['name'] == rule_name:
                try:
                    pattern = re.compile(variant['pattern'], re.IGNORECASE | re.UNICODE)
                except re.error:
                    pattern = None
                break
    
    # Cache the result (even if None to avoid repeated lookups)
    _compiled_patterns_cache[rule_name] = pattern
    return pattern


def clear_pattern_cache():
    """Clear the compiled pattern cache (useful for testing or dynamic updates)."""
    global _compiled_patterns_cache
    _compiled_patterns_cache.clear()


def detect_by_regex(text: str, enabled_rules: dict[str, bool]) -> list[MatchDetail]:
    """
    Regex-based detection (secondary layer).
    Returns list of matches.
    
    Args:
        text: Text to check
        enabled_rules: Dict of rule_name -> enabled status from database
    """
    matches = []
    normalized = normalize_text(text)
    
    for rule_name, is_enabled in enabled_rules.items():
        if not is_enabled:
            continue
        
        pattern = get_compiled_pattern(rule_name)
        
        if pattern:
            try:
                for match in pattern.finditer(normalized):
                    matches.append(MatchDetail(
                        match_type=MatchType.REGEX,
                        original_text=text[match.start():match.end()],
                        matched_fragment=match.group(),
                        lemma=None,
                        rule_name=rule_name,
                        position_start=match.start(),
                        position_end=match.end(),
                    ))
            except Exception:
                pass
    
    return matches


def detect_triggers(text: str, trigger_lemmas: set[str], regex_rules_enabled: dict[str, bool]) -> DetectionResult:
    """
    Main trigger detection function.
    
    Process:
    1. Check exclusions (quotes, URLs, commands)
    2. Lemma-based detection (primary layer)
    3. Regex-based detection (secondary layer)
    4. Return detailed result
    
    Args:
        text: Text to check
        trigger_lemmas: Set of lemmas for detection
        regex_rules_enabled: Dict {rule_name: enabled} for regex rules
    """
    if not text or not text.strip():
        return DetectionResult(triggered=False, matches=[])
    
    excluded, exclusion_reason = check_exclusions(text)
    if excluded:
        return DetectionResult(
            triggered=False,
            matches=[],
            excluded=True,
            exclusion_reason=exclusion_reason,
        )
    
    all_matches = []
    
    # Layer 1: lemma detection
    lemma_matches = detect_by_lemmas(text, trigger_lemmas)
    all_matches.extend(lemma_matches)
    
    # Layer 2: regex detection
    regex_matches = detect_by_regex(text, regex_rules_enabled)
    
    # Remove duplicates (if regex found same position as lemma)
    existing_positions = {(m.position_start, m.position_end) for m in all_matches}
    for rm in regex_matches:
        if (rm.position_start, rm.position_end) not in existing_positions:
            all_matches.append(rm)
    
    # Sort by position
    all_matches.sort(key=lambda m: m.position_start)
    
    return DetectionResult(
        triggered=len(all_matches) > 0,
        matches=all_matches,
    )


def format_match_for_message(match: MatchDetail) -> str:
    """Format match detail for bot message display."""
    if match.match_type == MatchType.LEMMA:
        return f'<b>{match.matched_fragment}</b> → лемма <code>{match.lemma}</code>'
    else:
        return f'<b>{match.matched_fragment}</b> → правило <code>{match.rule_name}</code>'


def format_detection_result(result: DetectionResult) -> str:
    """Format full detection result for display."""
    if not result.triggered:
        if result.excluded:
            return f"⚪ Исключение: {result.exclusion_reason}"
        return "✅ Триггеров не найдено"
    
    lines = ["🚨 <b>Найдены триггеры:</b>"]
    for i, match in enumerate(result.matches, 1):
        lines.append(f"  {i}. {format_match_for_message(match)}")
    
    return "\n".join(lines)
