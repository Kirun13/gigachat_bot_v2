"""
Trigger detection module.

Two-tier detection system:
1. Lemmas (pymorphy3) - primary detection layer
2. Regex patterns - secondary detection layer for variants/evasion

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

# Initialize morphological analyzer
morph = pymorphy3.MorphAnalyzer()

# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE OPTIMIZATION: Pattern Compilation Cache
# ═══════════════════════════════════════════════════════════════════════════════
# Compiled regex patterns are cached to avoid regeneration on every message
# This provides ~2-3ms speedup per message for large trigger sets

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
        """Форматирует для отображения пользователю."""
        if self.match_type == MatchType.LEMMA:
            return f'«{self.matched_fragment}» (лемма: {self.lemma})'
        else:
            return f'«{self.matched_fragment}» (правило: {self.rule_name})'


@dataclass
class DetectionResult:
    """Результат детекции."""
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
        """Первое совпадение (главный триггер)."""
        return self.matches[0] if self.matches else None


# ═══════════════════════════════════════════════════════════════════════════════
# НОРМАЛИЗАЦИЯ И ТОКЕНИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

# Regex для токенизации: слова на кириллице и латинице
TOKEN_PATTERN = re.compile(r'[а-яёa-z]+', re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Нормализует текст: lower, удаление лишних пробелов."""
    return text.lower().strip()


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """
    Разбивает текст на токены.
    Возвращает список (токен, start, end).
    """
    tokens = []
    for match in TOKEN_PATTERN.finditer(text.lower()):
        tokens.append((match.group(), match.start(), match.end()))
    return tokens


def get_lemma(word: str) -> str:
    """Получает лемму слова через pymorphy3."""
    try:
        parsed = morph.parse(word)
        if parsed:
            return parsed[0].normal_form
    except Exception:
        pass
    return word


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОВЕРКА ИСКЛЮЧЕНИЙ
# ═══════════════════════════════════════════════════════════════════════════════

def check_exclusions(text: str) -> tuple[bool, Optional[str]]:
    """
    Проверяет, попадает ли текст под исключения.
    Возвращает (excluded, reason).
    """
    normalized = normalize_text(text)
    
    for rule in EXCLUSION_PATTERNS:
        if not rule.enabled:
            continue
        match = rule.pattern.search(normalized)
        if match:
            return True, rule.name
    
    return False, None


# ═══════════════════════════════════════════════════════════════════════════════
# ДЕТЕКЦИЯ ПО ЛЕММАМ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_by_lemmas(text: str, trigger_lemmas: set[str]) -> list[MatchDetail]:
    """
    Детекция по леммам.
    Возвращает список совпадений.
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


# ═══════════════════════════════════════════════════════════════════════════════
# REGEX DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

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
    Detection by regex patterns from database.
    Returns list of matches.
    
    Args:
        text: Text to check
        enabled_rules: Dict of rule_name -> enabled status from database
    """
    matches = []
    normalized = normalize_text(text)
    
    # For each enabled rule in database, get compiled pattern and check
    for rule_name, is_enabled in enabled_rules.items():
        if not is_enabled:
            continue
        
        # Get compiled pattern from cache (or compile if first time)
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
                pass  # Skip patterns that cause runtime errors
    
    return matches


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DETECTION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_triggers(text: str, trigger_lemmas: set[str], regex_rules_enabled: dict[str, bool]) -> DetectionResult:
    """
    Main trigger detection function.
    
    1. Checks exclusions
    2. Searches by lemmas (primary layer)
    3. Searches by regex (secondary layer)
    4. Returns detailed result
    
    Args:
        text: текст для проверки
        trigger_lemmas: набор лемм для детекции
        regex_rules_enabled: словарь {rule_name: enabled} для regex-правил
    """
    if not text or not text.strip():
        return DetectionResult(triggered=False, matches=[])
    
    # Проверка исключений
    excluded, exclusion_reason = check_exclusions(text)
    if excluded:
        return DetectionResult(
            triggered=False,
            matches=[],
            excluded=True,
            exclusion_reason=exclusion_reason,
        )
    
    all_matches = []
    
    # Слой 1: леммы
    lemma_matches = detect_by_lemmas(text, trigger_lemmas)
    all_matches.extend(lemma_matches)
    
    # Слой 2: regex (только если нет совпадений по леммам, или для полноты)
    regex_matches = detect_by_regex(text, regex_rules_enabled)
    
    # Убираем дубликаты (если regex нашёл то же, что и лемма)
    existing_positions = {(m.position_start, m.position_end) for m in all_matches}
    for rm in regex_matches:
        if (rm.position_start, rm.position_end) not in existing_positions:
            all_matches.append(rm)
    
    # Сортируем по позиции
    all_matches.sort(key=lambda m: m.position_start)
    
    return DetectionResult(
        triggered=len(all_matches) > 0,
        matches=all_matches,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ ДЛЯ ОТОБРАЖЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def format_match_for_message(match: MatchDetail) -> str:
    """Форматирует совпадение для сообщения бота."""
    if match.match_type == MatchType.LEMMA:
        return f'🔤 Слово: <b>{match.matched_fragment}</b> → лемма: <code>{match.lemma}</code>'
    else:
        return f'📝 Паттерн: <b>{match.matched_fragment}</b> → правило: <code>{match.rule_name}</code>'


def format_detection_result(result: DetectionResult) -> str:
    """Форматирует полный результат детекции."""
    if not result.triggered:
        if result.excluded:
            return f"⚪ Исключение: {result.exclusion_reason}"
        return "✅ Триггеров не найдено"
    
    lines = ["🚨 <b>Найдены триггеры:</b>"]
    for i, match in enumerate(result.matches, 1):
        lines.append(f"  {i}. {format_match_for_message(match)}")
    
    return "\n".join(lines)
