# -*- coding: utf-8 -*-
"""SmartTrip · 基于语音合成技术的行程播报系统

纯 Python 标准库实现，无需安装任何第三方依赖：
    python app.py

启动后浏览器自动打开 http://127.0.0.1:8770
"""
import argparse
import json
import mimetypes
import os
import queue
import socket
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from core import advice as advice_mod
from core import schedule as sched_mod
from core import store as store_mod
from core import tts_openvoice
from core import weather as weather_mod

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")

store = store_mod.Store(DATA_DIR)
courses = store.load_courses()
settings = store.load_settings()

_weather_cache = {"at": 0.0, "key": "", "data": None}
_weather_lock = threading.Lock()
_last_advice = {"text": "", "course": "", "at": 0}
_state_lock = threading.Lock()


# ---------------- 事件总线（SSE 推送） ----------------
class EventBus:
    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


bus = EventBus()


# ---------------- 业务辅助 ----------------
def current_settings():
    with _state_lock:
        return dict(settings)


def current_courses():
    with _state_lock:
        return [dict(c) for c in courses]


def get_weather(force=False):
    s = current_settings()
    key = "|".join([s.get("provider", ""), s.get("city", ""), s.get("apiKey", ""), s.get("location", "")])
    now_ts = time.time()
    with _weather_lock:
        if not force and _weather_cache["data"] and _weather_cache["key"] == key \
                and now_ts - _weather_cache["at"] < 300:
            return _weather_cache["data"]
        data = weather_mod.get_weather(s)
        _weather_cache.update({"at": now_ts, "key": key, "data": data})
        return data


def build_advice_for(course_name, remaining=None, course=None):
    if remaining is None:
        settings_now = current_settings()
        advance = int(settings_now.get("advanceMinutes", 10) or 10)
        remaining = advance
    return advice_mod.build_advice(course_name, remaining, get_weather(), course=course)


def state_payload():
    s = current_settings()
    advance = int(s.get("advanceMinutes", 10) or 10)
    term_start = s.get("termStart")
    with _state_lock:
        cs = sched_mod.annotate(courses, advance, term_start)
        last = dict(_last_advice)
    return {
        "now": int(time.time() * 1000),
        "settings": s,
        "courses": cs,
        "weather": get_weather(),
        "lastAdvice": last,
        "tts": tts_openvoice.status(),
        "currentWeek": sched_mod.current_week(term_start),
    }


def on_fire(event):
    """调度器触发回调：生成建议、记录历史、推送前端。"""
    try:
        course = event.get("course") or {}
        remaining = event.get("remaining", 0)
        weather = get_weather()
        text = advice_mod.build_advice(
            event.get("courseName") or course.get("name", ""), remaining, weather, course=course)
        payload = {
            "type": "reminder",
            "course": course.get("name", ""),
            "courseId": event.get("courseId"),
            "room": course.get("room", ""),
            "teacher": course.get("teacher", ""),
            "color": course.get("color", "blue"),
            "time": event.get("time"),
            "remaining": remaining,
            "occurrence": event.get("occurrence"),
            "text": text,
            "weather": weather,
            "at": int(time.time() * 1000),
        }
        with _state_lock:
            _last_advice.update({
                "text": text,
                "course": course.get("name", ""),
                "at": payload["at"],
            })
        store.append_history({
            "at": payload["at"],
            "course": course.get("name", ""),
            "time": event.get("time"),
            "remaining": remaining,
            "room": course.get("room", ""),
            "color": course.get("color", "blue"),
            "text": text,
            "weatherText": weather.get("text", ""),
            "feelsLike": weather.get("feelsLike"),
        })
        bus.publish(payload)
        print("[播报] %s 课前提醒已触发：%s" % (course.get("name"), event.get("time")))
    except Exception:
        traceback.print_exc()


scheduler = sched_mod.Scheduler(current_settings, current_courses, on_fire, store)
scheduler.start()


# ---------------- HTTP 处理 ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SmartTrip/1.0"

    def handle_one_request(self):
        # 浏览器刷新/关闭 SSE 时会主动断连，属正常现象，不打印堆栈
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True

    def log_message(self, fmt, *args):
        if "/api/events" in (args[0] if args else ""):
            return
        sys.stderr.write("[HTTP] %s\n" % (fmt % args))

    # ---- 响应工具 ----
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _error(self, code, message):
        self._json({"ok": False, "error": message}, code)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            raw = self.rfile.read(n).decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}

    # ---- 路由 ----
    def do_GET(self):
        parts = urlsplit(self.path)
        path, query = unquote(parts.path), parts.query
        try:
            if path in ("/", "/index.html"):
                return self._serve_file(os.path.join(STATIC_DIR, "index.html"))
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                full = os.path.normpath(os.path.join(STATIC_DIR, rel))
                if not full.startswith(STATIC_DIR):
                    return self._error(403, "禁止访问")
                return self._serve_file(full)
            if path == "/api/state":
                return self._json(state_payload())
            if path == "/api/weather":
                force = "refresh=1" in query
                return self._json({"ok": True, "weather": get_weather(force)})
            if path == "/api/history":
                return self._json({"ok": True, "history": list(reversed(store.load_history()))[:80]})
            if path == "/api/courses/export":
                return self._export_courses()
            if path == "/api/events":
                return self._sse()
            if path == "/api/tts/status":
                return self._json(tts_openvoice.status())
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            return self._error(404, "未找到：%s" % path)
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            try:
                self._error(500, "服务器内部错误")
            except Exception:
                pass

    def _serve_file(self, full):
        if not os.path.isfile(full):
            return self._error(404, "文件不存在")
        ctype, _ = mimetypes.guess_type(full)
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = bus.subscribe()
        try:
            self.wfile.write(b"data: {\"type\":\"hello\"}\n\n")
            self.wfile.flush()
            while True:
                try:
                    evt = q.get(timeout=15)
                    chunk = "data: %s\n\n" % json.dumps(evt, ensure_ascii=False)
                except queue.Empty:
                    chunk = ": ping\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            bus.unsubscribe(q)

    # ---- 写操作 ----
    def do_POST(self):
        path = unquote(urlsplit(self.path).path)
        body = self._body()
        try:
            if path == "/api/courses":
                return self._add_course(body)
            if path == "/api/courses/import":
                return self._import_courses(body)
            if path == "/api/advice/preview":
                return self._preview(body)
            if path == "/api/settings":
                return self._save_settings(body)
            if path == "/api/tts":
                return self._tts(body)
            if path == "/api/weather/refresh":
                return self._json({"ok": True, "weather": get_weather(True)})
            return self._error(404, "未找到：%s" % path)
        except Exception:
            traceback.print_exc()
            return self._error(500, "服务器内部错误")

    def do_PUT(self):
        path = unquote(urlsplit(self.path).path)
        body = self._body()
        if path.startswith("/api/courses/"):
            return self._update_course(path.rsplit("/", 1)[-1], body)
        return self._error(404, "未找到：%s" % path)

    def do_DELETE(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/api/history":
            with _state_lock:
                store.clear_history()
            return self._json({"ok": True})
        if path.startswith("/api/courses/"):
            return self._delete_course(path.rsplit("/", 1)[-1])
        return self._error(404, "未找到：%s" % path)

    def _export_courses(self):
        data = {"courses": current_courses(), "exportedAt": int(time.time() * 1000)}
        self._send(200, json.dumps(data, ensure_ascii=False, indent=2),
                  "application/json; charset=utf-8", {
                      "Content-Disposition": "attachment; filename=courses.json"
                  })

    def _import_courses(self, body):
        imported = body.get("courses")
        if not isinstance(imported, list) or len(imported) == 0:
            return self._error(400, "课程列表格式不正确")
        with _state_lock:
            new_courses = []
            for raw in imported:
                c = sched_mod.normalize_course(raw)
                if c:
                    new_courses.append(c)
            if not new_courses:
                return self._error(400, "导入列表中没有有效课程")
            # 合并去重：同名同时间同星期不重复添加
            existing = list(courses)
            for nc in new_courses:
                dup = any(
                    (c.get("name") == nc["name"] and
                     c.get("time") == nc["time"] and
                     c.get("weekday") == nc.get("weekday"))
                    for c in existing
                )
                if not dup:
                    existing.append(nc)
            courses[:] = existing
            store.save_courses(courses)
        return self._json({
            "ok": True,
            "added": len(new_courses),
            "total": len(courses),
            "courses": sched_mod.annotate(
                courses, int(current_settings().get("advanceMinutes", 10)),
                current_settings().get("termStart")
            )
        })

    def do_DELETE(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/api/history":
            with _state_lock:
                store.clear_history()
            return self._json({"ok": True})
        if path.startswith("/api/courses/"):
            return self._delete_course(path.rsplit("/", 1)[-1])
        return self._error(404, "未找到：%s" % path)

    # ---- 业务实现 ----
    def _add_course(self, body):
        course = sched_mod.new_course(body.get("name"), body.get("time"), body)
        if not course:
            return self._error(400, "课程名不能为空，时间格式应为 HH:MM")
        with _state_lock:
            for c in courses:
                if (c.get("time") == course["time"] and c.get("name") == course["name"]
                        and c.get("weekday") == course.get("weekday")):
                    return self._error(409, "该课程已存在")
            courses.append(course)
            data = list(courses)
        store.save_courses(data)
        s = current_settings()
        return self._json({"ok": True, "course": course, "courses": sched_mod.annotate(
            data, int(s.get("advanceMinutes", 10)), s.get("termStart"))})

    def _update_course(self, cid, body):
        with _state_lock:
            target = next((c for c in courses if c.get("id") == cid), None)
            if not target:
                return self._error(404, "课程不存在")
            if "name" in body and not (body.get("name") or "").strip():
                return self._error(400, "课程名不能为空")
            if "time" in body and not sched_mod.validate_time(body.get("time")):
                return self._error(400, "时间格式应为 HH:MM")
            sched_mod.apply_course_fields(target, body)
            data = list(courses)
        store.save_courses(data)
        return self._json({"ok": True, "course": target})

    def _delete_course(self, cid):
        with _state_lock:
            before = len(courses)
            courses[:] = [c for c in courses if c.get("id") != cid]
            if len(courses) == before:
                return self._error(404, "课程不存在")
            data = list(courses)
        store.save_courses(data)
        return self._json({"ok": True})

    def _save_settings(self, body):
        global settings
        allowed = {"advanceMinutes", "autoSpeak", "voiceRate", "voiceName",
                   "city", "location", "apiKey", "provider", "termStart"}
        patch = {k: v for k, v in (body or {}).items() if k in allowed}
        if "advanceMinutes" in patch:
            try:
                patch["advanceMinutes"] = max(0, min(120, int(patch["advanceMinutes"])))
            except Exception:
                patch["advanceMinutes"] = 10
        if "voiceRate" in patch:
            try:
                patch["voiceRate"] = max(0.5, min(2.0, float(patch["voiceRate"])))
            except Exception:
                patch["voiceRate"] = 1.0
        with _state_lock:
            merged = dict(settings)
            merged.update(patch)
            settings = merged
        store.save_settings(settings)
        return self._json({"ok": True, "settings": settings})

    def _preview(self, body):
        cid = body.get("courseId")
        name = (body.get("course") or "").strip()
        course = None
        if cid:
            c = next((x for x in current_courses() if x.get("id") == cid), None)
            if c:
                course = c
                name = c.get("name", "")
        if not name:
            cs = current_courses()
            course = cs[0] if cs else None
            name = course.get("name") if course else "自习"
        s = current_settings()
        advance = int(s.get("advanceMinutes", 10) or 10)
        text = build_advice_for(name, advance, course)
        with _state_lock:
            _last_advice.update({"text": text, "course": name, "at": int(time.time() * 1000)})
        return self._json({"ok": True, "text": text, "course": name, "weather": get_weather()})

    def _tts(self, body):
        st = tts_openvoice.status()
        if not st["available"]:
            return self._json({
                "ok": False,
                "fallback": "browser",
                "message": "OpenVoice 未就绪，已使用浏览器内置语音播报",
                "missing": st["missing"],
            }, 200)
        text = (body.get("text") or "").strip()
        if not text:
            return self._error(400, "文本不能为空")
        path = tts_openvoice.synthesize(text)
        with open(path, "rb") as f:
            data = f.read()
        return self._send(200, data, "audio/wav")


def find_port(start=8770, tries=20):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def main():
    ap = argparse.ArgumentParser(description="SmartTrip 行程播报系统")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    port = find_port(args.port) if args.port == 8770 else args.port
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    url = "http://127.0.0.1:%d" % port

    print("=" * 52)
    print("  SmartTrip · 基于语音合成技术的行程播报系统")
    print("  服务地址：%s" % url)
    print("  局域网访问：http://<本机IP>:%d" % port)
    print("  课程数：%d    提前提醒：%s 分钟" % (
        len(courses), settings.get("advanceMinutes", 10)))
    print("  按 Ctrl+C 停止服务")
    print("=" * 52)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭……")
    finally:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()
