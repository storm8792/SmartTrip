# -*- coding: utf-8 -*-
"""天气模块：和风天气 API 优先，未配置 Key 时使用可复现的演示数据。

输出字段（前端与建议生成共用）：
    provider/city/temp/feelsLike/text/rainNow/rainSoon/summary/updatedAt/note
    humidity/windDir/windScale/uvIndex/pop
    hourly: [{time, temp, text, pop}]
"""
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

NOW_API = "https://devapi.qweather.com/v7/weather/now"
MINUTELY_API = "https://devapi.qweather.com/v7/minutely/5m"
HOURLY_API = "https://devapi.qweather.com/v7/weather/24h"

WEATHER_TEXTS = ["晴", "多云", "阴", "小雨", "阵雨", "雷阵雨"]


def _seed(text):
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def mock_weather(city, now=None, reason=""):
    """按「城市+日期+小时」生成稳定的演示数据，避免每次请求都跳变。"""
    now = now or datetime.now()
    city_key = city or "未知"
    day_key = now.strftime("%Y-%m-%d")
    seed = _seed("%s|%s|%d" % (city_key, day_key, now.hour))
    text = WEATHER_TEXTS[seed % len(WEATHER_TEXTS)]
    temp = 18 + seed % 12
    feels = temp + (seed // 7) % 4 - 2
    rainy = text in ("小雨", "阵雨", "雷阵雨")
    humidity = 45 + seed % 46
    wind_scale = 1 + (seed // 5) % 5
    uv = 0 if (now.hour < 7 or now.hour > 18) else (seed // 3) % 11
    pop = 85 if rainy else 5 + (seed // 11) % 40

    hourly = []
    for i in range(12):
        hs = _seed("%s|%s|%d" % (city_key, day_key, now.hour + i))
        hourly.append({
            "time": (now + timedelta(hours=i)).strftime("%H:00"),
            "temp": 17 + hs % 13,
            "text": text,
            "pop": pop if i < 2 else 5 + (hs // 11) % 45,
        })

    note = "演示数据（未配置和风天气 API Key）"
    if reason:
        note += "；真实接口调用失败：" + reason
    return {
        "provider": "mock",
        "city": city or "未知",
        "temp": temp,
        "feelsLike": feels,
        "text": text,
        "rainNow": rainy,
        "rainSoon": rainy or pop >= 50,
        "summary": ("当前有降水" if rainy else "未来两小时无明显降水"),
        "humidity": humidity,
        "windDir": "东南风",
        "windScale": wind_scale,
        "uvIndex": uv,
        "pop": pop,
        "hourly": hourly,
        "updatedAt": now.strftime("%H:%M:%S"),
        "note": note,
    }


def _get_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "SmartTrip/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def qweather(api_key, location, city, now=None):
    """调用和风天气实时天气 + 分钟级降水 + 24 小时预报。失败时回退演示数据。"""
    now = now or datetime.now()
    q = urllib.parse.urlencode({"location": location, "key": api_key})
    try:
        realtime = _get_json("%s?%s" % (NOW_API, q))
        if str(realtime.get("code")) != "200" or "now" not in realtime:
            return mock_weather(city, now, "返回码 %s" % realtime.get("code"))

        cur = realtime["now"]
        feels = _int(cur.get("feelsLike"), _int(cur.get("temp")))
        temp = _int(cur.get("temp"), feels)
        text = cur.get("text", "")

        rain_soon = False
        summary = "未来两小时无明显降水"
        try:
            minute = _get_json("%s?%s" % (MINUTELY_API, q))
            if str(minute.get("code")) == "200":
                summary = minute.get("summary", summary) or summary
                for item in minute.get("minutely", []) or []:
                    if _int(item.get("precip")) > 0:
                        rain_soon = True
                        break
        except Exception:
            pass

        hourly = []
        try:
            h24 = _get_json("%s?%s" % (HOURLY_API, q))
            if str(h24.get("code")) == "200":
                for it in (h24.get("hourly") or [])[:12]:
                    fx = str(it.get("fxTime") or "")
                    hourly.append({
                        "time": fx[11:16] if len(fx) >= 16 else fx,
                        "temp": _int(it.get("temp")),
                        "text": it.get("text", ""),
                        "pop": _int(it.get("pop")),
                    })
        except Exception:
            pass

        pop = _int(hourly[0]["pop"]) if hourly else (80 if rain_soon else 0)
        if hourly:
            hourly[0]["pop"] = pop

        return {
            "provider": "qweather",
            "city": city,
            "temp": temp,
            "feelsLike": feels,
            "text": text,
            "rainNow": ("雨" in text) or ("雪" in text),
            "rainSoon": rain_soon or pop >= 50,
            "summary": summary,
            "humidity": _int(cur.get("humidity")),
            "windDir": cur.get("windDir", ""),
            "windScale": _int(cur.get("windScale")),
            "uvIndex": _int(cur.get("uvIndex")),
            "pop": pop,
            "hourly": hourly,
            "updatedAt": now.strftime("%H:%M:%S"),
            "note": "数据来源：和风天气",
        }
    except Exception as exc:
        return mock_weather(city, now, str(exc)[:60])


def get_weather(settings, now=None):
    provider = (settings.get("provider") or "mock").lower()
    key = (settings.get("apiKey") or "").strip()
    location = (settings.get("location") or "").strip()
    city = settings.get("city") or ""
    if provider == "qweather" and key and location:
        return qweather(key, location, city, now)
    return mock_weather(city, now)
