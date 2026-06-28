import asyncio
import json
import logging
import os
from typing import List, Tuple
import aiohttp

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", ".")

# Import from metar monitor
from monitors.metar import CORRECTION_WATCH_STATIONS, MetarMonitor


class CorrectionMonitor:
    """
    Моніторить фіксований список станцій тільки для виявлення виправлень METAR.
    Не надсилає сповіщень про нові оновлення — тільки про виправлення.
    """
    def __init__(self):
        self.data_file = os.path.join(DATA_DIR, "correction_data.json")
        # {station_code: {metar_time: str, temp_c: float, temp_f: float}}
        self.station_data = {}
        # {chat_id: True} — хто підписаний на алерти виправлень
        self.subscribers_file = os.path.join(DATA_DIR, "correction_subscribers.json")
        self.subscribers = {}
        self._last_check = None
        self._total_corrections = 0
        self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    self.station_data = json.load(f)
            except Exception:
                self.station_data = {}
        if os.path.exists(self.subscribers_file):
            try:
                with open(self.subscribers_file, "r") as f:
                    self.subscribers = json.load(f)
            except Exception:
                self.subscribers = {}

    def _save(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(self.data_file, "w") as f:
                json.dump(self.station_data, f, indent=2)
            with open(self.subscribers_file, "w") as f:
                json.dump(self.subscribers, f, indent=2)
        except Exception as e:
            logger.error(f"CorrectionMonitor save error: {e}")

    def get_stats(self) -> dict:
        """Статистика моніторингу виправлень."""
        return {
            "total_stations": len(CORRECTION_WATCH_STATIONS),
            "checked_stations": len(self.station_data),
            "last_check": self._last_check,
            "total_corrections": self._total_corrections,
        }

    def subscribe(self, chat_id: str):
        """Підписати чат на алерти виправлень."""
        self.subscribers[chat_id] = True
        self._save()

    def unsubscribe(self, chat_id: str):
        self.subscribers.pop(chat_id, None)
        self._save()

    def is_subscribed(self, chat_id: str) -> bool:
        return self.subscribers.get(chat_id, False)

    async def check_corrections(self, metar_instance) -> List[Tuple]:
        """
        Перевіряє всі 44 станції на виправлення.
        Повертає (chat_id, station, correction_data) для всіх підписників.
        """
        if not self.subscribers:
            return []

        notifications = []

        for code in CORRECTION_WATCH_STATIONS:
            data = await metar_instance.fetch_metar(code)
            if not data:
                await asyncio.sleep(0.2)
                continue

            new_time = data["metar_time"]
            new_temp_c = data["temp_c"]
            new_temp_f = data["temp_f"]

            old = self.station_data.get(code)

            if old is None:
                # Перший запуск — зберігаємо без сповіщення
                self.station_data[code] = {
                    "metar_time": new_time,
                    "temp_c": new_temp_c,
                    "temp_f": new_temp_f,
                }
                continue

            old_time = old.get("metar_time")
            old_temp_c = old.get("temp_c")
            old_temp_f = old.get("temp_f")

            if new_time == old_time and old_temp_c is not None:
                # Той самий час — перевіряємо температуру
                if abs(new_temp_c - old_temp_c) >= 0.5:
                    logger.info(f"CORRECTION: {code} {old_temp_c}°C -> {new_temp_c}°C at {new_time}")
                    correction_data = {
                        **data,
                        "old_temp_c": old_temp_c,
                        "old_temp_f": old_temp_f,
                    }
                    for chat_id in self.subscribers:
                        notifications.append((chat_id, code, correction_data))
                    # Оновлюємо
                    self.station_data[code]["temp_c"] = new_temp_c
                    self.station_data[code]["temp_f"] = new_temp_f

            elif new_time != old_time:
                # Новий METAR — просто оновлюємо дані
                self.station_data[code] = {
                    "metar_time": new_time,
                    "temp_c": new_temp_c,
                    "temp_f": new_temp_f,
                }

            await asyncio.sleep(0.2)

        from datetime import datetime, timezone
        self._last_check = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        self._total_corrections += len(notifications)
        self._save()
        return notifications
