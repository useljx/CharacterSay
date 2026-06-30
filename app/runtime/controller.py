"""应用控制器 —— 串联音频采集 → ASR → 话语缓冲 → LLM → UI。"""

from __future__ import annotations

import asyncio
import contextlib
import queue
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.asr.client import ASRSegment, VolcASRClient, build_default_asr_client
from app.audio.capture import build_default_capture
from app.audio.model import AudioModel, DummyAudioModel
from app.character.manager import CharacterManager
from app.core.config import settings
from app.llm.client import LLMClient
from app.pipeline.utterance_buffer import UtteranceBuffer


class AppController(QObject):
    status_changed = Signal(str)
    partial_changed = Signal(str)      # ASR 中间结果（用户正在说）
    final_changed = Signal(str)        # ASR 最终结果（用户刚说完的一句话）
    utterance_changed = Signal(str)    # 触发的完整话语（送往 LLM 的）
    response_changed = Signal(str)     # 角色回复（流式更新）
    error_changed = Signal(str)
    history_changed = Signal(str, str) # (用户话语, 角色回复)

    def __init__(self, character_manager: CharacterManager | None = None) -> None:
        super().__init__()
        self._capture = None
        self._asr: VolcASRClient | None = None
        self._llm = LLMClient()
        self._char_mgr = character_manager or CharacterManager()

        # ── 音频模型（占位，后续可替换为真实 TTS）──
        self._audio_model: AudioModel = DummyAudioModel()

        # ── 话语缓冲 ──
        self._utterance_buffer = UtteranceBuffer(
            silence_seconds=0.6,  # 600ms 静默判定用户说完
            min_chars=4,           # 对话场景阈值低于面试（聊天可以很短）
            max_chars=300,
        )

        # ── 代数（防止旧回复覆盖新回复）──
        self._response_gen = 0

        # ── 对话历史 ──
        self._conversation_history: list[dict[str, str]] = []
        self._max_history_rounds = 5

        # ── 节流 ──
        self._last_partial_time = 0.0
        self._last_partial_text = ""
        self._partial_throttle_s = 0.2

        # ── 任务 ──
        self._receiver_task: asyncio.Task | None = None
        self._utterance_task: asyncio.Task | None = None
        self._pump_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._running = False

        # ── 字幕 ──
        self._subtitle_path = Path("captions.txt")
        self._subtitle_max_bytes = 500 * 1024

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def audio_model(self) -> AudioModel:
        return self._audio_model

    @audio_model.setter
    def audio_model(self, model: AudioModel) -> None:
        """注入音频模型实例（如 TTS 服务）。"""
        self._audio_model = model
        print(f"[Controller] Audio model replaced: {model.model_name}")

    @property
    def character_manager(self) -> CharacterManager:
        return self._char_mgr

    # ------------------------------------------------------------------
    # 启停
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return

        # 确保角色已加载
        if self._char_mgr.active is None:
            self._char_mgr.auto_activate()
            if self._char_mgr.active is None:
                self.error_changed.emit("没有可用的角色，请先在配置中创建角色。")
                return

        self._capture = build_default_capture()
        self._asr = build_default_asr_client()
        self._stop_event = asyncio.Event()

        self._capture.start()
        await self._asr.connect()
        await self._asr.send_full_request()

        self._receiver_task = asyncio.create_task(self._recv_loop())
        self._utterance_task = asyncio.create_task(self._utterance_loop())
        self._pump_task = asyncio.create_task(self._audio_loop())

        self._running = True
        char = self._char_mgr.active
        self.status_changed.emit(f"正在与 {char.name} 对话中")

    async def stop(self) -> None:
        if not self._running:
            return

        self._stop_event.set()

        for task in (self._receiver_task, self._utterance_task, self._pump_task):
            if task:
                task.cancel()
        for task in (self._receiver_task, self._utterance_task, self._pump_task):
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        if self._capture:
            self._capture.stop()
        if self._asr:
            await self._asr.close()

        self._running = False
        self.status_changed.emit("已停止")

    # ------------------------------------------------------------------
    # 内部循环
    # ------------------------------------------------------------------

    async def _audio_loop(self) -> None:
        assert self._capture is not None
        assert self._asr is not None
        while not self._stop_event.is_set():
            try:
                chunk = await asyncio.to_thread(self._capture.read, 2.0)
                await self._asr.send_audio_chunk(chunk.data)
            except queue.Empty:
                continue
            except Exception as exc:
                self.error_changed.emit(str(exc))

    async def _recv_loop(self) -> None:
        assert self._asr is not None
        while not self._stop_event.is_set():
            result = await self._asr.recv_once()
            if result is None:
                continue
            if result.segments:
                for segment in result.segments:
                    await self._handle_segment(segment)
            elif result.text.strip():
                segment = ASRSegment(text=result.text, is_final=result.is_final)
                await self._handle_segment(segment)

    async def _handle_segment(self, segment: ASRSegment) -> None:
        text = " ".join(segment.text.strip().split())
        if not text:
            return

        if segment.is_final:
            self.final_changed.emit(text)
            self._utterance_buffer.on_final(text)
            asyncio.create_task(self._append_subtitle_async(text))
        else:
            now = time.monotonic()
            if (
                text == self._last_partial_text
                or (now - self._last_partial_time) < self._partial_throttle_s
            ):
                return
            self._last_partial_time = now
            self._last_partial_text = text
            self.partial_changed.emit(text)

    # ------------------------------------------------------------------
    # 话语 → LLM 主循环
    # ------------------------------------------------------------------

    async def _utterance_loop(self) -> None:
        _COOLDOWN_S = 3.0           # 冷却窗口
        _MAX_UTTERANCE_CHARS = 500  # 合并后话语上限
        _cooldown_start = 0.0       # 冷却窗口起点（不可重置）
        _last_utterance_text = ""
        _llm_task: asyncio.Task | None = None

        while not self._stop_event.is_set():
            await asyncio.sleep(0.05)

            if not self._utterance_buffer.should_emit():
                continue

            utterance = self._utterance_buffer.pop_utterance().strip()
            if not utterance:
                continue

            now = time.monotonic()

            # 冷却期内 → 用户在快速补充，合并话语但不重置窗口
            if _last_utterance_text and (now - _cooldown_start) < _COOLDOWN_S:
                merged = f"{_last_utterance_text} {utterance}"
                if len(merged) > _MAX_UTTERANCE_CHARS:
                    merged = merged[-_MAX_UTTERANCE_CHARS:]
                if _llm_task and not _llm_task.done():
                    _llm_task.cancel()
                utterance = merged
                _last_utterance_text = utterance
                # _cooldown_start 不变
            else:
                _cooldown_start = now
                _last_utterance_text = utterance

            self._response_gen += 1
            gen = self._response_gen
            self.utterance_changed.emit(utterance)
            self.status_changed.emit(f"{self._char_mgr.active.name} 正在思考...")

            _llm_task = asyncio.create_task(self._stream_response(utterance, gen))

            try:
                result = await _llm_task
                if result is not None:
                    q, a = result
                    self._conversation_history.append({"q": q, "a": a})
                    if len(self._conversation_history) > self._max_history_rounds:
                        self._conversation_history = self._conversation_history[-self._max_history_rounds:]
                    self.history_changed.emit(q, a)

                    # ── 音频模型输出（未来 TTS）──
                    if self._audio_model.supported:
                        try:
                            voice_id = self._char_mgr.active.voice_id if self._char_mgr.active else ""
                            audio_bytes = await self._audio_model.synthesize(a, voice_id)
                            await self._play_audio(audio_bytes)
                        except Exception as exc:
                            print(f"[AudioModel] TTS skipped: {exc}")

                char_name = self._char_mgr.active.name if self._char_mgr.active else "角色"
                self.status_changed.emit(f"正在与 {char_name} 对话中")
            except asyncio.CancelledError:
                char_name = self._char_mgr.active.name if self._char_mgr.active else "角色"
                self.status_changed.emit(f"正在与 {char_name} 对话中")
            except Exception as exc:
                self.error_changed.emit(str(exc))
                self.status_changed.emit("对话异常")

    async def _stream_response(self, utterance: str, gen: int) -> tuple[str, str] | None:
        """流式生成角色回复。仅当 gen 仍是当前代数时才输出。"""
        char = self._char_mgr.active
        if char is None:
            return None

        system_prompt = self._char_mgr.build_system_prompt(char)

        # Token 估算保护
        estimated_tokens = (len(utterance) + len(system_prompt) + 2000) // 2
        if estimated_tokens > 8000:
            # 截断 system prompt
            system_prompt = system_prompt[:4000] + "\n\n（角色设定已截断以适配上下文长度）"

        accumulated = ""
        _LLM_TIMEOUT_S = 45.0

        try:
            async with asyncio.timeout(_LLM_TIMEOUT_S):
                async for token in self._llm.answer_stream(
                    user_message=utterance,
                    system_prompt=system_prompt,
                    history=list(self._conversation_history),
                ):
                    if self._response_gen != gen:
                        return None
                    accumulated += token
                    self.response_changed.emit(accumulated)
        except asyncio.TimeoutError:
            if self._response_gen != gen:
                return None
            if accumulated:
                accumulated += "\n\n[回复生成超时]"
                self.response_changed.emit(accumulated)
            else:
                accumulated = "（思考中...请再说一遍？）"
                self.response_changed.emit(accumulated)
            return utterance, accumulated.strip()
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            if self._response_gen != gen:
                return None
            error_msg = f"LLM 调用失败: {exc}"
            self.error_changed.emit(error_msg)
            print(f"[LLM ERROR] {error_msg}")
            accumulated = f"（出了点问题: {exc}）"
            self.response_changed.emit(accumulated)
            return utterance, accumulated.strip()

        if self._response_gen != gen:
            return None

        if not accumulated.strip():
            accumulated = "（嗯...让我想想）"
            self.response_changed.emit(accumulated)

        return utterance, accumulated.strip()

    async def _play_audio(self, audio_bytes: bytes) -> None:
        """播放音频（预留实现，当前为空）。"""
        # TODO: 使用 PyAudio / sounddevice 播放 PCM 音频
        # 示例:
        #   import sounddevice as sd
        #   import numpy as np
        #   samples = np.frombuffer(audio_bytes, dtype=np.int16)
        #   sd.play(samples, samplerate=16000)
        #   sd.wait()
        pass

    # ------------------------------------------------------------------
    # 字幕
    # ------------------------------------------------------------------

    async def _append_subtitle_async(self, text: str) -> None:
        try:
            await asyncio.to_thread(self._append_subtitle_sync, text)
        except Exception:
            pass

    def _append_subtitle_sync(self, text: str) -> None:
        try:
            if (
                self._subtitle_path.exists()
                and self._subtitle_path.stat().st_size > self._subtitle_max_bytes
            ):
                content = self._subtitle_path.read_text(encoding="utf-8", errors="replace")
                keep = content[-self._subtitle_max_bytes // 2:]
                self._subtitle_path.write_text(keep, encoding="utf-8")
            with self._subtitle_path.open("a", encoding="utf-8") as f:
                f.write(f"[用户] {text}\n")
        except Exception:
            pass
