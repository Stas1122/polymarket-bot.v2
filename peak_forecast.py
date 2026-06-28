import asyncio
import json
import logging
import os
from typing import List, Tuple
import aiohttp

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", ".")

try:
    from stations_data import STATIONS_META
except ImportError:
    STATIONS_META = {}



# ============ PEAK TEMPERATURE FORECAST MONITOR ============

OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"

try:
    from stations_data import STATIONS_META
except ImportError:
    STATIONS_META = {}


class PeakForecastMonitor:
    """
    Перевіряє прогноз температури для 44 станцій.
    Надсилає алерт якщо максимум температури очікується
    в перші 6 годин місцевого часу доби.
    Алерт надсилається за 3-4 години до опівночі місцевого часу.
    """

    def __init__(self):
        self.data_file = os.path.join(DATA_DIR, "peak_forecast.json")
        # {station: {date: alerted}} — щоб не спамити
        self.alerted = {}
        self.subscribers = {}
        self.subscribers_file = os.path.join(DATA_DIR, "peak_subscribers.json")
        self._load()

    def _load(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    self.alerted = json.load(f)
            except Exception:
                self.alerted = {}
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
                json.dump(self.alerted, f, indent=2)
            with open(self.subscribers_file, "w") as f:
                json.dump(self.subscribers, f, indent=2)
        except Exception as e:
            logger.error(f"PeakForecastMonitor save error: {e}")

    def subscribe(self, chat_id: str):
        self.subscribers[chat_id] = True
        self._save()

    def unsubscribe(self, chat_id: str):
        self.subscribers.pop(chat_id, None)
        self._save()

    def is_subscribed(self, chat_id: str) -> bool:
        return self.subscribers.get(chat_id, False)

    async def fetch_hourly_forecast(self, lat: float, lon: float, tz: str, session: aiohttp.ClientSession) -> list:
        """Отримує погодинний прогноз з Open-Meteo."""
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "temperature_unit": "celsius",
                "timezone": tz,
                "forecast_days": 2
            }
            async with session.get(OPEN_METEO_API, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    times = data["hourly"]["time"]
                    temps = data["hourly"]["temperature_2m"]
                    return list(zip(times, temps))
        except Exception as e:
            logger.error(f"Open-Meteo error: {e}")
        return []

    def _find_peak_in_first_6h(self, hourly: list, target_date: str) -> dict:
        """
        Перевіряє чи максимум температури припадає на перші 6 годин доби.
        target_date формат: "2026-06-25"
        """
        # Всі години цього дня
        day_hours = [(t, temp) for t, temp in hourly if t.startswith(target_date)]
        if not day_hours:
            return None

        # Знаходимо максимум за день
        max_temp = max(temp for _, temp in day_hours)
        max_time = next(t for t, temp in day_hours if temp == max_temp)
        max_hour = int(max_time[11:13])

        # Перевіряємо чи максимум в перші 6 годин (00:00-05:59)
        is_early_peak = max_hour < 6

        return {
            "max_temp": max_temp,
            "max_time": max_time[11:16],
            "max_hour": max_hour,
            "is_early_peak": is_early_peak,
            "all_day": day_hours,
        }

    async def check_forecasts(self) -> List[Tuple]:
        """
        Перевіряє всі станції.
        Надсилає алерт за 3-4 години до опівночі місцевого часу
        якщо максимум очікується в перші 6 годин.
        """
        if not self.subscribers or not STATIONS_META:
            return []

        from datetime import datetime, timezone, timedelta
        import pytz

        notifications = []
        now_utc = datetime.now(timezone.utc)

        async with aiohttp.ClientSession() as session:
            for code, meta in STATIONS_META.items():
                try:
                    tz_str = meta["tz"]
                    local_tz = pytz.timezone(tz_str)
                    now_local = now_utc.astimezone(local_tz)

                    # Перевіряємо чи зараз 20:00-21:00 місцевого (за 3-4 години до опівночі)
                    local_hour = now_local.hour
                    if local_hour not in (20, 21):
                        continue

                    # Завтрашня дата (місцева)
                    tomorrow = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")
                    alert_key = f"{code}_{tomorrow}"

                    # Вже надсилали алерт сьогодні?
                    if self.alerted.get(alert_key):
                        continue

                    # Отримуємо прогноз
                    hourly = await self.fetch_hourly_forecast(
                        meta["lat"], meta["lon"], tz_str, session
                    )
                    if not hourly:
                        continue

                    result = self._find_peak_in_first_6h(hourly, tomorrow)
                    if not result:
                        continue

                    if result["is_early_peak"]:
                        # Знаходимо температуру вдень для порівняння
                        day_temps = [temp for t, temp in result["all_day"] if 10 <= int(t[11:13]) <= 18]
                        day_max = max(day_temps) if day_temps else result["max_temp"]

                        alert_data = {
                            "station": code,
                            "city": meta["name"],
                            "date": tomorrow,
                            "max_temp": result["max_temp"],
                            "max_time": result["max_time"],
                            "day_max": day_max,
                        }

                        for chat_id in self.subscribers:
                            notifications.append((chat_id, alert_data))

                        self.alerted[alert_key] = True
                        logger.info(f"Peak forecast alert for {code}: max {result['max_temp']}°C at {result['max_time']}")

                except Exception as e:
                    logger.error(f"Peak forecast error for {code}: {e}")

                await asyncio.sleep(0.3)

        self._save()
        return notifications
