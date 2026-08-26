import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> dict:
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_E = _load_env()

BOT_TOKEN = _E.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = _E.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = _E.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# The analyst. Swap to claude-opus-5 here if you want the sharper (and pricier) read.
ANTHROPIC_MODEL = _E.get("ANTHROPIC_MODEL") or "claude-sonnet-5"
OPENROUTER_MODEL = _E.get("OPENROUTER_MODEL") or f"anthropic/{ANTHROPIC_MODEL}"
MODEL = ANTHROPIC_MODEL if ANTHROPIC_API_KEY else OPENROUTER_MODEL
WEB_MAX_USES = 6          # searches allowed per web-enabled step
MOCK_LLM = (_E.get("MOCK_LLM") or "").strip() == "1"   # canned answers, no API key needed

DB_PATH = ROOT / "bot.db"
EXPORT_DIR = ROOT / "exports"

ADMIN_ID = 429388141          # unlimited, free, sees debug

# ---------------- monetization (Telegram Stars, 1:1) ----------------
FULL_COST = 30                # all 8 steps
FAST_COST = 12                # short route: 1-2-5-7-8
NEW_USER_FREE_RUNS = 1        # first analysis on the house
REFERRAL_REWARD = 1           # free runs granted per qualified referral
TOPUP_PACKAGES = [25, 50, 100, 250, 500]

REGEN_LIMIT = 3               # "поправить" retries per step before it costs a top-up
TG_LIMIT = 3900               # safe chunk size for one Telegram message

# ---------------- "Запуск": paid track, settled by hand ----------------
# Off until the artefacts exist; while it is False only the admin sees the offer.
LAUNCH_ENABLED = (_E.get("LAUNCH_ENABLED") or "").strip() == "1"
LAUNCH_PRICE = int(_E.get("LAUNCH_PRICE") or 3900)     # rubles
PAY_DETAILS = _E.get("PAY_DETAILS") or ""              # e.g. "+7 900 000-00-00 (СБП, Тинькофф)"
PAY_NAME = _E.get("PAY_NAME") or ""                    # who the transfer should name
