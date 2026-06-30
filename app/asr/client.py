from __future__ import annotations

import gzip
import json
import struct
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import websockets
from websockets import ClientConnection

from app.core.config import settings

PROTOCOL_VERSION = 0x1
HEADER_SIZE = 0x1

MSG_TYPE_FULL_CLIENT_REQUEST = 0x1
MSG_TYPE_AUDIO_ONLY_REQUEST = 0x2
MSG_TYPE_FULL_SERVER_RESPONSE = 0x9
MSG_TYPE_SERVER_ERROR_RESPONSE = 0xF

FLAG_NO_SEQUENCE = 0x0
FLAG_POS_SEQUENCE = 0x1
FLAG_NEG_SEQUENCE = 0x3

SERIALIZATION_NONE = 0x0
SERIALIZATION_JSON = 0x1

COMPRESSION_NONE = 0x0
COMPRESSION_GZIP = 0x1


@dataclass
class ASRSegment:
    text: str
    is_final: bool
    start_time: int = 0
    end_time: int = 0


@dataclass
class ASRResult:
    text: str
    is_final: bool
    raw: dict[str, Any]
    segments: list[ASRSegment]


class VolcASRClient:
    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._ws: ClientConnection | None = None
        self._request_id = str(uuid.uuid4())
        self._connect_id = str(uuid.uuid4())
        self._audio_sequence = 0

    def validate(self) -> None:
        if not settings.volc_app_id or settings.volc_app_id == "xxxxxxxxx":
            raise RuntimeError("VOLC_APP_ID is not configured.")
        if not settings.volc_access_token or settings.volc_access_token == "xxxxxxxxx":
            raise RuntimeError("VOLC_ACCESS_TOKEN is not configured.")
        if not settings.volc_ws_url or "xxxxxxxxx" in settings.volc_ws_url:
            raise RuntimeError("VOLC_WS_URL is not configured.")

    async def connect(self) -> None:
        self.validate()

        headers = {
            "X-Api-App-Key": settings.volc_app_id,
            "X-Api-Access-Key": settings.volc_access_token,
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": self._request_id,
            "X-Api-Connect-Id": self._connect_id,
        }

        self._ws = await websockets.connect(
            settings.volc_ws_url,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
            open_timeout=10,
        )

        log_id = "?"
        response = getattr(self._ws, "response", None)
        if response is not None:
            log_id = response.headers.get("X-Tt-Logid", "?")

        print(f"[WS] Connected. LogID: {log_id}")

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_full_request(self) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")

        payload = {
            "user": {
                "uid": "charactersay-user",
                "platform": "windows",
            },
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
                "show_utterances": True,
                "result_type": "single",
                "enable_nonstream": True,
                "end_window_size": 800,
                "force_to_speech_time": 1000,
            },
        }

        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        compressed_payload = gzip.compress(payload_bytes)

        header = self._build_header(
            msg_type=MSG_TYPE_FULL_CLIENT_REQUEST,
            flags=FLAG_NO_SEQUENCE,
            serialization=SERIALIZATION_JSON,
            compression=COMPRESSION_GZIP,
        )
        frame = header + struct.pack(">I", len(compressed_payload)) + compressed_payload
        await self._ws.send(frame)

        self._audio_sequence = 1
        print("[ASR] Sent full client request")

    async def send_audio_chunk(self, audio: np.ndarray, is_last: bool = False) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")

        audio_bytes = float32_to_pcm16_bytes(audio)
        compressed_audio = gzip.compress(audio_bytes)

        if is_last:
            flags = FLAG_NEG_SEQUENCE
            self._audio_sequence = -1
            sequence_bytes = struct.pack(">i", self._audio_sequence)
        else:
            self._audio_sequence += 1
            flags = FLAG_POS_SEQUENCE
            sequence_bytes = struct.pack(">i", self._audio_sequence)

        header = self._build_header(
            msg_type=MSG_TYPE_AUDIO_ONLY_REQUEST,
            flags=flags,
            serialization=SERIALIZATION_NONE,
            compression=COMPRESSION_GZIP,
        )
        frame = (
            header
            + sequence_bytes
            + struct.pack(">I", len(compressed_audio))
            + compressed_audio
        )
        await self._ws.send(frame)

        if settings.debug:
            print(
                f"[ASR] Sent audio chunk: seq={self._audio_sequence}, "
                f"bytes={len(compressed_audio)}, is_last={is_last}"
            )

    async def recv_once(self) -> ASRResult | None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")

        try:
            message = await self._ws.recv()
        except websockets.exceptions.ConnectionClosed:
            return None

        if isinstance(message, str):
            return None

        return self._parse_binary_response(message)

    def _build_header(
        self,
        msg_type: int,
        flags: int,
        serialization: int,
        compression: int,
    ) -> bytes:
        b0 = ((PROTOCOL_VERSION & 0x0F) << 4) | (HEADER_SIZE & 0x0F)
        b1 = ((msg_type & 0x0F) << 4) | (flags & 0x0F)
        b2 = ((serialization & 0x0F) << 4) | (compression & 0x0F)
        b3 = 0x00
        return bytes((b0, b1, b2, b3))

    def _parse_binary_response(self, data: bytes) -> ASRResult | None:
        if len(data) < 4:
            print("[ASR] Received malformed frame: too short for header")
            return None

        b0, b1, b2, _b3 = data[:4]
        protocol_version = (b0 >> 4) & 0x0F
        header_size_words = b0 & 0x0F
        msg_type = (b1 >> 4) & 0x0F
        flags = b1 & 0x0F
        serialization = (b2 >> 4) & 0x0F
        compression = b2 & 0x0F

        if protocol_version != PROTOCOL_VERSION:
            print(f"[ASR] Unsupported protocol version: {protocol_version}")
            return None

        header_size = header_size_words * 4
        if len(data) < header_size:
            print("[ASR] Received malformed frame: incomplete header")
            return None

        if msg_type == MSG_TYPE_SERVER_ERROR_RESPONSE:
            return self._parse_error_response(data, header_size)

        if msg_type != MSG_TYPE_FULL_SERVER_RESPONSE:
            print(f"[ASR] Ignoring unsupported message type: {msg_type}")
            return None

        if flags == FLAG_NO_SEQUENCE:
            if len(data) < header_size + 4:
                print("[ASR] Received malformed server response")
                return None
            sequence = 0
            payload_size = struct.unpack(">I", data[header_size : header_size + 4])[0]
            payload_start = header_size + 4
        else:
            if len(data) < header_size + 8:
                print("[ASR] Received malformed server response")
                return None
            sequence = struct.unpack(">i", data[header_size : header_size + 4])[0]
            payload_size = struct.unpack(">I", data[header_size + 4 : header_size + 8])[0]
            payload_start = header_size + 8

        payload_end = payload_start + payload_size
        if len(data) < payload_end:
            print("[ASR] Received truncated payload")
            return None

        payload = data[payload_start:payload_end]
        if compression == COMPRESSION_GZIP:
            payload = gzip.decompress(payload)

        if serialization != SERIALIZATION_JSON:
            print(f"[ASR] Unsupported serialization in response: {serialization}")
            return None

        raw = json.loads(payload.decode("utf-8"))
        segments = extract_segments(raw, flags, sequence)
        text = segments[-1].text if segments else ""
        is_final = segments[-1].is_final if segments else False
        return ASRResult(text=text, is_final=is_final, raw=raw, segments=segments)

    def _parse_error_response(self, data: bytes, header_size: int) -> ASRResult | None:
        if len(data) < header_size + 8:
            print("[ASR] Received malformed error response")
            return None

        error_code = struct.unpack(">I", data[header_size : header_size + 4])[0]
        error_size = struct.unpack(">I", data[header_size + 4 : header_size + 8])[0]
        error_start = header_size + 8
        error_end = error_start + error_size
        error_payload = data[error_start:error_end]

        try:
            error_text = error_payload.decode("utf-8", errors="replace")
        except Exception:
            error_text = repr(error_payload)

        print(f"[ASR ERROR] code={error_code}, message={error_text}")
        return None


def float32_to_pcm16_bytes(audio: np.ndarray) -> bytes:
    if audio.ndim == 2 and audio.shape[1] == 1:
        audio = audio[:, 0]

    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    return pcm16.tobytes()


def extract_segments(payload: dict[str, Any], flags: int, sequence: int) -> list[ASRSegment]:
    result = payload.get("result", {})
    segments: list[ASRSegment] = []

    force_final = flags == FLAG_NEG_SEQUENCE or sequence < 0
    if not isinstance(result, dict):
        return segments

    utterances = result.get("utterances")
    if isinstance(utterances, list) and utterances:
        for item in utterances:
            if not isinstance(item, dict):
                continue

            text = (item.get("text") or "").strip()
            if not text:
                continue

            segments.append(
                ASRSegment(
                    text=text,
                    is_final=bool(item.get("definite", False)) or force_final,
                    start_time=int(item.get("start_time") or 0),
                    end_time=int(item.get("end_time") or 0),
                )
            )
        return segments

    text = (result.get("text") or "").strip()
    if text:
        segments.append(ASRSegment(text=text, is_final=force_final))

    return segments


def build_default_asr_client() -> VolcASRClient:
    return VolcASRClient(sample_rate=settings.sample_rate)
