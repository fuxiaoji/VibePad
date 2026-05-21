"""语音输入模块。

按住手柄按钮→录音→松开→识别→自动输入文字。
使用 Windows Speech Recognition API（无需联网），通过 speech_recognition 库封装。

Usage:
    vi = VoiceInput()
    vi.start()  # 开始录音
    # ... 说话 ...
    text = vi.stop()  # 停止录音，返回识别文字（失败返回空字符串）
    vi.cancel()  # 取消录音
"""

from __future__ import annotations

import threading
import io
import time
from typing import Optional


class VoiceInput:
    """语音输入器 — 后台录音 + 识别 + 自动输入。"""

    def __init__(self):
        self._recording = False
        self._thread: Optional[threading.Thread] = None
        self._audio_data: Optional[bytes] = None
        self._error: Optional[str] = None
        self._ready = threading.Event()

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self):
        """开始录音（后台线程）。重复调用无效果。"""
        if self._recording:
            return
        self._recording = True
        self._audio_data = None
        self._error = None
        self._ready.clear()
        self._thread = threading.Thread(target=self._record, daemon=True, name="voice-record")
        self._thread.start()

    def stop(self) -> str:
        """停止录音，等待识别完成，返回识别文字。失败返回空字符串。"""
        if not self._recording:
            return ""
        self._recording = False
        self._ready.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

        if self._audio_data and len(self._audio_data) > 1600:
            return self._recognize(self._audio_data)
        return ""

    def cancel(self):
        """取消录音（不识别）。"""
        self._recording = False
        self._ready.set()
        self._audio_data = None
        self._thread = None

    # ── 内部 ──

    def _record(self):
        """后台录音线程。"""
        try:
            import speech_recognition as sr
        except ImportError:
            self._error = "请安装 speech_recognition: pip install speech_recognition"
            return

        try:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                frames = []
                while self._recording:
                    try:
                        audio = r.listen(source, timeout=0.3, phrase_time_limit=None)
                        frames.append(audio)
                    except sr.WaitTimeoutError:
                        continue
                if frames:
                    self._audio_data = self._merge_audio(frames, r, source)
        except Exception as e:
            self._error = str(e)

    @staticmethod
    def _merge_audio(frames, recognizer, original_source) -> bytes:
        """合并多个 AudioData 碎片。"""
        try:
            import speech_recognition as sr
            combined = sr.AudioData(
                b"".join(f.get_raw_data() for f in frames),
                original_source.SAMPLE_RATE,
                original_source.SAMPLE_WIDTH,
            )
            return combined.get_wav_data()
        except Exception:
            return b"".join(f.get_wav_data() for f in frames)

    @staticmethod
    def _recognize(wav_data: bytes) -> str:
        """将 WAV 音频数据识别为文字。"""
        try:
            import speech_recognition as sr
        except ImportError:
            return ""

        r = sr.Recognizer()
        try:
            audio = sr.AudioData(wav_data, 16000, 2)
            return r.recognize_google(audio, language="zh-CN")
        except sr.UnknownValueError:
            return ""
        except sr.RequestError:
            # Google 不可用，尝试本地 Sphinx (离线识别)
            try:
                return r.recognize_sphinx(audio)
            except Exception:
                pass
        except Exception:
            pass
        return ""
