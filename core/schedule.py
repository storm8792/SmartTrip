# -*- coding: utf-8 -*-
"""课程表模块：课程模型（教师/教室/星期/周次/颜色）、下次上课时间计算、课前定时调度。"""
import re
import threading
import uuid
from datetime import datetime, timedelta

COLORS = ("blue", "green", "violet", "amber", "rose", "cyan")
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

COURSE_DEFAULTS = {
    "teacher": "",
    "room": "",
    "weekday": None,   # 0=周一 … 6=周日；None=每天
    "weeks": "",       # "1-16"，空=不限周次
    "color": "blue",
    "note": "",
}


def validate_time(hhmm):
    """校验 HH:MM 格式，返回规范化字符串或 None。"""
    try:
        h, m = [int(x) for x in str(hhmm).strip().split(":")]
    except Exception:
        return None
    if 0 <= h <= 23 and 0 <= m <= 59:
        return "%02d:%02d" % (h, m)
    return None


def parse_weeks(text):
    """'1-16' / '1-8,10-16' → {1..16}；空或无法解析 → None（表示不限周次）。"""
    text = (text or "").strip()
    if not text:
        return None
    weeks = set()
    for part in re.split(r"[,，;；\s]+", text):
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-~]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            weeks.update(range(max(1, a), min(52, b) + 1))
        elif part.isdigit():
            weeks.add(int(part))
    return weeks or None


def normalize_weeks(text):
    text = (text or "").strip()
    return text if parse_weeks(text) else ""


def _term_date(term_start):
    try:
        return datetime.strptime(str(term_start).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def week_of(day, term_start):
    """某一天属于学期第几周；无法确定时按第 1 周处理。"""
    start = _term_date(term_start)
    if not start:
        return 1
    return max(1, min(52, (day - start).days // 7 + 1))


def current_week(term_start, now=None):
    now = now or datetime.now()
    return week_of(now.date(), term_start)


def normalize_course(raw):
    """为旧数据补齐字段，保证前端拿到完整模型。"""
    if not isinstance(raw, dict):
        return None
    c = dict(raw)
    c["name"] = (str(c.get("name") or "")).strip()[:30] or "未命名"
    c["time"] = validate_time(c.get("time")) or "09:00"
    c["enabled"] = bool(c.get("enabled", True))
    c["teacher"] = (str(c.get("teacher") or "")).strip()[:20]
    c["room"] = (str(c.get("room") or "")).strip()[:20]
    c["note"] = (str(c.get("note") or "")).strip()[:80]
    c["weeks"] = normalize_weeks(c.get("weeks"))
    c["color"] = c.get("color") if c.get("color") in COLORS else "blue"
    wd = c.get("weekday")
    if wd in ("", None):
        c["weekday"] = None
    else:
        try:
            wd = int(wd)
            c["weekday"] = wd if 0 <= wd <= 6 else None
        except (TypeError, ValueError):
            c["weekday"] = None
    if not c.get("id"):
        c["id"] = "c_" + uuid.uuid4().hex[:10]
    return c


def apply_course_fields(course, patch):
    """把请求中的可编辑字段合并进课程对象。"""
    patch = patch or {}
    if "name" in patch:
        name = (patch.get("name") or "").strip()
        if name:
            course["name"] = name[:30]
    if "time" in patch:
        t = validate_time(patch.get("time"))
        if t:
            course["time"] = t
    if "enabled" in patch:
        course["enabled"] = bool(patch.get("enabled"))
    if "teacher" in patch:
        course["teacher"] = (patch.get("teacher") or "").strip()[:20]
    if "room" in patch:
        course["room"] = (patch.get("room") or "").strip()[:20]
    if "weekday" in patch:
        wd = patch.get("weekday")
        if wd in ("", None):
            course["weekday"] = None
        else:
            try:
                wd = int(wd)
                course["weekday"] = wd if 0 <= wd <= 6 else None
            except (TypeError, ValueError):
                course["weekday"] = None
    if "weeks" in patch:
        course["weeks"] = normalize_weeks(patch.get("weeks"))
    if "color" in patch:
        course["color"] = patch.get("color") if patch.get("color") in COLORS else "blue"
    if "note" in patch:
        course["note"] = (patch.get("note") or "").strip()[:80]
    return course


def new_course(name, hhmm, extra=None):
    t = validate_time(hhmm)
    name = (name or "").strip()
    if not t or not name:
        return None
    base = {
        "id": "c_" + uuid.uuid4().hex[:10],
        "name": name[:30],
        "time": t,
        "enabled": True,
        "teacher": "",
        "room": "",
        "weekday": None,
        "weeks": "",
        "color": "blue",
        "note": "",
    }
    return apply_course_fields(base, extra)


def _sort_key(c):
    wd = c.get("weekday")
    return (99 if wd is None else wd, c.get("time", "99:99"))


def sorted_courses(courses):
    """先「每天」，再周一→周日，同一天按上课时间升序。"""
    items = [normalize_course(c) for c in (courses or [])]
    return sorted([c for c in items if c], key=_sort_key)


def next_occurrence(hhmm, now=None, weekday=None, weeks=None, term_start=None):
    """计算下一次上课时间，考虑星期与周次约束；最多向后找 60 天。"""
    now = now or datetime.now()
    t = validate_time(hhmm)
    if not t:
        return None
    h, m = [int(x) for x in t.split(":")]
    week_set = parse_weeks(weeks) if isinstance(weeks, str) else weeks

    for offset in range(0, 61):
        day = (now + timedelta(days=offset)).date()
        if weekday is not None and day.weekday() != weekday:
            continue
        if week_set is not None and term_start and week_of(day, term_start) not in week_set:
            continue
        cand = datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)
        if cand > now:
            return cand
    return None


def annotate(courses, advance_minutes, term_start=None, now=None):
    """为每门课补充下次上课时间与提醒时间（毫秒时间戳），供前端倒计时。"""
    now = now or datetime.now()
    out = []
    for c in sorted_courses(courses):
        occ = next_occurrence(c.get("time", ""), now, c.get("weekday"),
                              c.get("weeks"), term_start)
        item = dict(c)
        if occ and c.get("enabled", True):
            fire = occ - timedelta(minutes=advance_minutes)
            item["nextAt"] = int(occ.timestamp() * 1000)
            item["fireAt"] = int(fire.timestamp() * 1000)
            item["nextText"] = occ.strftime("%m-%d %H:%M")
            item["nextWeekday"] = WEEKDAY_NAMES[occ.weekday()]
        else:
            item["nextAt"] = None
            item["fireAt"] = None
            item["nextText"] = "--"
            item["nextWeekday"] = ""
        out.append(item)
    return out


class Scheduler(threading.Thread):
    """每秒轮询一次，到达提醒时刻则回调。同一课程-日期只触发一次。"""

    def __init__(self, get_settings, get_courses, on_fire, store):
        super().__init__(daemon=True)
        self.get_settings = get_settings
        self.get_courses = get_courses
        self.on_fire = on_fire
        self.store = store
        self._stop = threading.Event()
        self._fired = store.load_fired()

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:  # 调度器不能因单次异常退出
                print("[调度器] 异常:", exc)
            self._stop.wait(1.0)

    def _tick(self):
        settings = self.get_settings()
        advance = int(settings.get("advanceMinutes", 10) or 10)
        term_start = settings.get("termStart")
        now = datetime.now()
        changed = False

        for c in self.get_courses():
            if not c.get("enabled", True):
                continue
            occ = next_occurrence(c.get("time", ""), now, c.get("weekday"),
                                  c.get("weeks"), term_start)
            if not occ:
                continue
            fire_at = occ - timedelta(minutes=advance)
            # 只在「已到提醒时刻、且还没上课」的时间窗内触发
            if not (fire_at <= now < occ):
                continue
            key = "%s|%s|%s" % (c.get("id"), occ.strftime("%Y-%m-%d"), c.get("time"))
            if key in self._fired:
                continue
            self._fired.add(key)
            changed = True
            remaining = int((occ - now).total_seconds() // 60)
            self.on_fire({
                "course": dict(c),
                "courseName": c.get("name", ""),
                "courseId": c.get("id"),
                "time": c.get("time"),
                "remaining": remaining,
                "occurrence": occ.strftime("%Y-%m-%d %H:%M"),
            })

        if changed:
            self.store.save_fired(self._fired)
