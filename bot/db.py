"""
Event-sourcing storage on SQLite.

Architecture:
- events: source of truth (all changes)
- chat_state: cached current state (recalculated from events)
- chat_triggers: triggers per chat (lemmas + regex rules)

Event types:
- TRIGGER: automatic trigger detection
- MANUAL_RESET: manual reset via /reset command
- UNDO: rollback of previous event
"""

import json
import aiosqlite
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Any

from bot.config import DATABASE_PATH, TRIGGER_LEMMAS, REGEX_RULES

# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE OPTIMIZATION: In-Memory Trigger Cache
# ═══════════════════════════════════════════════════════════════════════════════
# Chat triggers are cached in memory to avoid DB I/O on every message
# This provides ~10-50ms speedup per message

_trigger_cache: dict[int, tuple[dict, datetime]] = {}
_CACHE_TTL = timedelta(minutes=5)  # Cache expires after 5 minutes


class EventType(str, Enum):
    """Event types."""
    TRIGGER = "TRIGGER"           # Automatic trigger detection
    MANUAL_RESET = "MANUAL_RESET" # Manual reset
    UNDO = "UNDO"                 # Event rollback


@dataclass
class Event:
    """System event."""
    id: Optional[int]
    chat_id: int
    event_type: EventType
    user_id: int
    username: Optional[str]
    message_id: Optional[int]
    timestamp: datetime
    details: dict                  # Details: match_info, reason, etc.
    snapshot: dict                 # State snapshot BEFORE event (for undo)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "username": self.username,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "snapshot": self.snapshot,
        }
    
    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Event":
        return cls(
            id=row["id"],
            chat_id=row["chat_id"],
            event_type=EventType(row["event_type"]),
            user_id=row["user_id"],
            username=row["username"],
            message_id=row["message_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            details=json.loads(row["details"]),
            snapshot=json.loads(row["snapshot"]),
        )


@dataclass
class ChatState:
    """Current chat state (cache)."""
    chat_id: int
    streak_start: Optional[datetime]  # When current streak started
    best_streak_seconds: int          # Best streak in seconds
    best_streak_start: Optional[datetime]
    best_streak_end: Optional[datetime]
    last_reset_event_id: Optional[int]
    last_reset_user_id: Optional[int]
    last_reset_username: Optional[str]
    last_reset_timestamp: Optional[datetime]
    last_reset_details: Optional[dict]
    total_resets: int
    
    @classmethod
    def default(cls, chat_id: int) -> "ChatState":
        return cls(
            chat_id=chat_id,
            streak_start=None,
            best_streak_seconds=0,
            best_streak_start=None,
            best_streak_end=None,
            last_reset_event_id=None,
            last_reset_user_id=None,
            last_reset_username=None,
            last_reset_timestamp=None,
            last_reset_details=None,
            total_resets=0,
        )
    
    def get_current_streak_seconds(self) -> int:
        """Returns current streak in seconds."""
        if self.streak_start is None:
            return 0
        delta = datetime.now(timezone.utc) - self.streak_start
        return int(delta.total_seconds())
    
    def format_current_streak(self) -> str:
        """Formats current streak in human-readable format."""
        return format_duration(self.get_current_streak_seconds())
    
    def format_best_streak(self) -> str:
        """Formats best streak in human-readable format."""
        return format_duration(self.best_streak_seconds)
    
    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "ChatState":
        return cls(
            chat_id=row["chat_id"],
            streak_start=datetime.fromisoformat(row["streak_start"]) if row["streak_start"] else None,
            best_streak_seconds=row["best_streak_seconds"],
            best_streak_start=datetime.fromisoformat(row["best_streak_start"]) if row["best_streak_start"] else None,
            best_streak_end=datetime.fromisoformat(row["best_streak_end"]) if row["best_streak_end"] else None,
            last_reset_event_id=row["last_reset_event_id"],
            last_reset_user_id=row["last_reset_user_id"],
            last_reset_username=row["last_reset_username"],
            last_reset_timestamp=datetime.fromisoformat(row["last_reset_timestamp"]) if row["last_reset_timestamp"] else None,
            last_reset_details=json.loads(row["last_reset_details"]) if row["last_reset_details"] else None,
            total_resets=row["total_resets"],
        )
    
    def to_snapshot(self) -> dict:
        """Создаёт снимок состояния для сохранения в событии."""
        return {
            "streak_start": self.streak_start.isoformat() if self.streak_start else None,
            "best_streak_seconds": self.best_streak_seconds,
            "best_streak_start": self.best_streak_start.isoformat() if self.best_streak_start else None,
            "best_streak_end": self.best_streak_end.isoformat() if self.best_streak_end else None,
            "last_reset_event_id": self.last_reset_event_id,
            "last_reset_user_id": self.last_reset_user_id,
            "last_reset_username": self.last_reset_username,
            "last_reset_timestamp": self.last_reset_timestamp.isoformat() if self.last_reset_timestamp else None,
            "last_reset_details": self.last_reset_details,
            "total_resets": self.total_resets,
        }
    
    @classmethod
    def from_snapshot(cls, chat_id: int, snapshot: dict) -> "ChatState":
        """Восстанавливает состояние из снимка."""
        return cls(
            chat_id=chat_id,
            streak_start=datetime.fromisoformat(snapshot["streak_start"]) if snapshot.get("streak_start") else None,
            best_streak_seconds=snapshot.get("best_streak_seconds", 0),
            best_streak_start=datetime.fromisoformat(snapshot["best_streak_start"]) if snapshot.get("best_streak_start") else None,
            best_streak_end=datetime.fromisoformat(snapshot["best_streak_end"]) if snapshot.get("best_streak_end") else None,
            last_reset_event_id=snapshot.get("last_reset_event_id"),
            last_reset_user_id=snapshot.get("last_reset_user_id"),
            last_reset_username=snapshot.get("last_reset_username"),
            last_reset_timestamp=datetime.fromisoformat(snapshot["last_reset_timestamp"]) if snapshot.get("last_reset_timestamp") else None,
            last_reset_details=snapshot.get("last_reset_details"),
            total_resets=snapshot.get("total_resets", 0),
        )


def format_duration(seconds: int) -> str:
    """Форматирует длительность в человекочитаемый формат."""
    if seconds <= 0:
        return "0 минут"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0 or not parts:
        parts.append(f"{minutes} мин.")
    
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ БД
# ═══════════════════════════════════════════════════════════════════════════════

async def init_database():
    """Создаёт таблицы, если их нет."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица событий (источник истины)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                message_id INTEGER,
                timestamp TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                snapshot TEXT NOT NULL DEFAULT '{}',
                
                -- Индексы для быстрого поиска
                CONSTRAINT valid_event_type CHECK (
                    event_type IN ('TRIGGER', 'MANUAL_RESET', 'UNDO')
                )
            )
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_chat_id ON events(chat_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id)
        """)
        
        # Таблица состояния чатов (кэш) - обновлённая для времени
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_state (
                chat_id INTEGER PRIMARY KEY,
                streak_start TEXT,
                best_streak_seconds INTEGER NOT NULL DEFAULT 0,
                best_streak_start TEXT,
                best_streak_end TEXT,
                last_reset_event_id INTEGER,
                last_reset_user_id INTEGER,
                last_reset_username TEXT,
                last_reset_timestamp TEXT,
                last_reset_details TEXT,
                total_resets INTEGER NOT NULL DEFAULT 0,
                
                FOREIGN KEY (last_reset_event_id) REFERENCES events(id)
            )
        """)
        
        # Таблица статистики пользователей (агрегат для leaderboard)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                trigger_count INTEGER NOT NULL DEFAULT 0,
                manual_reset_count INTEGER NOT NULL DEFAULT 0,
                
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        # Таблица триггеров для каждого чата
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_triggers (
                chat_id INTEGER NOT NULL,
                trigger_type TEXT NOT NULL,
                value TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                added_by_user_id INTEGER,
                added_at TEXT,
                
                PRIMARY KEY (chat_id, trigger_type, value),
                CONSTRAINT valid_trigger_type CHECK (trigger_type IN ('lemma', 'regex'))
            )
        """)
        
        await db.commit()
        
        # Инициализируем глобальные триггеры для новых чатов (они будут копироваться при первом использовании)
        await _ensure_global_triggers_table(db)


async def _ensure_global_triggers_table(db):
    """Создаёт таблицу глобальных триггеров по умолчанию."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS global_triggers (
            trigger_type TEXT NOT NULL,
            value TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            
            PRIMARY KEY (trigger_type, value)
        )
    """)
    await db.commit()
    
    # Проверяем, есть ли уже данные
    cursor = await db.execute("SELECT COUNT(*) FROM global_triggers")
    row = await cursor.fetchone()
    if row[0] == 0:
        # Заполняем из config.py
        for lemma in TRIGGER_LEMMAS:
            await db.execute(
                "INSERT OR IGNORE INTO global_triggers (trigger_type, value, enabled) VALUES (?, ?, ?)",
                ("lemma", lemma, 1)
            )
        for rule in REGEX_RULES:
            await db.execute(
                "INSERT OR IGNORE INTO global_triggers (trigger_type, value, enabled) VALUES (?, ?, ?)",
                ("regex", rule.name, 1 if rule.enabled else 0)
            )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# ОПЕРАЦИИ С СОБЫТИЯМИ
# ═══════════════════════════════════════════════════════════════════════════════

async def get_chat_state(chat_id: int) -> ChatState:
    """Получает текущее состояние чата (или создаёт дефолтное)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM chat_state WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return ChatState.from_row(row)
        return ChatState.default(chat_id)


async def save_chat_state(state: ChatState):
    """Сохраняет состояние чата в кэш."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO chat_state (
                chat_id, streak_start, best_streak_seconds,
                best_streak_start, best_streak_end,
                last_reset_event_id, last_reset_user_id, last_reset_username,
                last_reset_timestamp, last_reset_details, total_resets
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.chat_id,
            state.streak_start.isoformat() if state.streak_start else None,
            state.best_streak_seconds,
            state.best_streak_start.isoformat() if state.best_streak_start else None,
            state.best_streak_end.isoformat() if state.best_streak_end else None,
            state.last_reset_event_id,
            state.last_reset_user_id,
            state.last_reset_username,
            state.last_reset_timestamp.isoformat() if state.last_reset_timestamp else None,
            json.dumps(state.last_reset_details) if state.last_reset_details else None,
            state.total_resets,
        ))
        await db.commit()


async def save_event(event: Event) -> int:
    """Сохраняет событие и возвращает его ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO events (
                chat_id, event_type, user_id, username, message_id,
                timestamp, details, snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.chat_id,
            event.event_type.value,
            event.user_id,
            event.username,
            event.message_id,
            event.timestamp.isoformat(),
            json.dumps(event.details),
            json.dumps(event.snapshot),
        ))
        await db.commit()
        return cursor.lastrowid


async def update_user_stats(chat_id: int, user_id: int, username: Optional[str], 
                            event_type: EventType):
    """Обновляет статистику пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Upsert статистики
        await db.execute("""
            INSERT INTO user_stats (chat_id, user_id, username, trigger_count, manual_reset_count)
            VALUES (?, ?, ?, 0, 0)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = COALESCE(excluded.username, user_stats.username)
        """, (chat_id, user_id, username))
        
        if event_type == EventType.TRIGGER:
            await db.execute("""
                UPDATE user_stats 
                SET trigger_count = trigger_count + 1
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
        elif event_type == EventType.MANUAL_RESET:
            await db.execute("""
                UPDATE user_stats 
                SET manual_reset_count = manual_reset_count + 1
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
        
        await db.commit()


async def decrement_user_stats(chat_id: int, user_id: int, event_type: EventType):
    """Уменьшает статистику пользователя (при undo)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if event_type == EventType.TRIGGER:
            await db.execute("""
                UPDATE user_stats 
                SET trigger_count = CASE WHEN trigger_count > 0 THEN trigger_count - 1 ELSE 0 END
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
        elif event_type == EventType.MANUAL_RESET:
            await db.execute("""
                UPDATE user_stats 
                SET manual_reset_count = CASE WHEN manual_reset_count > 0 THEN manual_reset_count - 1 ELSE 0 END
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
        
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРИМЕНЕНИЕ СОБЫТИЙ
# ═══════════════════════════════════════════════════════════════════════════════

async def apply_trigger_event(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    message_id: int,
    match_details: dict,
) -> tuple[Event, ChatState, int]:
    """
    Применяет событие TRIGGER.
    Возвращает (event, new_state, old_streak_seconds).
    """
    now = datetime.now(timezone.utc)
    
    # Получаем текущее состояние
    old_state = await get_chat_state(chat_id)
    old_streak_seconds = old_state.get_current_streak_seconds()
    
    # Создаём событие со снимком текущего состояния
    event = Event(
        id=None,
        chat_id=chat_id,
        event_type=EventType.TRIGGER,
        user_id=user_id,
        username=username,
        message_id=message_id,
        timestamp=now,
        details=match_details,
        snapshot=old_state.to_snapshot(),
    )
    
    # Сохраняем событие
    event_id = await save_event(event)
    event.id = event_id
    
    # Обновляем лучший стрик если нужно
    new_best_seconds = old_state.best_streak_seconds
    new_best_start = old_state.best_streak_start
    new_best_end = old_state.best_streak_end
    
    if old_streak_seconds > old_state.best_streak_seconds:
        new_best_seconds = old_streak_seconds
        new_best_start = old_state.streak_start
        new_best_end = now
    
    # Вычисляем новое состояние
    new_state = ChatState(
        chat_id=chat_id,
        streak_start=now,  # Новый стрик начинается сейчас
        best_streak_seconds=new_best_seconds,
        best_streak_start=new_best_start,
        best_streak_end=new_best_end,
        last_reset_event_id=event_id,
        last_reset_user_id=user_id,
        last_reset_username=username,
        last_reset_timestamp=now,
        last_reset_details=match_details,
        total_resets=old_state.total_resets + 1,
    )
    
    # Сохраняем состояние
    await save_chat_state(new_state)
    
    # Обновляем статистику пользователя
    await update_user_stats(chat_id, user_id, username, EventType.TRIGGER)
    
    return event, new_state, old_streak_seconds


async def apply_manual_reset_event(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    reason: str = "",
) -> tuple[Event, ChatState, int]:
    """
    Применяет событие MANUAL_RESET.
    Возвращает (event, new_state, old_streak_seconds).
    """
    now = datetime.now(timezone.utc)
    
    old_state = await get_chat_state(chat_id)
    old_streak_seconds = old_state.get_current_streak_seconds()
    
    event = Event(
        id=None,
        chat_id=chat_id,
        event_type=EventType.MANUAL_RESET,
        user_id=user_id,
        username=username,
        message_id=None,
        timestamp=now,
        details={"reason": reason},
        snapshot=old_state.to_snapshot(),
    )
    
    event_id = await save_event(event)
    event.id = event_id
    
    # Обновляем лучший стрик если нужно
    new_best_seconds = old_state.best_streak_seconds
    new_best_start = old_state.best_streak_start
    new_best_end = old_state.best_streak_end
    
    if old_streak_seconds > old_state.best_streak_seconds:
        new_best_seconds = old_streak_seconds
        new_best_start = old_state.streak_start
        new_best_end = now
    
    new_state = ChatState(
        chat_id=chat_id,
        streak_start=now,
        best_streak_seconds=new_best_seconds,
        best_streak_start=new_best_start,
        best_streak_end=new_best_end,
        last_reset_event_id=event_id,
        last_reset_user_id=user_id,
        last_reset_username=username,
        last_reset_timestamp=now,
        last_reset_details={"type": "manual", "reason": reason},
        total_resets=old_state.total_resets + 1,
    )
    
    await save_chat_state(new_state)
    await update_user_stats(chat_id, user_id, username, EventType.MANUAL_RESET)
    
    return event, new_state, old_streak_seconds


async def apply_undo_event(
    chat_id: int,
    user_id: int,
    username: Optional[str],
    count: int = 1,
) -> tuple[list[Event], ChatState, int]:
    """
    Откатывает последние N событий (не UNDO).
    Возвращает (undone_events, restored_state, actual_count).
    """
    now = datetime.now(timezone.utc)
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Находим последние N событий, которые не UNDO
        cursor = await db.execute("""
            SELECT * FROM events 
            WHERE chat_id = ? AND event_type != 'UNDO'
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, count))
        rows = await cursor.fetchall()
    
    if not rows:
        # Нечего откатывать
        state = await get_chat_state(chat_id)
        return [], state, 0
    
    undone_events = [Event.from_row(row) for row in rows]
    actual_count = len(undone_events)
    
    # Восстанавливаем состояние из снимка самого старого откатываемого события
    oldest_event = undone_events[-1]  # Последний в списке = самый старый
    restored_state = ChatState.from_snapshot(chat_id, oldest_event.snapshot)
    
    # Сохраняем UNDO-событие
    current_state = await get_chat_state(chat_id)
    undo_event = Event(
        id=None,
        chat_id=chat_id,
        event_type=EventType.UNDO,
        user_id=user_id,
        username=username,
        message_id=None,
        timestamp=now,
        details={
            "undone_event_ids": [e.id for e in undone_events],
            "undone_count": actual_count,
        },
        snapshot=current_state.to_snapshot(),
    )
    await save_event(undo_event)
    
    # Применяем восстановленное состояние
    await save_chat_state(restored_state)
    
    # Корректируем статистику пользователей
    for event in undone_events:
        await decrement_user_stats(chat_id, event.user_id, event.event_type)
    
    return undone_events, restored_state, actual_count


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПРОСЫ ДЛЯ LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════════

async def get_chat_leaderboard(limit: int = 10) -> list[dict]:
    """Топ чатов по лучшему стрику."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT chat_id, streak_start, best_streak_seconds, total_resets
            FROM chat_state
            ORDER BY best_streak_seconds DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        
        return [
            {
                "chat_id": row["chat_id"],
                "streak_start": row["streak_start"],
                "best_streak_seconds": row["best_streak_seconds"],
                "total_resets": row["total_resets"],
            }
            for row in rows
        ]


async def get_breakers_leaderboard(chat_id: int, limit: int = 10) -> list[dict]:
    """Топ "ломателей" стрика в конкретном чате."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT user_id, username, trigger_count, manual_reset_count,
                   (trigger_count + manual_reset_count) as total_breaks
            FROM user_stats
            WHERE chat_id = ?
            ORDER BY total_breaks DESC
            LIMIT ?
        """, (chat_id, limit))
        rows = await cursor.fetchall()
        
        return [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "trigger_count": row["trigger_count"],
                "manual_reset_count": row["manual_reset_count"],
                "total_breaks": row["total_breaks"],
            }
            for row in rows
        ]


async def get_recent_events(chat_id: int, limit: int = 10) -> list[Event]:
    """Получает последние события в чате."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM events
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))
        rows = await cursor.fetchall()
        
        return [Event.from_row(row) for row in rows]


async def start_streak_if_needed(chat_id: int):
    """Начинает стрик, если он ещё не начат."""
    state = await get_chat_state(chat_id)
    
    if state.streak_start is None:
        state.streak_start = datetime.now(timezone.utc)
        await save_chat_state(state)
    
    return state


# ═══════════════════════════════════════════════════════════════════════════════
# УПРАВЛЕНИЕ ТРИГГЕРАМИ
# ═══════════════════════════════════════════════════════════════════════════════

def invalidate_trigger_cache(chat_id: int):
    """
    Invalidate the trigger cache for a specific chat.
    Call this whenever triggers are modified (add/remove/enable/disable).
    """
    _trigger_cache.pop(chat_id, None)


def clear_all_trigger_caches():
    """Clear all trigger caches (useful for testing or global updates)."""
    global _trigger_cache
    _trigger_cache.clear()


async def get_chat_triggers(chat_id: int, force_refresh: bool = False) -> dict:
    """
    Получает триггеры для чата (или копирует глобальные).
    
    Performance optimization: Results are cached in memory with TTL.
    
    Args:
        chat_id: Chat ID
        force_refresh: If True, bypass cache and fetch from DB
    
    Returns:
        Dict with "lemmas" (set) and "regex_rules" (dict)
    """
    # Check cache first (unless force_refresh)
    if not force_refresh and chat_id in _trigger_cache:
        cached_data, cached_time = _trigger_cache[chat_id]
        age = datetime.now(timezone.utc) - cached_time
        
        if age < _CACHE_TTL:
            # Cache hit - return cached data
            return cached_data
    
    # Cache miss or expired - fetch from database
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Проверяем, есть ли триггеры для этого чата
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM chat_triggers WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cursor.fetchone()
        
        if row["cnt"] == 0:
            # Копируем глобальные триггеры
            await db.execute("""
                INSERT INTO chat_triggers (chat_id, trigger_type, value, enabled)
                SELECT ?, trigger_type, value, enabled FROM global_triggers
            """, (chat_id,))
            await db.commit()
        
        # Получаем триггеры
        cursor = await db.execute(
            "SELECT trigger_type, value, enabled FROM chat_triggers WHERE chat_id = ?",
            (chat_id,)
        )
        rows = await cursor.fetchall()
        
        lemmas = []
        regex_rules = {}
        
        for row in rows:
            if row["trigger_type"] == "lemma":
                if row["enabled"]:
                    lemmas.append(row["value"])
            elif row["trigger_type"] == "regex":
                regex_rules[row["value"]] = bool(row["enabled"])
        
        result = {
            "lemmas": set(lemmas),
            "regex_rules": regex_rules,
        }
        
        # Update cache
        _trigger_cache[chat_id] = (result, datetime.now(timezone.utc))
        
        return result


async def add_trigger_lemma(chat_id: int, lemma: str, user_id: int) -> bool:
    """
    Adds a lemma to chat triggers and generates associated regex variants.
    Returns True if added successfully.
    """
    from bot.config import generate_regex_variants_for_word
    
    lemma = lemma.lower().strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            # Add the lemma
            await db.execute("""
                INSERT INTO chat_triggers (chat_id, trigger_type, value, enabled, added_by_user_id, added_at)
                VALUES (?, 'lemma', ?, 1, ?, ?)
            """, (chat_id, lemma, user_id, datetime.now(timezone.utc).isoformat()))
            
            # Generate and add regex variants for this word
            regex_variants = generate_regex_variants_for_word(lemma)
            for variant in regex_variants:
                try:
                    # Store regex pattern name in database
                    await db.execute("""
                        INSERT OR IGNORE INTO chat_triggers (chat_id, trigger_type, value, enabled, added_by_user_id, added_at)
                        VALUES (?, 'regex', ?, ?, ?, ?)
                    """, (chat_id, variant["name"], 1 if variant["enabled"] else 0, user_id, datetime.now(timezone.utc).isoformat()))
                except Exception as e:
                    # Don't fail if regex variant insertion fails
                    pass
            
            await db.commit()
            
            # Invalidate cache after modification
            invalidate_trigger_cache(chat_id)
            
            return True
        except aiosqlite.IntegrityError:
            # Already exists, enable it
            await db.execute("""
                UPDATE chat_triggers SET enabled = 1
                WHERE chat_id = ? AND trigger_type = 'lemma' AND value = ?
            """, (chat_id, lemma))
            await db.commit()
            
            # Invalidate cache after modification
            invalidate_trigger_cache(chat_id)
            
            return True


async def remove_trigger_lemma(chat_id: int, lemma: str) -> bool:
    """
    Removes a lemma from chat triggers and its associated regex variants.
    Returns True if removed successfully.
    """
    lemma = lemma.lower().strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM chat_triggers
            WHERE chat_id = ? AND trigger_type = 'lemma' AND value = ?
        """, (chat_id, lemma))
        
        deleted = cursor.rowcount > 0
        
        if deleted:
            # Also remove associated regex variants (they follow naming pattern: {word}_*)
            await db.execute("""
                DELETE FROM chat_triggers
                WHERE chat_id = ? AND trigger_type = 'regex' AND value LIKE ?
            """, (chat_id, f"{lemma}_%"))
        
        await db.commit()
        
        # Invalidate cache after modification
        if deleted:
            invalidate_trigger_cache(chat_id)
        
        return deleted


async def toggle_regex_rule(chat_id: int, rule_name: str, enabled: bool) -> bool:
    """Toggles regex rule on/off. Returns True if found."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE chat_triggers SET enabled = ?
            WHERE chat_id = ? AND trigger_type = 'regex' AND value = ?
        """, (1 if enabled else 0, chat_id, rule_name))
        await db.commit()
        
        modified = cursor.rowcount > 0
        
        # Invalidate cache after modification
        if modified:
            invalidate_trigger_cache(chat_id)
        
        return modified


async def get_all_trigger_lemmas(chat_id: int) -> list[str]:
    """Получает все леммы (включая отключённые) для отображения."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT value, enabled FROM chat_triggers
            WHERE chat_id = ? AND trigger_type = 'lemma'
            ORDER BY value
        """, (chat_id,))
        rows = await cursor.fetchall()
        return [(row["value"], bool(row["enabled"])) for row in rows]


async def get_all_regex_rules(chat_id: int) -> list[tuple[str, bool]]:
    """Get all regex rules for display."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT value, enabled FROM chat_triggers
            WHERE chat_id = ? AND trigger_type = 'regex'
            ORDER BY value
        """, (chat_id,))
        rows = await cursor.fetchall()
        return [(row["value"], bool(row["enabled"])) for row in rows]


async def clear_chat_data(chat_id: int, admin_user_id: int, admin_username: Optional[str]) -> dict:
    """
    Clear all data for specific chat only.
    Deletes: events, chat_state, chat_triggers, user_stats.
    
    Args:
        chat_id: ID of chat to clear
        admin_user_id: ID of admin performing action
        admin_username: Username of admin performing action
    
    Returns:
        dict with counts of deleted records
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Count records before deletion
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM events WHERE chat_id = ?", (chat_id,))
        events_count = (await cursor.fetchone())["cnt"]
        
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM chat_triggers WHERE chat_id = ?", (chat_id,))
        triggers_count = (await cursor.fetchone())["cnt"]
        
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM user_stats WHERE chat_id = ?", (chat_id,))
        users_count = (await cursor.fetchone())["cnt"]
        
        # Delete all data for this chat
        await db.execute("DELETE FROM events WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM chat_state WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM chat_triggers WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM user_stats WHERE chat_id = ?", (chat_id,))
        
        await db.commit()
    
    # Clear cache for this chat
    if chat_id in _trigger_cache:
        del _trigger_cache[chat_id]
    
    return {
        "events": events_count,
        "triggers": triggers_count,
        "users": users_count,
    }
