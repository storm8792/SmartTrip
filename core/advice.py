# -*- coding: utf-8 -*-
"""出行建议生成：时间 + 课程（教室/教师） + 天气（温度/降水/紫外线/风力） → 播报文本。"""
from datetime import datetime


def _cn_time(dt):
    return "%d点%d分" % (dt.hour, dt.minute)


def _temp_tip(f):
    if f <= 10:
        return "体感偏冷，请注意保暖，建议加穿外套。"
    if f <= 18:
        return "体感微凉，建议穿薄外套。"
    if f <= 26:
        return "气温舒适，适合出行。"
    if f <= 32:
        return "体感偏热，注意补水防晒。"
    return "天气炎热，请避免长时间户外停留。"


def build_advice(course_name, remaining, weather, now=None, course=None):
    """按「时间 → 课程 → 地点 → 体感温度 → 降水 → 紫外线 → 风力」顺序拼装。"""
    now = now or datetime.now()
    course = course or {}
    remaining = max(0, int(remaining))

    if remaining <= 0:
        head = "现在是%s，%s马上开始。" % (_cn_time(now), course_name)
    else:
        head = "当前时间为%s，%d分钟之后有%s课。" % (_cn_time(now), remaining, course_name)

    parts = [head]

    room = str(course.get("room") or "").strip()
    teacher = str(course.get("teacher") or "").strip()
    if room and teacher:
        parts.append("上课地点%s，任课教师%s。" % (room, teacher))
    elif room:
        parts.append("上课地点%s。" % room)
    elif teacher:
        parts.append("任课教师%s。" % teacher)

    feels = weather.get("feelsLike")
    text = weather.get("text") or ""
    pop = weather.get("pop")

    if feels is not None:
        f = int(feels)
        parts.append("当前体感温度为%d摄氏度，%s" % (f, _temp_tip(f)))

    if text:
        parts.append("当前天气为%s。" % text)

    if weather.get("rainNow"):
        parts.append("当前正在降水，出门请带伞。")
    elif weather.get("rainSoon") or (pop is not None and int(pop) >= 50):
        parts.append("未来两小时内有降水可能，请携带雨具。")

    uv = weather.get("uvIndex")
    if uv is not None and int(uv) >= 6 and 8 <= now.hour <= 17:
        parts.append("紫外线较强，建议做好防晒。")

    wind = weather.get("windScale")
    if wind is not None and int(wind) >= 5:
        parts.append("风力较大，注意出行安全。")

    parts.append("祝你上课顺利。")
    return "".join(parts)
