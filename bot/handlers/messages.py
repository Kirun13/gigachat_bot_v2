"""
Message handler: trigger detection and state updates.
Processes all incoming messages (text, captions, media) for trigger words.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message

from bot.detect import detect_triggers, format_match_for_message, DetectionResult
from bot.db import (
    apply_trigger_event,
    start_streak_if_needed,
    get_chat_state,
    get_chat_triggers,
    format_duration,
)

logger = logging.getLogger(__name__)
router = Router()


def get_username(message: Message) -> str | None:
    """Gets username or full name of user."""
    user = message.from_user
    if not user:
        return None
    if user.username:
        return f"@{user.username}"
    return user.full_name


def format_streak_broken_message(
    username: str,
    old_streak_seconds: int,
    result: DetectionResult,
) -> str:
    """Formats streak broken notification message."""
    duration_str = format_duration(old_streak_seconds)
    
    lines = [
        "🚨 <b>Стрик сломан!</b>",
        "",
        f"👤 Кто: {username}",
        f"📊 Был стрик: <b>{duration_str}</b>",
        "",
        "🔍 <b>Причина:</b>",
    ]
    
    for match in result.matches:
        lines.append(f"  • {format_match_for_message(match)}")
    
    lines.extend([
        "",
        "⏱ Счётчик начинается заново",
    ])
    
    return "\n".join(lines)


@router.message(F.text & ~F.text.startswith('/'))
async def handle_text_message(message: Message):
    """
    Обработчик текстовых сообщений (не команд).
    
    1. Проверяет текст на триггеры
    2. Если триггер найден — сбрасывает стрик и уведомляет
    3. Если нет — стрик продолжается (время идёт)
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    text = message.text or ""
    
    # Убеждаемся, что стрик начат
    await start_streak_if_needed(chat_id)
    
    # Получаем триггеры для этого чата
    triggers = await get_chat_triggers(chat_id)
    
    # Детекция триггеров
    result = detect_triggers(text, triggers["lemmas"], triggers["regex_rules"])
    
    if result.triggered:
        # Применяем событие TRIGGER
        event, new_state, old_streak_seconds = await apply_trigger_event(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            message_id=message.message_id,
            match_details=result.to_dict(),
        )
        
        # Отправляем уведомление
        response = format_streak_broken_message(
            username=username or "Неизвестный",
            old_streak_seconds=old_streak_seconds,
            result=result,
        )
        
        await message.reply(response)
        
        logger.info(
            f"Trigger in chat {chat_id} by user {user_id}: "
            f"{result.first_match.format_human() if result.first_match else 'unknown'}"
        )


@router.message(F.caption & ~F.caption.startswith('/'))
async def handle_caption_message(message: Message):
    """Processes media captions (non-commands) for triggers."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    text = message.caption
    
    # Убеждаемся, что стрик начат
    await start_streak_if_needed(chat_id)
    
    # Получаем триггеры для этого чата
    triggers = await get_chat_triggers(chat_id)
    
    result = detect_triggers(text, triggers["lemmas"], triggers["regex_rules"])
    
    if result.triggered:
        event, new_state, old_streak_seconds = await apply_trigger_event(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            message_id=message.message_id,
            match_details=result.to_dict(),
        )
        
        response = format_streak_broken_message(
            username=username or "Неизвестный",
            old_streak_seconds=old_streak_seconds,
            result=result,
        )
        
        await message.reply(response)
    # If not triggered, still count the message by ensuring streak is active (already done above)


@router.message(~F.text & ~F.caption)  # Only non-text, non-caption messages (stickers, GIFs, etc.)
async def handle_other_message(message: Message):
    """
    Processes all other message types (stickers, GIFs, etc.).
    Just ensures streak is running (time counts automatically).
    """
    chat_id = message.chat.id
    await start_streak_if_needed(chat_id)
