import asyncio
import json
import logging
import os
import re
from typing import List, Tuple, Dict, Optional
import aiohttp

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", ".")


# ============ METAR MONITOR ============

METAR_API = "https://aviationweather.gov/api/data/metar"

# Станції для моніторингу виправлень (без сповіщень про кожне оновлення)
CORRECTION_WATCH_STATIONS = [
    "NZWN", "WSSS", "EGLC", "RCSS", "RKSI", "ZUCK", "ZSQD", "WMKK",
    "EFHK", "ZSPD", "ZGGG", "VILK", "EHAM", "LFPB", "LTAC", "FACT",
    "EDDM", "RKPK", "LEMD", "ZGSZ", "LTFM", "KMIA", "ZUUU", "EPWA",
    "SBGR", "LLBG", "ZBAA", "LIMC", "OPKC", "KAUS", "OEJN", "KORD",
    "KLGA", "CYYZ", "SAEZ", "KATL", "KLAX", "KSFO", "KBKF", "ZHHH",
    "KHOU", "MPMG", "KSEA", "MMMX"
]

METAR_DATA_FILE = os.path.join(DATA_DIR, "metar_stations.json")


class MetarMonitor:
    def __init__(self):
        self.stations = {}  # {chat_id: [{code, last_metar_time}]}
        self._load()

    def _load(self):
        if os.path.exists(METAR_DATA_FILE):
            try:
                with open(METAR_DATA_FILE, "r") as f:
                    self.stations = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load metar stations: {e}")

    def _save(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(METAR_DATA_FILE, "w") as f:
                json.dump(self.stations, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metar stations: {e}")

    def add_station(self, chat_id: str, code: str) -> str:
        code = code.upper()
        if chat_id not in self.stations:
            self.stations[chat_id] = []
        for s in self.stations[chat_id]:
            if s["code"] == code:
                return "exists"
        self.stations[chat_id].append({
            "code": code,
            "last_metar_time": None,
            "last_temp_c": None,    # для виявлення виправлень
            "last_temp_f": None,
        })
        self._save()
        return "added"

    def remove_station(self, chat_id: str, code: str):
        code = code.upper()
        if chat_id in self.stations:
            self.stations[chat_id] = [
                s for s in self.stations[chat_id] if s["code"] != code
            ]
            self._save()

    def get_stations(self, chat_id: str) -> List[Dict]:
        return self.stations.get(chat_id, [])

    def get_total_stations(self) -> int:
        return sum(len(v) for v in self.stations.values())

    def _parse_metar_temp(self, raw: str):
        import re
        # Точний формат T01720094
        t_match = re.search(r'T(\d{4})(\d{4})', raw)
        if t_match:
            temp_raw = t_match.group(1)
            sign = -1 if temp_raw[0] == '1' else 1
            temp_c = sign * int(temp_raw[1:]) / 10.0
            temp_f = temp_c * 9/5 + 32
            return temp_f, temp_c
        # Стандартний TT/DD
        import re
        temp_match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', raw)
        if temp_match:
            temp_str = temp_match.group(1)
            sign = -1 if temp_str.startswith('M') else 1
            temp_c = sign * int(temp_str.replace('M', ''))
            temp_f = temp_c * 9/5 + 32
            return temp_f, temp_c
        return None

    def _parse_metar_time(self, raw: str) -> str:
        import re
        time_match = re.search(r'\d{6}Z', raw)
        if time_match:
            t = time_match.group(0)
            return f"{t[2:4]}:{t[4:6]} UTC"
        return ""

    async def fetch_metar(self, station: str) -> Dict:
        station = station.upper()
        try:
            async with aiohttp.ClientSession() as session:
                params = {"ids": station, "format": "raw", "taf": "false", "hours": "1"}
                async with session.get(METAR_API, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    text = await resp.text()
                    if not text.strip():
                        return None

                    # Об'єднуємо багаторядкові METAR (MMMX та інші розбивають на 2 рядки)
                    raw_lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
                    merged = []
                    current = ""
                    for line in raw_lines:
                        upper = line.upper()
                        if upper.startswith("METAR") or upper.startswith("SPECI"):
                            if current:
                                merged.append(current)
                            current = line
                        else:
                            current = (current + " " + line).strip() if current else line
                    if current:
                        merged.append(current)
                    if not merged:
                        merged = raw_lines
                    metar_line = ""
                    for line in merged:
                        if station.upper() in line.upper():
                            metar_line = line
                            break
                    if not metar_line:
                        metar_line = merged[0] if merged else ""
                    if not metar_line:
                        return None

                    result = self._parse_metar_temp(metar_line)
                    if result is None:
                        return None

                    temp_f, temp_c = result
                    time_str = self._parse_metar_time(metar_line)

                    return {
                        "temp_f": temp_f,
                        "temp_c": temp_c,
                        "time": time_str,
                        "raw": metar_line,
                        "metar_time": time_str,
                    }
        except Exception as e:
            logger.error(f"Error fetching METAR for {station}: {e}")
            return None

    async def check_updates(self) -> List[Tuple]:
        """
        Перевіряє METAR оновлення.
        Повертає (chat_id, code, data, event_type)
        event_type: "new" = нові дані, "correction" = виправлення
        """
        if not self.stations:
            return []

        notifications = []

        # Унікальні станції
        unique = {}
        for chat_id, station_list in self.stations.items():
            for s in station_list:
                code = s["code"]
                if code not in unique:
                    unique[code] = []
                unique[code].append((chat_id, s))

        for code, subscribers in unique.items():
            data = await self.fetch_metar(code)
            if not data:
                await asyncio.sleep(0.3)
                continue

            new_time = data["metar_time"]
            new_temp_c = data["temp_c"]
            new_temp_f = data["temp_f"]

            for chat_id, station_data in subscribers:
                last_time = station_data.get("last_metar_time")
                last_temp_c = station_data.get("last_temp_c")

                if last_time is None:
                    # Перший запуск — просто зберігаємо
                    station_data["last_metar_time"] = new_time
                    station_data["last_temp_c"] = new_temp_c
                    station_data["last_temp_f"] = new_temp_f
                    continue

                if new_time != last_time:
                    # Новий METAR (час змінився)
                    notifications.append((chat_id, code, data, "new"))
                    station_data["last_metar_time"] = new_time
                    station_data["last_temp_c"] = new_temp_c
                    station_data["last_temp_f"] = new_temp_f

                elif new_time == last_time and last_temp_c is not None:
                    # Той самий час — перевіряємо чи змінилась температура
                    if abs(new_temp_c - last_temp_c) >= 0.5:
                        # ВИПРАВЛЕННЯ! Той самий час але інша температура
                        correction_data = {
                            **data,
                            "old_temp_c": last_temp_c,
                            "old_temp_f": station_data.get("last_temp_f", last_temp_c * 9/5 + 32),
                        }
                        notifications.append((chat_id, code, correction_data, "correction"))
                        station_data["last_temp_c"] = new_temp_c
                        station_data["last_temp_f"] = new_temp_f
                        logger.info(f"METAR correction detected for {code}: {last_temp_c}°C -> {new_temp_c}°C at {new_time}")

            await asyncio.sleep(0.3)

        self._save()
        return notifications

