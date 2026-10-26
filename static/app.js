/* SmartTrip · 前端逻辑 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const WEEK_CHARS = "一二三四五六日";
  const COLOR_HEX = {
    blue: "#2f6bff", green: "#10b981", violet: "#8b5cf6",
    amber: "#f59e0b", rose: "#f43f5e", cyan: "#06b6d4"
  };
  const ICONS = { "晴": "☀️", "多云": "⛅", "阴": "☁️", "小雨": "🌦️", "阵雨": "🌦️", "雷阵雨": "⛈️" };

  const state = {
    settings: { advanceMinutes: 10, autoSpeak: true, voiceRate: 1, voiceName: "" },
    courses: [],
    weather: null,
    history: [],
    currentWeek: 1,
    view: "list",
    recTab: "history",
    editingId: null,
    formColor: "blue",
    speaking: false,
    lastText: ""
  };
  let voices = [];
  let primed = false;

  /* ---------------- 工具 ---------------- */
  const pad = (n) => String(n).padStart(2, "0");

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[m]));
  }

  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " " + kind : "");
    el.textContent = msg;
    $("toastWrap").appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = ".3s";
      setTimeout(() => el.remove(), 320);
    }, 2600);
  }

  function addLog(text, hi) {
    const li = document.createElement("li");
    if (hi) li.className = "hi";
    const t = new Date();
    li.innerHTML = `<span class="t">${pad(t.getHours())}:${pad(t.getMinutes())}</span>`;
    li.append(document.createTextNode(text));
    const ul = $("logList");
    ul.prepend(li);
    while (ul.children.length > 40) ul.lastChild.remove();
  }

  async function api(path, method, body) {
    const opt = { method: method || "GET", headers: {} };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    const res = await fetch(path, opt);
    const ct = res.headers.get("Content-Type") || "";
    if (ct.includes("application/json")) {
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "请求失败");
      return data;
    }
    if (!res.ok) throw new Error("请求失败（" + res.status + "）");
    return res;
  }

  const todayIndex = () => (new Date().getDay() + 6) % 7; // 0=周一
  const wdLabel = (wd) => (wd === null || wd === undefined) ? "每天" : "周" + WEEK_CHARS[wd];

  function fmtDateTime(date) {
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  /* ---------------- 语音 ---------------- */
  function loadVoices() {
    voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  }
  if ("speechSynthesis" in window) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }

  function primeSpeech() {
    if (primed || !("speechSynthesis" in window)) return;
    primed = true;
    const u = new SpeechSynthesisUtterance("");
    u.volume = 0;
    speechSynthesis.speak(u);
  }
  document.addEventListener("click", primeSpeech, { once: true });

  function setWave(active) {
    $("wave").classList.toggle("active", active);
  }

  function speak(text) {
    if (!text) return;
    if (!("speechSynthesis" in window)) {
      toast("当前浏览器不支持语音播报", "err");
      addLog("语音播报不可用：浏览器不支持 Web Speech API");
      return;
    }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-CN";
    u.rate = Math.min(2, Math.max(0.5, Number(state.settings.voiceRate) || 1));
    const zh = voices.find((v) => v.name === state.settings.voiceName)
      || voices.find((v) => /zh[-_]?CN|Chinese|中文|普通话/i.test(v.lang + v.name))
      || voices.find((v) => /^zh/i.test(v.lang));
    if (zh) u.voice = zh;

    u.onstart = () => {
      state.speaking = true;
      $("btnSpeak").classList.add("playing");
      $("speakLabel").textContent = "正在播报";
      $("adviceText").classList.add("speaking");
      setWave(true);
      addLog("开始语音播报" + (zh ? "（音色：" + zh.name + "）" : ""));
    };
    u.onend = u.onerror = () => {
      state.speaking = false;
      $("btnSpeak").classList.remove("playing");
      $("speakLabel").textContent = "播放播报";
      $("adviceText").classList.remove("speaking");
      setWave(false);
    };
    speechSynthesis.speak(u);
  }

  /* ---------------- 天气 ---------------- */
  function renderWeather(w) {
    if (!w) return;
    $("wIcon").textContent = ICONS[w.text] || "☁️";
    $("wTemp").textContent = (w.feelsLike != null ? w.feelsLike : "--") + "°";
    $("wText").textContent = (w.text || "") + " · 体感";
    const dot = $("wDot");
    dot.classList.toggle("real", w.provider === "qweather");
    dot.title = w.note || "";
  }

  function renderHourly(w) {
    const box = $("hourly");
    box.innerHTML = "";
    const list = (w && w.hourly) || [];
    if (!list.length) {
      box.innerHTML = '<span class="hourly-empty">暂无逐时数据</span>';
      return;
    }
    list.forEach((h, i) => {
      const el = document.createElement("div");
      el.className = "hitem";
      el.innerHTML = `<div class="h-time">${i === 0 ? "现在" : escapeHtml(h.time)}</div>
        <div class="h-icon">${ICONS[h.text] || "☁️"}</div>
        <div class="h-temp">${h.temp}°</div>
        <div class="h-pop">💧${h.pop}%</div>`;
      box.appendChild(el);
    });
  }

  /* ---------------- 课程渲染 ---------------- */
  function fmtCountdown(ms) {
    if (ms <= 0) return "00:00";
    const total = Math.floor(ms / 1000);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${h}:${pad(m)}:${pad(s)}`;
    return `${pad(m)}:${pad(s)}`;
  }

  function renderStat() {
    const list = state.courses || [];
    const ti = todayIndex();
    const todayCount = list.filter((c) => c.weekday === null || c.weekday === undefined || c.weekday === ti).length;
    $("courseStat").textContent = `第 ${state.currentWeek || 1} 周 · 今日 ${todayCount} 节 · 共 ${list.length} 门`;
  }

  function sortedByTime(arr) {
    return arr.slice().sort((a, b) => String(a.time).localeCompare(String(b.time)));
  }

  function renderCourses() {
    const box = $("timeline");
    box.querySelectorAll(".course-item").forEach((n) => n.remove());
    const list = state.courses || [];
    $("courseEmpty").hidden = list.length > 0;

    const now = Date.now();
    const upcoming = list.filter((c) => c.enabled && c.fireAt)
      .sort((a, b) => a.fireAt - b.fireAt)[0];

    list.forEach((c) => {
      const el = document.createElement("div");
      el.className = "course-item";
      el.style.setProperty("--c", COLOR_HEX[c.color] || COLOR_HEX.blue);
      if (upcoming && c.id === upcoming.id) el.classList.add("next");
      if (!c.enabled) el.classList.add("disabled");
      el.dataset.id = c.id;

      const remain = c.fireAt ? c.fireAt - now : null;
      const relText = !c.enabled ? "已停用"
        : remain > 0 ? `${fmtCountdown(remain)} 后提醒`
          : "即将提醒";
      const meta = [c.room, c.teacher].filter(Boolean).map(escapeHtml).join(" · ");

      el.innerHTML = `
        <div class="c-time">${c.time}<span class="c-wd">${wdLabel(c.weekday)}</span>${upcoming && c.id === upcoming.id ? '<span class="badge-next">下一次</span>' : ""}</div>
        <div class="c-name">${escapeHtml(c.name)}</div>
        ${meta ? `<div class="c-sub">${meta}</div>` : ""}
        <div class="c-meta">下次 ${c.nextWeekday ? escapeHtml(c.nextWeekday) + " " : ""}${escapeHtml(c.nextText)} · <b>${relText}</b></div>
        ${c.note ? `<div class="c-note">${escapeHtml(c.note)}</div>` : ""}
        <div class="c-actions">
          <button class="mini-btn" data-act="edit" title="编辑">✎</button>
          <button class="mini-btn" data-act="speak" title="试听这门课的建议">🔊</button>
          <button class="mini-btn" data-act="toggle" title="${c.enabled ? "停用" : "启用"}">${c.enabled ? "⏸" : "▶"}</button>
          <button class="mini-btn del" data-act="del" title="删除">✕</button>
        </div>`;
      box.appendChild(el);
    });

    renderNext(upcoming);
    renderStat();
  }

  function gridCard(c) {
    const el = document.createElement("div");
    el.className = "gcard" + (c.enabled ? "" : " disabled");
    el.style.setProperty("--c", COLOR_HEX[c.color] || COLOR_HEX.blue);
    el.dataset.id = c.id;
    const meta = [c.room, c.teacher].filter(Boolean).map(escapeHtml).join(" · ");
    el.innerHTML = `
      <div class="gcard-time">${c.time}</div>
      <div class="gcard-name">${escapeHtml(c.name)}</div>
      <div class="gcard-meta">${meta || "—"}</div>`;
    return el;
  }

  function renderGrid() {
    const box = $("weekGrid");
    box.innerHTML = "";
    const list = state.courses || [];
    const daily = list.filter((c) => c.weekday === null || c.weekday === undefined);
    if (daily.length) {
      const row = document.createElement("div");
      row.className = "grid-daily";
      row.innerHTML = '<div class="gd-label">每天</div><div class="gd-list"></div>';
      const dl = row.querySelector(".gd-list");
      sortedByTime(daily).forEach((c) => dl.appendChild(gridCard(c)));
      box.appendChild(row);
    }

    const cols = document.createElement("div");
    cols.className = "grid-cols";
    const ti = todayIndex();
    for (let i = 0; i < 7; i++) {
      const col = document.createElement("div");
      col.className = "gcol" + (i === ti ? " today" : "");
      col.innerHTML = `<div class="ghead">周${WEEK_CHARS[i]}</div>`;
      const body = document.createElement("div");
      body.className = "gbody";
      const items = sortedByTime(list.filter((c) => c.weekday === i));
      items.forEach((c) => body.appendChild(gridCard(c)));
      if (!items.length) body.innerHTML = '<div class="gempty">—</div>';
      col.appendChild(body);
      cols.appendChild(col);
    }
    box.appendChild(cols);
  }

  function applyView() {
    $("timeline").hidden = state.view !== "list";
    $("courseEmpty").hidden = state.view !== "list" || (state.courses || []).length > 0;
    $("weekGrid").hidden = state.view !== "grid";
    document.querySelectorAll(".view-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.view === state.view);
    });
    if (state.view === "grid") renderGrid();
  }

  function renderNext(next) {
    const card = $("nextCard");
    if (!next) { card.hidden = true; return; }
    card.hidden = false;
    $("nextCourse").textContent = next.name;
    $("nextSub").textContent = `${next.nextWeekday || ""} ${next.time} · ${next.room ? next.room + " · " : ""}提前 ${state.settings.advanceMinutes} 分钟提醒`;
  }

  function tickCountdown() {
    const now = Date.now();
    const list = (state.courses || []).filter((c) => c.enabled && c.fireAt);
    const next = list.sort((a, b) => a.fireAt - b.fireAt)[0];
    if (!next) { $("nextCard").hidden = true; return; }
    $("nextCount").textContent = fmtCountdown(next.fireAt - now);
    renderNext(next);
    document.querySelectorAll(".course-item").forEach((el) => {
      const c = list.find((x) => x.id === el.dataset.id);
      const meta = el.querySelector(".c-meta b");
      if (c && meta) {
        const r = c.fireAt - now;
        meta.textContent = r > 0 ? `${fmtCountdown(r)} 后提醒` : "即将提醒";
      }
    });
  }

  /* ---------------- 播报历史 ---------------- */
  function renderHistory() {
    const ul = $("historyList");
    ul.innerHTML = "";
    const items = state.history || [];
    if (!items.length) {
      ul.innerHTML = '<li class="rec-empty">暂无播报记录，触发提醒后会出现在这里</li>';
      return;
    }
    items.forEach((h) => {
      const li = document.createElement("li");
      li.className = "rec-item";
      li.style.setProperty("--c", COLOR_HEX[h.color] || COLOR_HEX.blue);
      const d = new Date(h.at || Date.now());
      li.innerHTML = `
        <div class="rec-top">
          <span class="rec-name">${escapeHtml(h.course)}</span>
          <span class="rec-time">${fmtDateTime(d)}</span>
        </div>
        <div class="rec-text">${escapeHtml(h.text || "")}</div>`;
      ul.appendChild(li);
    });
  }

  async function loadHistory() {
    try {
      const data = await api("/api/history");
      state.history = data.history || [];
      renderHistory();
    } catch (e) { /* 静默失败，不影响主界面 */ }
  }

  /* ---------------- 状态同步 ---------------- */
  async function loadState() {
    try {
      const data = await api("/api/state");
      state.settings = data.settings;
      state.courses = data.courses;
      state.weather = data.weather;
      state.currentWeek = data.currentWeek;
      renderWeather(data.weather);
      renderHourly(data.weather);
      renderCourses();
      applyView();
      tickCountdown();
      if (data.lastAdvice && data.lastAdvice.text && !state.lastText) {
        state.lastText = data.lastAdvice.text;
        $("adviceText").textContent = data.lastAdvice.text;
      }
      renderEngine(data.tts);
    } catch (e) {
      toast("无法连接服务：" + e.message, "err");
    }
  }

  function renderEngine(tts) {
    const box = $("engineBox");
    if (!tts) { box.textContent = "检测中…"; return; }
    if (tts.available) {
      box.innerHTML = "<b>OpenVoice 本地音色克隆</b>已就绪";
    } else {
      box.innerHTML = `<b>浏览器内置中文语音</b>（当前可用）<br>OpenVoice 未配置：${tts.missing.join("、")}`;
    }
  }

  /* ---------------- 课程表单 ---------------- */
  function setFormColor(color) {
    state.formColor = COLOR_HEX[color] ? color : "blue";
    document.querySelectorAll(".swatch").forEach((s) => {
      s.classList.toggle("active", s.dataset.color === state.formColor);
    });
  }

  function openForm(course) {
    state.editingId = course ? course.id : null;
    $("courseForm").hidden = false;
    $("inputName").value = course ? course.name : "";
    $("inputTime").value = course ? course.time : "09:00";
    $("inputWeekday").value = course && course.weekday != null ? String(course.weekday) : "";
    $("inputTeacher").value = course ? (course.teacher || "") : "";
    $("inputRoom").value = course ? (course.room || "") : "";
    $("inputWeeks").value = course ? (course.weeks || "") : "";
    $("inputNote").value = course ? (course.note || "") : "";
    setFormColor(course ? course.color : "blue");
    $("inputName").focus();
  }

  function closeForm() {
    state.editingId = null;
    $("courseForm").hidden = true;
  }

  $("btnAddCourse").onclick = () => openForm(null);
  $("btnCancelCourse").onclick = closeForm;

  $("colorPicker").addEventListener("click", (ev) => {
    const sw = ev.target.closest(".swatch");
    if (sw) setFormColor(sw.dataset.color);
  });

  $("btnSaveCourse").onclick = async () => {
    const name = $("inputName").value.trim();
    const time = $("inputTime").value;
    if (!name) return toast("请填写课程名称", "err");
    if (!time) return toast("请选择上课时间", "err");
    const wdRaw = $("inputWeekday").value;
    const payload = {
      name, time,
      weekday: wdRaw === "" ? null : Number(wdRaw),
      teacher: $("inputTeacher").value.trim(),
      room: $("inputRoom").value.trim(),
      weeks: $("inputWeeks").value.trim(),
      note: $("inputNote").value.trim(),
      color: state.formColor
    };
    try {
      if (state.editingId) {
        await api("/api/courses/" + state.editingId, "PUT", payload);
        toast("课程已更新", "ok");
        addLog(`更新课程：${name} ${time}`);
      } else {
        await api("/api/courses", "POST", payload);
        toast("课程已添加", "ok");
        addLog(`新增课程：${name} ${time}`);
      }
      closeForm();
      await loadState();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  async function handleCourseAction(ev) {
    const id = ev.target.closest("[data-id]")?.dataset.id;
    const course = state.courses.find((c) => c.id === id);
    if (!course) return;
    const btn = ev.target.closest("[data-act]");
    const act = btn ? btn.dataset.act : "edit";
    try {
      if (act === "edit") {
        openForm(course);
      } else if (act === "speak") {
        const data = await api("/api/advice/preview", "POST", { courseId: course.id });
        $("adviceText").textContent = data.text;
        $("adviceTag").textContent = "课程试听";
        $("adviceTime").textContent = new Date().toLocaleTimeString("zh-CN");
        state.lastText = data.text;
        speak(data.text);
      } else if (act === "toggle") {
        await api("/api/courses/" + course.id, "PUT", { enabled: !course.enabled });
        addLog(`${course.enabled ? "停用" : "启用"}课程：${course.name}`);
        await loadState();
      } else if (act === "del") {
        if (!confirm(`确定删除课程「${course.name}」？`)) return;
        await api("/api/courses/" + course.id, "DELETE");
        toast("课程已删除", "ok");
        addLog(`删除课程：${course.name}`);
        await loadState();
      }
    } catch (e) {
      toast(e.message, "err");
    }
  }

  $("timeline").addEventListener("click", handleCourseAction);
  $("weekGrid").addEventListener("click", handleCourseAction);

  /* ---------------- 视图切换 ---------------- */
  $("viewTabs").addEventListener("click", (ev) => {
    const tab = ev.target.closest(".view-tab");
    if (!tab) return;
    state.view = tab.dataset.view;
    applyView();
  });

  /* ---------------- 播报操作 ---------------- */
  $("btnSpeak").onclick = () => {
    if (state.speaking) {
      speechSynthesis.cancel();
      return;
    }
    speak($("adviceText").textContent.trim());
  };

  $("btnPreview").onclick = async () => {
    try {
      const data = await api("/api/advice/preview", "POST", {});
      state.lastText = data.text;
      $("adviceText").textContent = data.text;
      $("adviceTag").textContent = "即时预览";
      $("adviceTime").textContent = new Date().toLocaleTimeString("zh-CN");
      renderWeather(data.weather);
      renderHourly(data.weather);
      addLog("已生成建议：" + data.course);
      if (state.settings.autoSpeak) speak(data.text);
    } catch (e) {
      toast(e.message, "err");
    }
  };

  $("btnWeatherRefresh").onclick = async () => {
    try {
      const data = await api("/api/weather/refresh", "POST", {});
      state.weather = data.weather;
      renderWeather(data.weather);
      renderHourly(data.weather);
      toast("天气已刷新", "ok");
      addLog("天气刷新：" + data.weather.text + " 体感 " + data.weather.feelsLike + "°");
    } catch (e) {
      toast(e.message, "err");
    }
  };

  /* ---------------- 记录面板 ---------------- */
  $("recTabs").addEventListener("click", (ev) => {
    const tab = ev.target.closest(".rec-tab");
    if (!tab) return;
    state.recTab = tab.dataset.rec;
    document.querySelectorAll(".rec-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.rec === state.recTab);
    });
    $("historyList").hidden = state.recTab !== "history";
    $("logList").hidden = state.recTab !== "log";
    $("btnClearHistory").hidden = state.recTab !== "history";
  });

  $("btnClearHistory").onclick = async () => {
    if (!confirm("清空全部播报历史？")) return;
    try {
      await api("/api/history", "DELETE");
      state.history = [];
      renderHistory();
      toast("历史已清空", "ok");
    } catch (e) {
      toast(e.message, "err");
    }
  };

  /* ---------------- 导入导出 ---------------- */
  $("btnExport").onclick = () => {
    const a = document.createElement("a");
    a.href = "/api/courses/export";
    a.download = "courses.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    addLog("已导出课程表");
  };

  $("btnImport").onclick = () => $("fileImport").click();

  $("fileImport").addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const list = Array.isArray(data) ? data : data.courses;
      if (!Array.isArray(list) || !list.length) throw new Error("文件中没有课程列表");
      const res = await api("/api/courses/import", "POST", { courses: list });
      toast(`导入完成：新增 ${res.added} 门，共 ${res.total} 门`, "ok");
      addLog(`导入课程 ${res.added} 门`);
      await loadState();
    } catch (e) {
      toast("导入失败：" + e.message, "err");
    }
  });

  /* ---------------- 设置 ---------------- */
  function openDrawer() {
    const s = state.settings;
    $("setAdvance").value = s.advanceMinutes;
    $("advanceVal").textContent = s.advanceMinutes + " 分钟";
    $("setAutoSpeak").checked = !!s.autoSpeak;
    $("setRate").value = s.voiceRate;
    $("rateVal").textContent = Number(s.voiceRate).toFixed(1) + "×";
    $("setTermStart").value = s.termStart || "";
    $("setProvider").value = s.provider || "mock";
    $("setCity").value = s.city || "";
    $("setLocation").value = s.location || "";
    $("setApiKey").value = s.apiKey || "";
    $("drawer").classList.add("open");
    $("scrim").classList.add("show");
  }
  function closeDrawer() {
    $("drawer").classList.remove("open");
    $("scrim").classList.remove("show");
  }

  $("btnSettings").onclick = openDrawer;
  $("btnCloseDrawer").onclick = closeDrawer;
  $("scrim").onclick = closeDrawer;

  $("setAdvance").oninput = (e) => { $("advanceVal").textContent = e.target.value + " 分钟"; };
  $("setRate").oninput = (e) => { $("rateVal").textContent = Number(e.target.value).toFixed(1) + "×"; };

  $("btnSaveSettings").onclick = async () => {
    const patch = {
      advanceMinutes: Number($("setAdvance").value),
      autoSpeak: $("setAutoSpeak").checked,
      voiceRate: Number($("setRate").value),
      termStart: $("setTermStart").value,
      provider: $("setProvider").value,
      city: $("setCity").value.trim(),
      location: $("setLocation").value.trim(),
      apiKey: $("setApiKey").value.trim()
    };
    try {
      const data = await api("/api/settings", "POST", patch);
      state.settings = data.settings;
      toast("设置已保存", "ok");
      addLog(`设置更新：提前 ${data.settings.advanceMinutes} 分钟，天气源 ${data.settings.provider}`);
      closeDrawer();
      await loadState();
    } catch (e) {
      toast(e.message, "err");
    }
  };

  /* ---------------- 深色模式 ---------------- */
  function applyTheme(dark) {
    document.body.classList.toggle("dark", dark);
    $("btnTheme").textContent = dark ? "☀️" : "🌙";
    try { localStorage.setItem("smarttrip-theme", dark ? "dark" : "light"); } catch (e) {}
  }
  $("btnTheme").onclick = () => applyTheme(!document.body.classList.contains("dark"));
  try {
    applyTheme(localStorage.getItem("smarttrip-theme") === "dark");
  } catch (e) { /* 忽略隐私模式下的 localStorage 异常 */ }

  /* ---------------- SSE 实时提醒 ---------------- */
  function connectEvents() {
    if (!("EventSource" in window)) return;
    const es = new EventSource("/api/events");
    es.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      if (data.type !== "reminder") return;

      state.lastText = data.text;
      $("adviceText").textContent = data.text;
      $("adviceTag").textContent = "课前播报";
      $("adviceTime").textContent = new Date().toLocaleTimeString("zh-CN");
      renderWeather(data.weather);
      renderHourly(data.weather);
      toast(`课前提醒：${data.course}（${data.remaining} 分钟后上课）`, "ok");
      addLog(`触发课前提醒：${data.course} ${data.time}`, true);
      if (state.settings.autoSpeak) speak(data.text);
      loadState();
      loadHistory();
    };
    es.onerror = () => { /* EventSource 会自动重连 */ };
  }

  /* ---------------- 时钟 ---------------- */
  function tickClock() {
    const d = new Date();
    $("clockTime").textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    $("clockDate").textContent = `${d.getMonth() + 1}月${d.getDate()}日 周${WEEK_CHARS[todayIndex()]}`;
  }

  /* ---------------- 波形条 ---------------- */
  (function buildWave() {
    const wave = $("wave");
    for (let i = 0; i < 34; i++) {
      const b = document.createElement("i");
      b.style.animationDelay = (i * 0.045).toFixed(3) + "s";
      b.style.height = 6 + Math.round(Math.random() * 6) + "px";
      wave.appendChild(b);
    }
  })();

  /* ---------------- 启动 ---------------- */
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(tickCountdown, 500);
  loadState().then(loadHistory).then(connectEvents);
  setInterval(loadState, 60000);
  addLog("系统已启动，等待课程提醒");
})();
