import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATA_DIR = os.environ.get("DATA_DIR", ".")

# Conversation states
WAITING_ADDRESS = 1
WAITING_NICKNAME = 2
WAITING_TYPE = 3
WAITING_METAR = 4

# Intervals
POLYMARKET_CHECK_INTERVAL = 30   # секунд
METAR_CHECK_INTERVAL = 60        # секунд
HOURLY_INTERVAL = 3600           # секунд
DAILY_INTERVAL = 86400           # секунд
