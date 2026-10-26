# SmartTrip · 基于语音合成技术的行程播报系统

课程表管理 + 天气体感建议 + 课前定时语音播报。纯 Python 标准库实现（HTTP 服务 + SSE 推送 + 单页前端），**零第三方依赖**，双击即可运行。

## 功能

- **课程表**：课程名、上课时间、星期、周次（如 `1-16`）、教师、教室、颜色标签、备注
- **两种视图**：时间轴视图 / 周课表网格视图，按当前周次自动过滤
- **课前播报**：默认提前 10 分钟触发，跑在独立调度线程里；已触发记录持久化，重启不会重复播报
- **天气**：和风天气实时接口（实时 / 分钟级降水 / 24 小时）；未填 Key 时用「城市 + 日期 + 小时」哈希生成稳定的演示数据，断网也能演示
- **建议文案**：时间 → 课程 → 地点/教师 → 体感温度（五档）→ 降水 → 紫外线 → 风力，逐段拼装
- **语音播报**：浏览器内置 Web Speech 优先，开箱即用；OpenVoice 作为可选增强（见下文）
- **播报历史**：保留最近 100 条，可一键清空
- **其他**：深色模式、课程导入 / 导出（JSON）、设置抽屉（提前分钟数、语速、自动播报、学期起始日）

## 快速开始

环境要求：**Windows 10/11 + Python 3.10 及以上**。

```
双击 启动SmartTrip.bat
```

或者命令行：

```bat
python app.py
```

启动后会自动打开浏览器（默认 <http://127.0.0.1:8770>；端口被占用时自动往后找，最多试 20 个）。

可选参数：

```bat
python app.py --port 8800      :: 指定端口
python app.py --no-browser     :: 不自动开浏览器
```

## 目录结构

```
SmartTrip/
├── app.py                 HTTP 服务、路由、SSE 事件总线、调度线程装配
├── core/
│   ├── schedule.py        课程模型、下次上课时间计算、周次解析、Scheduler 调度线程
│   ├── weather.py         和风天气三个接口 + 演示数据生成
│   ├── advice.py          播报文案生成
│   ├── store.py           JSON 持久化（课程 / 设置 / 已触发 / 历史）
│   └── tts_openvoice.py   OpenVoice 可选适配层（未安装时前端自动禁用）
├── static/                单页前端（index.html / app.js / style.css）
├── data/                  运行数据
│   ├── courses.json       课程表
│   ├── settings.json      设置（含天气 Key，默认留空）
│   ├── fired.json         已触发的播报记录（防重复）
│   └── history.json       播报历史
├── assets/smarttrip.ico   图标
└── 启动SmartTrip.bat
```

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 全量状态：课程、天气、上次建议、TTS 状态、当前周次 |
| GET | `/api/weather` | 当前天气（服务端缓存 5 分钟） |
| POST | `/api/weather/refresh` | 强制刷新天气 |
| GET | `/api/events` | SSE 事件流，播报触发时实时推送 |
| GET / POST | `/api/courses`、`/api/courses/import` | 课程读取 / 新增 / 批量导入 |
| PUT / DELETE | `/api/courses/<id>` | 修改 / 删除单门课程 |
| GET | `/api/courses/export` | 导出课程 JSON |
| POST | `/api/advice/preview` | 手动生成一次建议文案 |
| GET / POST / DELETE | `/api/settings`、`/api/history` | 设置读写、历史读取与清空 |
| POST | `/api/tts` | 调用 OpenVoice 合成（不可用时返回原因） |
| GET | `/api/tts/status` | 检查 OpenVoice 是否可用 |

## 天气配置

设置抽屉 → 数据源选「和风天气」，填城市 / 经纬度 / API Key，保存后点「刷新天气」。
Key 只写入本机 `data/settings.json`，不会上传到任何地方；默认值是空字符串，此时走演示数据。

## 语音合成

- **默认**：浏览器 `speechSynthesis`，语速可在设置里调（0.6×–1.8×），不需要任何模型。
- **可选 OpenVoice**：把预训练权重放到 `checkpoints/base_speakers/EN/`、`checkpoints/converter/`，参考音色放到 `references/ref.wav`，再 `pip install openvoice torch`，重启后 `/api/tts/status` 会变为可用，前端会走本地合成。

## 已知限制

- 课程表按周循环，不区分单双周与节假日调课。
- 演示天气是哈希生成的稳定假数据，仅用于无 Key / 断网时演示，不代表真实天气。
- 播报依赖页面开着；浏览器关闭后定时器停止（服务端仍会记录已触发状态）。
- OpenVoice 首次合成需要加载数百 MB 模型，冷启动较慢。
