"""
Bot commands: /start, /help, /counter, /reset, /undo, /leaderboard, /triggers.
Admin commands: /addword, /removeword, /enablerule, /disablerule.
"""

import logging
from datetime import datetime, timezone
from aiogram import Router
from aiogram.types import Message, ChatMemberOwner, ChatMemberAdministrator
from aiogram.filters import Command, CommandObject

from bot.db import (
    get_chat_state,
    apply_manual_reset_event,
    apply_undo_event,
    get_breakers_leaderboard,
    get_chat_triggers,
    add_trigger_lemma,
    remove_trigger_lemma,
    toggle_regex_rule,
    get_all_trigger_lemmas,
    get_all_regex_rules,
    format_duration,
    EventType,
)
from bot.config import REGEX_RULES

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


def format_timedelta(dt: datetime) -> str:
    """Formats time elapsed since dt."""
    now = datetime.now(timezone.utc)
    delta = now - dt
    
    seconds = int(delta.total_seconds())
    
    if seconds < 60:
        return f"{seconds} сек. назад"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин. назад"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} ч. назад"
    else:
        days = seconds // 86400
        return f"{days} дн. назад"


async def is_admin(message: Message) -> bool:
    """Checks if user is chat administrator."""
    if message.chat.type == "private":
        return True  # All commands available in private chat
    
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, (ChatMemberOwner, ChatMemberAdministrator))
    except Exception as e:
        logger.warning(f"Failed to check admin status for user {message.from_user.id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome message and brief help."""
    text = """
🤖 <b>Счётчик Гигачата v2</b>

Привет! Я отслеживаю, сколько времени прошло с последнего упоминания триггерных слов.

<b>Как это работает:</b>
• Время идёт с момента последнего сброса
• При срабатывании триггера — счётчик сбрасывается
• Я показываю, кто и чем сломал стрик

<b>Основные команды:</b>
/counter — текущий стрик
/leaderboard — топ ломателей
/triggers — список триггеров
/help — полная справка

Начинаем! 🚀
"""
    await message.reply(text.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# /help
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Detailed command reference."""
    text = """
📚 <b>Справка по командам</b>

<b>📊 Информация:</b>
/counter — текущий стрик (время) и инфо о последнем сбросе
/leaderboard — топ "ломателей" стрика
/triggers — список триггер-слов
/triggers full — подробный список с regex-правилами

<b>⚙️ Управление:</b>
/reset [причина] — ручной сброс стрика
/undo [N] — откат последних N событий (по умолчанию 1)

<b>👮 Админ-команды:</b>
/addword слово — добавить триггер-слово
/removeword слово — удалить триггер-слово
/enablerule имя — включить regex-правило
/disablerule имя — выключить regex-правило

<b>ℹ️ Прочее:</b>
/start — приветствие
/help — эта справка

<b>Как работает детекция:</b>
1️⃣ <b>Леммы</b> — слова приводятся к нормальной форме (pymorphy3)
2️⃣ <b>Regex</b> — дополнительные паттерны (сленг, латиница, обходы)
"""
    await message.reply(text.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# /counter
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("counter"))
async def cmd_counter(message: Message):
    """Current streak and last reset info."""
    chat_id = message.chat.id
    state = await get_chat_state(chat_id)
    
    current_streak_str = state.format_current_streak()
    best_streak_str = state.format_best_streak()
    
    lines = [
        "📊 <b>Статус счётчика</b>",
        "",
        f"⏱ Текущий стрик: <b>{current_streak_str}</b>",
        f"🏆 Лучший стрик: <b>{best_streak_str}</b>",
        f"🔄 Всего сбросов: <b>{state.total_resets}</b>",
    ]
    
    if state.last_reset_user_id:
        lines.extend([
            "",
            "📌 <b>Последний сброс:</b>",
            f"  👤 Кто: {state.last_reset_username or 'Неизвестный'}",
        ])
        
        if state.last_reset_timestamp:
            lines.append(f"  ⏰ Когда: {format_timedelta(state.last_reset_timestamp)}")
        
        if state.last_reset_details:
            details = state.last_reset_details
            if details.get("type") == "manual":
                reason = details.get("reason", "не указана")
                lines.append(f"  📝 Причина: ручной сброс" + (f" ({reason})" if reason else ""))
            elif "matches" in details and details["matches"]:
                first_match = details["matches"][0]
                match_type = first_match.get("match_type", "unknown")
                fragment = first_match.get("matched_fragment", "?")
                
                if match_type == "lemma":
                    lemma = first_match.get("lemma", "?")
                    lines.append(f"  🔤 Чем: «{fragment}» (лемма: {lemma})")
                else:
                    rule = first_match.get("rule_name", "?")
                    lines.append(f"  📝 Чем: «{fragment}» (правило: {rule})")
    
    await message.reply("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# /reset
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("reset"))
async def cmd_reset(message: Message, command: CommandObject):
    """Manual streak reset."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    reason = command.args or ""
    
    old_state = await get_chat_state(chat_id)
    old_streak_seconds = old_state.get_current_streak_seconds()
    old_streak_str = format_duration(old_streak_seconds)
    
    event, new_state, _ = await apply_manual_reset_event(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        reason=reason,
    )
    
    lines = [
        "🔄 <b>Стрик сброшен вручную</b>",
        "",
        f"👤 Кто: {username or 'Неизвестный'}",
        f"📊 Был стрик: <b>{old_streak_str}</b>",
    ]
    
    if reason:
        lines.append(f"📝 Причина: {reason}")
    
    lines.append("\n⏱ Счётчик начинается заново")
    
    await message.reply("\n".join(lines))
    
    logger.info(f"Manual reset in chat {chat_id} by user {user_id}: {reason or 'no reason'}")


# ═══════════════════════════════════════════════════════════════════════════════
# /undo
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("undo"))
async def cmd_undo(message: Message, command: CommandObject):
    """Undo last N events."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    
    # Парсим количество
    count = 1
    if command.args:
        try:
            count = int(command.args.strip())
            if count < 1:
                count = 1
            elif count > 10:
                count = 10  # Лимит
        except ValueError:
            await message.reply("⚠️ Укажите число от 1 до 10. Пример: /undo 3")
            return
    
    undone_events, restored_state, actual_count = await apply_undo_event(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        count=count,
    )
    
    if actual_count == 0:
        await message.reply("⚠️ Нечего откатывать — история пуста.")
        return
    
    lines = [
        f"↩️ <b>Откачено событий: {actual_count}</b>",
        "",
    ]
    
    for event in undone_events:
        event_type_emoji = {
            EventType.TRIGGER: "🚨",
            EventType.MANUAL_RESET: "🔄",
        }.get(event.event_type, "❓")
        
        event_desc = ""
        if event.event_type == EventType.TRIGGER:
            matches = event.details.get("matches", [])
            if matches:
                first = matches[0]
                event_desc = f"триггер «{first.get('matched_fragment', '?')}»"
            else:
                event_desc = "триггер"
        elif event.event_type == EventType.MANUAL_RESET:
            event_desc = "ручной сброс"
        
        lines.append(f"  {event_type_emoji} {event_desc} от {event.username or 'Неизвестный'}")
    
    lines.extend([
        "",
        f"📊 Восстановленный стрик: <b>{restored_state.format_current_streak()}</b>",
    ])
    
    await message.reply("\n".join(lines))
    
    logger.info(f"Undo {actual_count} events in chat {chat_id} by user {user_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# /leaderboard
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    """Top streak breakers leaderboard."""
    chat_id = message.chat.id
    
    # Топ ломателей в этом чате
    breakers = await get_breakers_leaderboard(chat_id, limit=5)
    
    # Текущее состояние чата
    state = await get_chat_state(chat_id)
    
    lines = [
        "🏆 <b>Leaderboard</b>",
        "",
        f"📊 <b>Этот чат:</b>",
        f"  • Текущий стрик: <b>{state.format_current_streak()}</b>",
        f"  • Лучший стрик: <b>{state.format_best_streak()}</b>",
        f"  • Всего сбросов: {state.total_resets}",
    ]
    
    if breakers:
        lines.extend([
            "",
            "💀 <b>Топ ломателей стрика:</b>",
        ])
        
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        
        for i, b in enumerate(breakers):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            # Remove @ from username if present
            raw_name = b["username"] or f"User {b['user_id']}"
            name = raw_name.lstrip('@')
            total = b["total_breaks"]
            triggers = b["trigger_count"]
            manual = b["manual_reset_count"]
            
            detail = []
            if triggers > 0:
                detail.append(f"{triggers} триггер{'ов' if triggers > 1 else ''}")
            if manual > 0:
                detail.append(f"{manual} ручн.")
            
            detail_str = f" ({', '.join(detail)})" if detail else ""
            lines.append(f"  {medal} {name}: <b>{total}</b> сбросов{detail_str}")
    else:
        lines.extend([
            "",
            "💀 <b>Топ ломателей:</b> пока пусто",
        ])
    
    await message.reply("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# /triggers (or /words)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("triggers", "words"))
async def cmd_triggers(message: Message, command: CommandObject):
    """List of trigger words and regex patterns."""
    chat_id = message.chat.id
    
    # Проверяем флаг подробного вывода
    verbose = command.args and "full" in command.args.lower()
    
    # Получаем триггеры для этого чата (инициализирует если нужно)
    await get_chat_triggers(chat_id)
    
    # Получаем все леммы
    lemmas_data = await get_all_trigger_lemmas(chat_id)
    enabled_lemmas = [l for l, enabled in lemmas_data if enabled]
    
    lines = [
        "🎯 <b>Триггер-слова</b>",
        "",
    ]
    
    if enabled_lemmas:
        # Группируем по 5 в строке
        lemma_groups = [enabled_lemmas[i:i+5] for i in range(0, len(enabled_lemmas), 5)]
        for group in lemma_groups:
            lines.append(", ".join(f"<code>{l}</code>" for l in group))
    else:
        lines.append("<i>Нет триггер-слов</i>")
    
    if verbose:
        # Regex-правила
        regex_rules = await get_all_regex_rules(chat_id)
        active_rules = [(name, enabled) for name, enabled in regex_rules if enabled]
        disabled_rules = [(name, enabled) for name, enabled in regex_rules if not enabled]
        
        # Получаем описания из config
        rule_descriptions = {r.name: r.description for r in REGEX_RULES}
        rule_examples = {r.name: r.examples for r in REGEX_RULES}
        
        if active_rules:
            lines.extend([
                "",
                f"📝 <b>Regex-правила ({len(active_rules)} вкл.):</b>",
            ])
            
            for name, _ in active_rules:
                desc = rule_descriptions.get(name, "")
                lines.append(f"  ✅ <code>{name}</code>: {desc}")
                
                examples = rule_examples.get(name, [])
                if examples:
                    examples_str = ", ".join(f"«{e}»" for e in examples[:3])
                    lines.append(f"      <i>Примеры: {examples_str}</i>")
        
        if disabled_rules:
            lines.extend([
                "",
                f"⏸ <b>Отключённые правила ({len(disabled_rules)}):</b>",
            ])
            for name, _ in disabled_rules:
                desc = rule_descriptions.get(name, "")
                lines.append(f"  ❌ <code>{name}</code>: {desc}")
    else:
        lines.extend([
            "",
            f"<i>Всего слов: {len(enabled_lemmas)}</i>",
            "<i>Подробнее: /triggers full</i>",
        ])
    
    await message.reply("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS: trigger management
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("addword"))
async def cmd_addword(message: Message, command: CommandObject):
    """
    Adds a trigger word (admin only).
    Automatically generates regex variants for evasion detection.
    """
    if not await is_admin(message):
        await message.reply("⚠️ Эта команда доступна только администраторам.")
        return
    
    if not command.args:
        await message.reply("⚠️ Укажите слово. Пример: /addword гигачат")
        return
    
    word = command.args.strip().lower()
    if len(word) < 2:
        await message.reply("⚠️ Слово слишком короткое.")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    # Убеждаемся, что триггеры инициализированы
    await get_chat_triggers(chat_id)
    
    success = await add_trigger_lemma(chat_id, word, user_id)
    
    if success:
        await message.reply(f"✅ Слово <code>{word}</code> добавлено в триггеры.")
        logger.info(f"Admin {user_id} added trigger word '{word}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Не удалось добавить слово <code>{word}</code>.")


@router.message(Command("removeword"))
async def cmd_removeword(message: Message, command: CommandObject):
    """
    Removes a trigger word (admin only).
    Also removes associated regex variants.
    """
    if not await is_admin(message):
        await message.reply("⚠️ Эта команда доступна только администраторам.")
        return
    
    if not command.args:
        await message.reply("⚠️ Укажите слово. Пример: /removeword гигачат")
        return
    
    word = command.args.strip().lower()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    # Убеждаемся, что триггеры инициализированы
    await get_chat_triggers(chat_id)
    
    success = await remove_trigger_lemma(chat_id, word)
    
    if success:
        await message.reply(f"✅ Слово <code>{word}</code> удалено из триггеров.")
        logger.info(f"Admin {user_id} removed trigger word '{word}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Слово <code>{word}</code> не найдено в триггерах.")


@router.message(Command("enablerule"))
async def cmd_enablerule(message: Message, command: CommandObject):
    """Enables a regex rule (admin only)."""
    if not await is_admin(message):
        await message.reply("⚠️ Эта команда доступна только администраторам.")
        return
    
    if not command.args:
        rule_names = ", ".join(f"<code>{r.name}</code>" for r in REGEX_RULES)
        await message.reply(f"⚠️ Укажите имя правила.\n\nДоступные правила:\n{rule_names}")
        return
    
    rule_name = command.args.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    # Убеждаемся, что триггеры инициализированы
    await get_chat_triggers(chat_id)
    
    success = await toggle_regex_rule(chat_id, rule_name, True)
    
    if success:
        await message.reply(f"✅ Правило <code>{rule_name}</code> включено.")
        logger.info(f"Admin {user_id} enabled rule '{rule_name}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Правило <code>{rule_name}</code> не найдено.")


@router.message(Command("disablerule"))
async def cmd_disablerule(message: Message, command: CommandObject):
    """Disables a regex rule (admin only)."""
    if not await is_admin(message):
        await message.reply("⚠️ Эта команда доступна только администраторам.")
        return
    
    if not command.args:
        rule_names = ", ".join(f"<code>{r.name}</code>" for r in REGEX_RULES)
        await message.reply(f"⚠️ Укажите имя правила.\n\nДоступные правила:\n{rule_names}")
        return
    
    rule_name = command.args.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    # Убеждаемся, что триггеры инициализированы
    await get_chat_triggers(chat_id)
    
    success = await toggle_regex_rule(chat_id, rule_name, False)
    
    if success:
        await message.reply(f"✅ Правило <code>{rule_name}</code> выключено.")
        logger.info(f"Admin {user_id} disabled rule '{rule_name}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Правило <code>{rule_name}</code> не найдено.")
