from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundcard as sc

from app.core.config import settings


@dataclass
class AudioChunk:
    data: np.ndarray
    sample_rate: int
    channels: int


class AudioCapture:
    def __init__(
        self,
        sample_rate: int,
        channels: int = 1,
        block_seconds: float = 0.5,
        input_device: Optional[str] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_seconds = block_seconds
        self.input_device = input_device

        self._queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mic = None

    @staticmethod
    def list_microphones():
        return sc.all_microphones(include_loopback=True)

    def _select_microphone(self):
        microphones = self.list_microphones()
        if not microphones:
            raise RuntimeError("No microphone or loopback device found.")

        if self.input_device:
            keyword = self.input_device.lower()
            for mic in microphones:
                name = str(mic)
                if keyword in name.lower():
                    return mic
            raise RuntimeError(
                f"Configured input device not found: {self.input_device}"
            )

        default_mic = sc.default_microphone()
        if default_mic is not None:
            return default_mic

        return microphones[0]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._mic = self._select_microphone()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def read(self, timeout: float = 1.0) -> AudioChunk:
        return self._queue.get(timeout=timeout)

    def _record_loop(self) -> None:
        frames = max(1, int(self.sample_rate * self.block_seconds))

        with self._mic.recorder(
            samplerate=self.sample_rate,
            channels=self.channels,
        ) as recorder:
            while not self._stop_event.is_set():
                data = recorder.record(numframes=frames)

                if data.ndim == 1:
                    data = data.reshape(-1, 1)

                mono = data.mean(axis=1, keepdims=True).astype(np.float32)

                chunk = AudioChunk(
                    data=mono,
                    sample_rate=self.sample_rate,
                    channels=1,
                )

                try:
                    self._queue.put(chunk, timeout=0.2)
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._queue.put_nowait(chunk)


def describe_microphones() -> str:
    lines = []
    for idx, mic in enumerate(AudioCapture.list_microphones(), start=1):
        lines.append(f"{idx}. {mic}")
    return "\n".join(lines)


def build_default_capture() -> AudioCapture:
    return AudioCapture(
        sample_rate=settings.sample_rate,
        channels=settings.channels,
        block_seconds=settings.block_seconds,
        input_device=settings.input_device,
    )
