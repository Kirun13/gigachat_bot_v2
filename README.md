# Counter Bot v2

Telegram bot for tracking "streaks" in chats with trigger word detection using **lemmas** (pymorphy3) and **regex patterns**.

## Features

- **Two-tier detection:**
  - Primary layer: word lemmas with pymorphy3 (automatic word form normalization)
  - Secondary layer: regex patterns (catch variants, slang, evasion techniques)
  
- **Event-sourcing storage (SQLite):**
  - `events` table — source of truth
  - `chat_state` table — cached current state
  - `chat_triggers` table — per-chat trigger configuration
  - Correct undo even after multiple resets
  
- **Dynamic trigger management:**
  - Add/remove trigger words via commands
  - Auto-generates regex variants for evasion detection (spaced letters, l33t speak)
  - Per-chat trigger configuration
  
- **Transparency:**
  - Shows who/when/what broke the streak
  - Displays original form + lemma and/or regex rule name

## Commands

### User Commands
| Command | Description |
|---------|----------|
| `/start` | Welcome message and brief help |
| `/help` | Detailed command reference |
| `/counter` | Current streak + last reset info |
| `/reset [reason]` | Manual streak reset (recorded as event) |
| `/undo [N]` | Undo last N events (default 1, max 10) |
| `/leaderboard` | Top streak breakers in chat |
| `/triggers` | List trigger words |
| `/triggers full` | Detailed list with regex patterns |

### Admin Commands
| Command | Description |
|---------|----------|
| `/addword <word>` | Add trigger word (auto-generates regex variants) |
| `/removeword <word>` | Remove trigger word (removes variants too) |
| `/enablerule <name>` | Enable regex pattern |
| `/disablerule <name>` | Disable regex pattern |

## Project Structure

```
coutner_bot_v2/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entry point
│   ├── config.py        # Default trigger configuration
│   ├── db.py            # Event-sourcing SQLite database
│   ├── detect.py        # Trigger detection logic
│   └── handlers/
│       ├── __init__.py
│       ├── messages.py  # Message handlers
│       └── commands.py  # Bot commands
├── data/
│   └── bot.db           # SQLite database (auto-created)
├── requirements.txt
└── README.md
```

## Installation

```bash
# Clone repository
cd coutner_bot_v2

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo BOT_TOKEN=your_telegram_bot_token > .env

# Run bot
python -m bot.main
```

## Trigger Configuration

Default triggers are configured in `bot/config.py`:

- **TRIGGER_LEMMAS** — set of default lemmas for new chats
- **generate_regex_variants_for_word()** — generates evasion-detection patterns
- **EXCLUSION_PATTERNS** — exceptions (don't count as triggers)

Once deployed, triggers are managed per-chat via `/addword` and `/removeword` commands.

### How Regex Variants Work

When you add a word like "test" using `/addword test`, the bot automatically generates:
1. **Spaced variant**: `t\s{0,2}e\s{0,2}s\s{0,2}t` - catches "t e s t", "test", etc.
2. **L33t speak variant**: `[t][e3е][s5ѕ][t]` - catches "t3st", "te5t", etc.

These variants are stored in the database and enabled/disabled independently.

## Architecture

The bot uses **event sourcing** pattern:
- All changes are recorded as events in `events` table
- Current state is cached in `chat_state` table (recalculated from events)
- Undo works by replaying events from history
- Supports rollback even after multiple resets

## License

MIT
