# Counter Bot v2

Telegram bot for tracking "streaks" in group chats with intelligent trigger word detection. Uses **lemmatization** (pymorphy3) and **regex patterns** to catch trigger words even when obfuscated.

## Features

### 🔍 Intelligent Detection System

- **Two-tier detection:**
  - **Primary layer**: Lemma-based detection with pymorphy3 (automatic word form normalization)
  - **Secondary layer**: Regex patterns (catch variants, slang, evasion techniques)
  
- **Advanced evasion detection:**
  - Transliteration: test ↔ тест, привет ↔ privet
  - Character substitution: test → t3st, тест → т3ст
  - Spaced characters: test → t e s t
  - Zero-width characters: invisible Unicode
  - Diacritics: test → tëst, tést
  - Multi-modal combinations

### 📊 Event Sourcing Architecture

- `events` table — source of truth for all changes
- `chat_state` table — cached current state for fast lookups
- `chat_triggers` table — per-chat trigger configuration
- Full undo support even after multiple resets

### ⚙️ Dynamic Configuration

- Add/remove trigger words via commands
- Auto-generates regex variants for evasion detection
- Per-chat trigger configuration
- Enable/disable specific detection rules

### 📈 Statistics & Transparency

- Shows who/when/what broke the streak
- Displays original form + lemma/regex rule name
- Leaderboard of top streak breakers
- Event history with full details

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and quick start guide |
| `/help` | Brief command reference |
| `/help full` | Detailed reference with detection system explanation |
| `/counter` | Current streak + last reset details |
| `/leaderboard` | Top 5 streak breakers in chat |
| `/triggers` | Simple list of trigger words |
| `/triggers full` | Detailed list with regex patterns and examples |
| `/reset [reason]` | Manual streak reset (recorded as event) |
| `/undo [N]` | Undo last N events (default 1, max 10) |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/addword <word>` | Add trigger word (auto-generates regex variants) |
| `/removeword <word>` | Remove trigger word (removes variants too) |
| `/enablerule <name>` | Enable specific regex pattern |
| `/disablerule <name>` | Disable specific regex pattern |

**Note:** All bot messages are in Russian. Code comments and docstrings are in English.

## Project Structure

```
coutner_bot_v2/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entry point
│   ├── config.py        # Trigger configuration and regex generators
│   ├── db.py            # Event-sourcing SQLite database
│   ├── detect.py        # Trigger detection logic (lemmas + regex)
│   └── handlers/
│       ├── __init__.py
│       ├── messages.py  # Message handlers (trigger detection)
│       └── commands.py  # Bot commands (/start, /help, etc.)
├── data/
│   └── bot.db           # SQLite database (auto-created)
├── requirements.txt     # Python dependencies
├── README.md            # This file
├── COMMANDS.md          # Command reference for BotFather (Russian)
├── CHANGELOG.md         # Version history
└── REFACTORING_SUMMARY.md  # Refactoring details
```

## Installation

### Prerequisites

- Python 3.10+
- pip
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Setup

```bash
# Clone repository
cd coutner_bot_v2

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with your bot token
echo BOT_TOKEN=your_telegram_bot_token_here > .env

# Run bot
python -m bot.main
```

### Configure BotFather

1. Open [@BotFather](https://t.me/botfather) in Telegram
2. Select your bot
3. Use `/setcommands` and paste the command list from `COMMANDS.md`
4. Use `/setdescription` to set bot description
5. Use `/setabouttext` to set short description

See `COMMANDS.md` for ready-to-paste text in Russian.

## Trigger Configuration

### Default Setup

Default triggers are configured in `bot/config.py`:

```python
TRIGGER_LEMMAS: set[str] = {
    "test",  # Add your default triggers here
}
```

### Runtime Configuration

Once deployed, triggers are managed per-chat via commands:

```
/addword гигачат
/addword example
/removeword test
```

### Auto-Generated Detection Variants

When you add a word like "тест" using `/addword тест`, the bot automatically creates:

1. **Transliteration**: `test` ↔ `тест`
2. **Lookalike**: Character substitutions (cyrillic/latin/leet)
3. **Spaced**: `t\s*e\s*s\s*t` - catches "t e s t", etc.
4. **Zero-width**: Invisible Unicode characters between letters
5. **Diacritics**: Unicode normalization variants
6. **Multi-modal**: Combined patterns (transliteration + spacing)

These variants are stored in the database and can be enabled/disabled independently with `/enablerule` and `/disablerule`.

### Exclusion Patterns

The following are **NOT** counted as triggers:

- Words in quotation marks: `"test"` or `«тест»`
- URLs: `https://test.com`
- Bot command context: `/triggers test`

## Architecture

### Event Sourcing Pattern

The bot uses **event sourcing** for data persistence:

- All changes are recorded as events in `events` table
- Current state is cached in `chat_state` table (recalculated from events)
- Undo works by replaying events from history
- Supports rollback even after multiple resets

### Event Types

```python
class EventType(str, Enum):
    TRIGGER = "TRIGGER"           # Automatic trigger detection
    MANUAL_RESET = "MANUAL_RESET" # Manual reset via /reset
    UNDO = "UNDO"                 # Event rollback
```

### Database Schema

```sql
-- Event log (source of truth)
events (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    event_type TEXT,
    user_id INTEGER,
    username TEXT,
    message_id INTEGER,
    timestamp TEXT,
    details TEXT,  -- JSON
    snapshot TEXT  -- JSON: state before event
)

-- Current state (cached, recalculated from events)
chat_state (
    chat_id INTEGER PRIMARY KEY,
    streak_start TEXT,
    best_streak_seconds INTEGER,
    last_reset_user_id INTEGER,
    last_reset_username TEXT,
    last_reset_timestamp TEXT,
    last_reset_details TEXT,  -- JSON
    total_resets INTEGER
)

-- Per-chat trigger configuration
chat_triggers (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    trigger_type TEXT,  -- 'lemma' or 'regex'
    trigger_value TEXT,
    enabled INTEGER,
    created_by INTEGER,
    created_at TEXT
)
```

## Detection System

### How It Works

#### 1. Lemma-Based Detection (Primary Layer)

Uses **pymorphy3** morphological analyzer:
- Automatically handles word forms (case, tense, number, gender)
- Language-aware for Russian, English, and Kazakh
- Example: "тесты", "тестом", "тестировать" all match trigger "тест"

#### 2. Regex Pattern Detection (Secondary Layer)

Catches creative spelling and evasion attempts:
- Patterns are auto-generated for each trigger word
- Compiled patterns are cached for performance
- Multiple pattern types to catch different evasion techniques

#### 3. Exclusion Check

Messages matching exclusion patterns are ignored:
- Quotations (word appears in quotes)
- URLs (word is part of URL)
- Command context (word used in bot commands)

### Detection Flow

```
Message received
    ↓
Check exclusions → Excluded? → Ignore
    ↓
Tokenize text
    ↓
Check lemmas → Match? → Trigger!
    ↓
Check regex patterns → Match? → Trigger!
    ↓
No matches → Continue streak
```

## Performance Optimizations

### In-Memory Caching

- **Trigger cache**: Reduces database I/O (~10-50ms speedup per message)
- **Compiled regex cache**: Avoids pattern recompilation (~2-3ms speedup)
- **Cache TTL**: 5 minutes for trigger cache

### Async Operations

- Non-blocking database operations
- Concurrent message processing
- Efficient event log writing

## Usage Examples

### Basic Workflow

```bash
# Start bot in a chat
/start

# Check current streak
/counter

# View active triggers
/triggers

# Add custom trigger (admin)
/addword гигачат

# Someone mentions the word → streak resets automatically

# Check leaderboard
/leaderboard

# Undo accidental trigger
/undo
```

### Admin Configuration

```bash
# Add multiple triggers
/addword chatgpt
/addword claude
/addword gemini

# View all detection rules
/triggers full

# Fine-tune detection sensitivity
/disablerule chatgpt_zerowidth
/disablerule claude_translit_en

# Remove unwanted trigger
/removeword gemini
```

### Advanced Usage

```bash
# Manual reset with reason
/reset конец недели

# Undo multiple events
/undo 5

# View detailed help
/help full

# Enable specific detection rule
/enablerule test_spaced
```

## Development

### Code Structure

- **English**: Code comments, docstrings, variable names
- **Russian**: User-facing messages, command responses
- **Type hints**: Used throughout for better IDE support
- **Async/await**: For all I/O operations

### Key Files

- `bot/config.py`: Trigger configuration and regex pattern generators
- `bot/detect.py`: Detection logic (lemmas + regex)
- `bot/db.py`: Event sourcing implementation
- `bot/handlers/commands.py`: Command handlers
- `bot/handlers/messages.py`: Message processing

### Adding New Features

1. Keep event sourcing pattern
2. Add new event types if needed
3. Update database schema with migrations
4. Maintain backward compatibility
5. Add tests for new detection patterns

## Troubleshooting

### Bot doesn't start

```bash
# Check token is set
cat .env

# Check dependencies installed
pip install -r requirements.txt

# Check Python version
python --version  # Should be 3.10+
```

### Detection not working

```bash
# Check triggers are configured
/triggers full

# Test with simple word
/addword test

# Check exclusions
# Words in quotes are ignored by design
```

### Performance issues

- Check cache settings in `bot/db.py` (CACHE_TTL)
- Review regex complexity in `bot/config.py`
- Consider disabling unused detection rules

## Contributing

1. Keep code comments in English
2. Keep user messages in Russian
3. Maintain event sourcing architecture
4. Add tests for new detection patterns
5. Update documentation

## License

MIT

## Credits

- **aiogram**: Async Telegram Bot framework
- **pymorphy3**: Morphological analyzer for Russian/Ukrainian/Kazakh
- **aiosqlite**: Async SQLite wrapper

## Links

- **Telegram Bot API**: https://core.telegram.org/bots/api
- **aiogram Documentation**: https://docs.aiogram.dev/
- **pymorphy3 Documentation**: https://pymorphy3.readthedocs.io/
