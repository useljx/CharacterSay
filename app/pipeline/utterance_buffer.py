"""话语缓冲器 —— 检测用户说完一段话后触发 LLM 回复。

与面试版 QuestionBuffer 逻辑相同，但参数针对聊天场景调整：
- 更短的静默阈值（对话中停顿更短）
- 更低的字数阈值（聊天可能只有几个字）
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class UtteranceBuffer:
    """基于静默检测的话语缓冲器。

    当用户连续说话后停顿超过 silence_seconds 时，
    将当前缓冲中的文本作为一个完整话语触发回复。
    """

    silence_seconds: float = 0.6
    min_chars: int = 4
    max_chars: int = 300

    # 内部状态
    finals: list[str] = field(default_factory=list)
    last_final_at: float = 0.0
    last_emit_at: float = 0.0

    def on_final(self, text: str) -> None:
        """接收 ASR final 文本，追加到缓冲。"""
        text = self._normalize(text)
        if not text:
            return
        self.finals.append(text)
        self.last_final_at = time.monotonic()

    def should_emit(self) -> bool:
        """判断是否应该触发话语输出。"""
        if not self.finals:
            return False
        if self.last_final_at <= self.last_emit_at:
            return False
        if time.monotonic() - self.last_final_at < self.silence_seconds:
            return False
        utterance = self.build_utterance()
        if len(utterance) < self.min_chars:
            return False
        return True

    def pop_utterance(self) -> str:
        """取出当前话语并清空缓冲。"""
        utterance = self.build_utterance()
        self.finals.clear()
        self.last_emit_at = time.monotonic()
        return utterance

    def build_utterance(self) -> str:
        """拼接并清洗当前缓冲中的所有 final 片段。"""
        text = "".join(self.finals)
        text = self._normalize(text)
        text = self._strip_fillers(text)
        return text[-self.max_chars:]

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().split())

    @staticmethod
    def _strip_fillers(text: str) -> str:
        """移除常见口头语。"""
        fillers = [
            "嗯", "啊", "额", "呃", "那个", "就是", "然后",
            "所以说", "你知道吧", "内个",
        ]
        for f in fillers:
            text = text.replace(f, "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
