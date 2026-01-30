"""
Bot command handlers.

User commands:
- /start, /help, /counter, /leaderboard, /triggers, /reset, /undo

Admin commands:
- /addword, /removeword, /enablerule, /disablerule
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
    """Format time elapsed since datetime as human-readable string."""
    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    
    if seconds < 60:
        return f"{seconds} сек. назад"
    elif seconds < 3600:
        return f"{seconds // 60} мин. назад"
    elif seconds < 86400:
        return f"{seconds // 3600} ч. назад"
    else:
        return f"{seconds // 86400} дн. назад"


async def is_admin(message: Message) -> bool:
    """Check if user is chat administrator or owner."""
    if message.chat.type == "private":
        return True
    
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, (ChatMemberOwner, ChatMemberAdministrator))
    except Exception as e:
        logger.warning(f"Failed to check admin status for user {message.from_user.id}: {e}")
        return False

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome message and quick start guide."""
    text = """
🤖 <b>Счётчик Триггеров v2</b>

Привет! Я бот для отслеживания стриков в чатах. Считаю время с последнего упоминания триггерных слов и показываю, кто его сломал.

<b>Как это работает:</b>
• Время идёт непрерывно с момента последнего сброса
• Кто-то пишет триггерное слово → стрик сбрасывается
• Я показываю детали: кто, когда и каким словом

<b>🔍 Умная детекция:</b>
• Распознаю любые формы слова (тесты, тестом, тестировать)
• Ловлю обходы: t3st, т е с т, тёst
• Вижу транслит: test → тест, привет → privet

<b>📋 Основные команды:</b>
/counter — текущий стрик и статистика
/leaderboard — топ ломателей стрика
/triggers — список триггерных слов
/help — справка по всем командам
/help full — подробная справка с детекцией

<b>⚙️ Для администраторов:</b>
/addword — добавить триггер
/removeword — удалить триггер

Готов к работе! 🚀
"""
    await message.reply(text.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# /help
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("help"))
async def cmd_help(message: Message, command: CommandObject):
    """Detailed command reference with optional verbose mode."""
    verbose = command.args and "full" in command.args.lower()
    
    if verbose:
        # Full help with detection details
        text = """
📚 <b>Полная справка по командам</b>

<b>📊 Просмотр информации:</b>
/counter — текущий стрик, лучший результат и детали последнего сброса
/leaderboard — топ-5 пользователей, которые чаще всего ломают стрик
/triggers — список активных триггерных слов
/triggers full — подробный список с regex-правилами и примерами

<b>🔧 Управление стриком:</b>
/reset [причина] — ручной сброс стрика (с необязательной причиной)
/undo [N] — откатить последние N событий (по умолчанию 1, максимум 10)

<b>⚙️ Админ-команды (только для администраторов):</b>
/addword слово — добавить новое триггерное слово
  <i>Автоматически создаёт правила для детекции обходов</i>

/removeword слово — удалить триггерное слово
  <i>Удаляет слово и все связанные правила</i>

/enablerule название — включить regex-правило
/disablerule название — выключить regex-правило
  <i>Используйте /triggers full чтобы увидеть все правила</i>

<b>🔍 Как работает детекция:</b>

<b>1. Лемматизация (pymorphy3)</b>
Слова приводятся к нормальной форме. Например, "тесты", "тестом", "тестировать" → "тест"

<b>2. Regex-паттерны (обход детекции)</b>
• <b>Транслитерация:</b> привет → privet, test → тест
• <b>Замена букв:</b> test → t3st, тест → т3ст, а → a
• <b>Разделители:</b> test → t e s t, t.e.s.t
• <b>Невидимые символы:</b> test с Unicode-пробелами
• <b>Диакритика:</b> test → tëst, tést
• <b>Комбинации:</b> privet → p r i v e t

<b>3. Исключения (НЕ считаются триггерами)</b>
• Слова в кавычках: "test" или «тест»
• Часть URL: https://test.com
• В контексте команд: /triggers test

<b>💡 Примеры использования:</b>

Обычная работа:
  /counter — проверить текущий стрик
  
Админ добавляет слово:
  /addword гигачат
  
Кто-то пишет слово → стрик сброшен
  
Ошибочный сброс:
  /undo — откатить последнее событие
  
Ручной сброс:
  /reset конец недели

<b>ℹ️ Особенности:</b>
• Каждый чат имеет свои триггеры
• История событий сохраняется
• Undo работает даже после нескольких сбросов
• Все действия логируются
"""
    else:
        # Basic help without detection details
        text = """
📚 <b>Справка по командам</b>

<b>📊 Просмотр информации:</b>
/counter — текущий стрик и статистика
/leaderboard — топ-5 ломателей стрика
/triggers — список триггерных слов
/triggers full — подробный список с правилами

<b>🔧 Управление:</b>
/reset [причина] — ручной сброс стрика
/undo [N] — откатить последние N событий (1-10)

<b>⚙️ Администрирование:</b>
/addword слово — добавить триггерное слово
/removeword слово — удалить триггерное слово
/enablerule название — включить regex-правило
/disablerule название — выключить regex-правило

<b>ℹ️ Прочее:</b>
/start — приветствие и краткая инструкция
/help — эта справка
/help full — подробная справка с детекцией

<i>💡 Бот автоматически распознаёт любые формы слов и ловит обходы (l33t speak, транслит, разделители). Подробнее: /help full</i>
"""
    
    await message.reply(text.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# /counter
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("counter"))
async def cmd_counter(message: Message):
    """Display current streak, best streak, and last reset details."""
    chat_id = message.chat.id
    state = await get_chat_state(chat_id)
    
    current_streak_str = state.format_current_streak()
    best_streak_str = state.format_best_streak()
    
    lines = [
        "📊 <b>Статистика стрика</b>",
        "",
        f"⏱ <b>Текущий стрик:</b> {current_streak_str}",
        f"🏆 <b>Лучший стрик:</b> {best_streak_str}",
        f"🔄 <b>Всего сбросов:</b> {state.total_resets}",
    ]
    
    if state.last_reset_user_id:
        lines.extend([
            "",
            "📌 <b>Последний сброс:</b>",
            f"👤 {state.last_reset_username or 'Неизвестный'}",
        ])
        
        if state.last_reset_timestamp:
            lines.append(f"🕐 {format_timedelta(state.last_reset_timestamp)}")
        
        if state.last_reset_details:
            details = state.last_reset_details
            if details.get("type") == "manual":
                reason = details.get("reason", "")
                if reason:
                    lines.append(f"📝 Причина: {reason}")
                else:
                    lines.append(f"📝 Ручной сброс")
            elif "matches" in details and details["matches"]:
                first_match = details["matches"][0]
                match_type = first_match.get("match_type", "unknown")
                fragment = first_match.get("matched_fragment", "?")
                
                if match_type == "lemma":
                    lemma = first_match.get("lemma", "?")
                    lines.append(f"🔤 Слово: <b>{fragment}</b> → лемма <code>{lemma}</code>")
                else:
                    rule = first_match.get("rule_name", "?")
                    lines.append(f"📝 Паттерн: <b>{fragment}</b> → правило <code>{rule}</code>")
    
    await message.reply("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# /reset
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("reset"))
async def cmd_reset(message: Message, command: CommandObject):
    """Manual streak reset with optional reason."""
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
        f"👤 {username or 'Неизвестный'}",
        f"📊 Был стрик: <b>{old_streak_str}</b>",
    ]
    
    if reason:
        lines.append(f"📝 Причина: <i>{reason}</i>")
    
    lines.append("\n⏱ Счётчик начинается заново")
    await message.reply("\n".join(lines))
    logger.info(f"Manual reset in chat {chat_id} by user {user_id}: {reason or 'no reason'}")


# ═══════════════════════════════════════════════════════════════════════════════
# /undo
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("undo"))
async def cmd_undo(message: Message, command: CommandObject):
    """Undo last N events (1-10, default 1)."""
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    username = get_username(message)
    
    count = 1
    if command.args:
        try:
            count = int(command.args.strip())
            if count < 1:
                count = 1
            elif count > 10:
                count = 10
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
        await message.reply("⚠️ Нечего откатывать — история пуста")
        return
    
    lines = [f"↩️ <b>Откачено событий: {actual_count}</b>", ""]
    
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
        
        lines.append(f"{event_type_emoji} {event_desc} от {event.username or 'Неизвестный'}")
    
    lines.extend(["", f"📊 Восстановлен стрик: <b>{restored_state.format_current_streak()}</b>"])
    await message.reply("\n".join(lines))
    logger.info(f"Undo {actual_count} events in chat {chat_id} by user {user_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# /leaderboard
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    """Top 5 streak breakers leaderboard."""
    chat_id = message.chat.id
    breakers = await get_breakers_leaderboard(chat_id, limit=5)
    state = await get_chat_state(chat_id)
    
    lines = [
        "🏆 <b>Рейтинг</b>",
        "",
        f"📊 <b>Этот чат:</b>",
        f"⏱ Текущий стрик: <b>{state.format_current_streak()}</b>",
        f"🏅 Лучший стрик: <b>{state.format_best_streak()}</b>",
        f"🔄 Всего сбросов: {state.total_resets}",
    ]
    
    if breakers:
        lines.extend(["", "💀 <b>Топ ломателей стрика:</b>"])
        medals = ["🥇", "🥈", "🥉"]
        
        for i, b in enumerate(breakers):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            raw_name = b["username"] or f"User {b['user_id']}"
            name = raw_name.lstrip('@')
            total = b["total_breaks"]
            triggers = b["trigger_count"]
            manual = b["manual_reset_count"]
            
            detail = []
            if triggers > 0:
                detail.append(f"{triggers} триггер{'ов' if triggers != 1 else ''}")
            if manual > 0:
                detail.append(f"{manual} ручных")
            
            detail_str = f" ({', '.join(detail)})" if detail else ""
            lines.append(f"{medal} <b>{name}</b> — {total} сброс{'ов' if total != 1 else ''}{detail_str}")
    else:
        lines.extend(["", "💀 <b>Ломателей пока нет</b>", "<i>Будьте первым! 😈</i>"])
    
    await message.reply("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# /triggers (or /words)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("triggers", "words"))
async def cmd_triggers(message: Message, command: CommandObject):
    """List trigger words and regex patterns (add 'full' for details)."""
    chat_id = message.chat.id
    verbose = command.args and "full" in command.args.lower()
    
    await get_chat_triggers(chat_id)
    lemmas_data = await get_all_trigger_lemmas(chat_id)
    enabled_lemmas = [l for l, enabled in lemmas_data if enabled]
    
    lines = ["🎯 <b>Триггерные слова</b>", ""]
    
    if enabled_lemmas:
        lemma_groups = [enabled_lemmas[i:i+5] for i in range(0, len(enabled_lemmas), 5)]
        for group in lemma_groups:
            lines.append(", ".join(f"<code>{l}</code>" for l in group))
    else:
        lines.append("<i>Нет активных триггеров</i>")
    
    if verbose:
        regex_rules = await get_all_regex_rules(chat_id)
        active_rules = [(name, enabled) for name, enabled in regex_rules if enabled]
        disabled_rules = [(name, enabled) for name, enabled in regex_rules if not enabled]
        
        rule_descriptions = {r.name: r.description for r in REGEX_RULES}
        rule_examples = {r.name: r.examples for r in REGEX_RULES}
        
        if active_rules:
            lines.extend(["", f"📝 <b>Активные правила ({len(active_rules)}):</b>"])
            
            for name, _ in active_rules:
                desc = rule_descriptions.get(name, "")
                lines.append(f"✅ <code>{name}</code>")
                if desc:
                    lines.append(f"   <i>{desc}</i>")
                
                examples = rule_examples.get(name, [])
                if examples:
                    examples_str = ", ".join(f"«{e}»" for e in examples[:3])
                    lines.append(f"   Примеры: {examples_str}")
        
        if disabled_rules:
            lines.extend(["", f"⏸ <b>Отключённые правила ({len(disabled_rules)}):</b>"])
            for name, _ in disabled_rules:
                desc = rule_descriptions.get(name, "")
                lines.append(f"❌ <code>{name}</code>" + (f" — {desc}" if desc else ""))
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
    """Add trigger word (admin only). Auto-generates regex evasion variants."""
    if not await is_admin(message):
        await message.reply("⚠️ Команда только для администраторов")
        return
    
    if not command.args:
        await message.reply("⚠️ Укажите слово\n\nПример: /addword гигачат")
        return
    
    word = command.args.strip().lower()
    if len(word) < 2:
        await message.reply("⚠️ Слово слишком короткое (минимум 2 символа)")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    await get_chat_triggers(chat_id)
    success = await add_trigger_lemma(chat_id, word, user_id)
    
    if success:
        await message.reply(
            f"✅ Слово <code>{word}</code> добавлено\n\n"
            f"<i>Автоматически созданы правила для обнаружения обходов</i>"
        )
        logger.info(f"Admin {user_id} added trigger '{word}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Не удалось добавить слово <code>{word}</code>")


@router.message(Command("removeword"))
async def cmd_removeword(message: Message, command: CommandObject):
    """Remove trigger word (admin only). Removes associated regex variants."""
    if not await is_admin(message):
        await message.reply("⚠️ Команда только для администраторов")
        return
    
    if not command.args:
        await message.reply("⚠️ Укажите слово\n\nПример: /removeword гигачат")
        return
    
    word = command.args.strip().lower()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    await get_chat_triggers(chat_id)
    success = await remove_trigger_lemma(chat_id, word)
    
    if success:
        await message.reply(f"✅ Слово <code>{word}</code> удалено")
        logger.info(f"Admin {user_id} removed trigger '{word}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Слово <code>{word}</code> не найдено в триггерах")


@router.message(Command("enablerule"))
async def cmd_enablerule(message: Message, command: CommandObject):
    """Enable regex rule (admin only)."""
    if not await is_admin(message):
        await message.reply("⚠️ Команда только для администраторов")
        return
    
    if not command.args:
        rule_names = ", ".join(f"<code>{r.name}</code>" for r in REGEX_RULES)
        await message.reply(
            f"⚠️ Укажите имя правила\n\n"
            f"Доступные правила:\n{rule_names}\n\n"
            f"<i>Или используйте /triggers full</i>"
        )
        return
    
    rule_name = command.args.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    await get_chat_triggers(chat_id)
    success = await toggle_regex_rule(chat_id, rule_name, True)
    
    if success:
        await message.reply(f"✅ Правило <code>{rule_name}</code> включено")
        logger.info(f"Admin {user_id} enabled rule '{rule_name}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Правило <code>{rule_name}</code> не найдено")


@router.message(Command("disablerule"))
async def cmd_disablerule(message: Message, command: CommandObject):
    """Disable regex rule (admin only)."""
    if not await is_admin(message):
        await message.reply("⚠️ Команда только для администраторов")
        return
    
    if not command.args:
        rule_names = ", ".join(f"<code>{r.name}</code>" for r in REGEX_RULES)
        await message.reply(
            f"⚠️ Укажите имя правила\n\n"
            f"Доступные правила:\n{rule_names}\n\n"
            f"<i>Или используйте /triggers full</i>"
        )
        return
    
    rule_name = command.args.strip()
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    
    await get_chat_triggers(chat_id)
    success = await toggle_regex_rule(chat_id, rule_name, False)
    
    if success:
        await message.reply(f"✅ Правило <code>{rule_name}</code> выключено")
        logger.info(f"Admin {user_id} disabled rule '{rule_name}' in chat {chat_id}")
    else:
        await message.reply(f"⚠️ Правило <code>{rule_name}</code> не найдено")
