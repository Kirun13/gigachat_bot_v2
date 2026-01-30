"""
Message handler for trigger detection.

Processes all incoming messages (text, captions, media) for trigger words
using the two-tier detection system (lemmas + regex patterns).
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
    """Extract username or full name from message."""
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
    """Format streak broken notification with trigger details."""
    duration_str = format_duration(old_streak_seconds)
    
    lines = [
        "🚨 <b>Стрик сломан!</b>",
        "",
        f"👤 {username}",
        f"📊 Был стрик: <b>{duration_str}</b>",
        "",
        "🔍 <b>Сработало:</b>",
    ]
    
    for match in result.matches:
        lines.append(f"• {format_match_for_message(match)}")
    
    lines.extend(["", "⏱ Счётчик начинается заново"])
    return "\n".join(lines)


@router.message(F.text & ~F.text.startswith('/'))
async def handle_text_message(message: Message):
    """
    Handle text messages (excluding commands).
    
    1. Check text for triggers
    2. If triggered - reset streak and notify
    3. If not - streak continues
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    text = message.text or ""
    
    await start_streak_if_needed(chat_id)
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
            username=username or "Unknown",
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
    """Process media captions (non-commands) for triggers."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    text = message.caption
    
    await start_streak_if_needed(chat_id)
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
            username=username or "Unknown",
            old_streak_seconds=old_streak_seconds,
            result=result,
        )
        
        await message.reply(response)


@router.message(~F.text & ~F.caption)
async def handle_other_message(message: Message):
    """
    Handle non-text messages (stickers, GIFs, etc.).
    Ensures streak continues running.
    """
    chat_id = message.chat.id
    await start_streak_if_needed(chat_id)
