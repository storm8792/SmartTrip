# -*- coding: utf-8 -*-
"""可选：OpenVoice 本地语音合成适配。

浏览器端已内置 Web Speech 语音播报，可开箱即用。
若想使用 SRS 中描述的 OpenVoice 音色克隆，把预训练模型放到 checkpoints/ 下，
并安装 openvoice、torch，本模块即可接管 /api/tts。
"""
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT_BASE = os.path.join(BASE_DIR, "checkpoints", "base_speakers", "EN")
CKPT_CONVERTER = os.path.join(BASE_DIR, "checkpoints", "converter")
REFERENCE_WAV = os.path.join(BASE_DIR, "references", "ref.wav")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

_lock = threading.Lock()
_engine = None


def status():
    """检查 OpenVoice 是否可用，供前端提示。"""
    missing = []
    if not os.path.isdir(CKPT_CONVERTER):
        missing.append("checkpoints/converter")
    if not os.path.isfile(REFERENCE_WAV):
        missing.append("references/ref.wav")
    try:
        import torch  # noqa: F401
    except Exception:
        missing.append("torch")
    try:
        import openvoice  # noqa: F401
    except Exception:
        missing.append("openvoice")
    return {"available": not missing, "missing": missing}


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    from openvoice.api import BaseSpeakerTTS, ToneColorConverter

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = BaseSpeakerTTS(os.path.join(CKPT_BASE, "config.json"), device="cpu")
    base.load_ckpt(os.path.join(CKPT_BASE, "checkpoint.pth"))
    converter = ToneColorConverter(os.path.join(CKPT_CONVERTER, "config.json"), device="cpu")
    converter.load_ckpt(os.path.join(CKPT_CONVERTER, "checkpoint.pth"))
    _engine = (base, converter)
    return _engine


def synthesize(text, out_path=None):
    """文本 → 目标音色 wav。返回输出文件绝对路径。"""
    with _lock:
        base, converter = _get_engine()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = out_path or os.path.join(OUTPUT_DIR, "advice.wav")
        tmp_path = os.path.join(OUTPUT_DIR, "tmp.wav")
        se_path = os.path.join(OUTPUT_DIR, "se.pth")

        base.tts(text, tmp_path, speaker="default", language="Chinese")
        converter.extract_se([REFERENCE_WAV], se_path)
        converter.convert(
            audio_src_path=tmp_path,
            src_se=se_path,
            tgt_se=se_path,
            output_path=out_path,
            message="@SmartTrip",
        )
        return out_path
