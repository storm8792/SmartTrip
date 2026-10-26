# -*- coding: utf-8 -*-
"""数据持久化：课程表、设置、已触发记录。"""
import json
import os
import tempfile
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DEFAULT_SETTINGS = {
    "advanceMinutes": 10,      # 课前提前提醒分钟数
    "autoSpeak": True,         # 收到提醒后自动语音播报
    "voiceRate": 1.0,          # 语速
    "voiceName": "",           # 指定浏览器音色，空=自动
    "city": "广州",
    "location": "113.2644,23.1291",
    "apiKey": "",
    "provider": "mock",        # mock=演示数据，qweather=和风天气
    "termStart": "2026-09-01", # 学期开始日期，用于计算当前是第几周
}


class Store:
    """线程安全的 JSON 文件存储。"""

    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._courses_path = os.path.join(self.data_dir, "courses.json")
        self._settings_path = os.path.join(self.data_dir, "settings.json")
        self._fired_path = os.path.join(self.data_dir, "fired.json")
        self._history_path = os.path.join(self.data_dir, "history.json")

    # ---------- 通用读写 ----------
    def _read(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write(self, path, data):
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
        os.close(fd)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ---------- 课程 ----------
    def load_courses(self):
        with self._lock:
            data = self._read(self._courses_path, [])
            return data if isinstance(data, list) else []

    def save_courses(self, courses):
        with self._lock:
            self._write(self._courses_path, courses)

    # ---------- 设置 ----------
    def load_settings(self):
        with self._lock:
            data = self._read(self._settings_path, {})
            merged = dict(DEFAULT_SETTINGS)
            if isinstance(data, dict):
                merged.update(data)
            return merged

    def save_settings(self, settings):
        with self._lock:
            merged = dict(DEFAULT_SETTINGS)
            if isinstance(settings, dict):
                merged.update(settings)
            self._write(self._settings_path, merged)
            return merged

    # ---------- 已触发记录 ----------
    def load_fired(self):
        with self._lock:
            data = self._read(self._fired_path, [])
            return set(data) if isinstance(data, list) else set()

    def save_fired(self, keys):
        with self._lock:
            # 只保留最近 500 条，避免文件无限增长
            self._write(self._fired_path, sorted(keys)[-500:])

    # ---------- 播报历史 ----------
    def load_history(self):
        with self._lock:
            data = self._read(self._history_path, [])
            return data if isinstance(data, list) else []

    def append_history(self, record, limit=100):
        with self._lock:
            items = self.load_history()
            items.append(record)
            self._write(self._history_path, items[-limit:])

    def clear_history(self):
        with self._lock:
            self._write(self._history_path, [])
