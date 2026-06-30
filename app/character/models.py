"""角色数据模型。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Character:
    """角色定义 —— 一个可对话的 AI 角色。"""

    name: str                                    # 角色名称
    persona: str = ""                            # 核心性格描述
    backstory: str = ""                          # 背景故事
    speaking_style: str = ""                     # 说话风格（语气、口头禅等）
    voice_id: str = ""                           # TTS 音色 ID（未来使用）
    avatar_emoji: str = ""                         # 悬浮窗展示的标识
    greeting: str = "你好！很高兴和你聊天。"       # 招呼语

    char_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self) -> None:
        """更新 updated_at 时间戳。"""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "char_id": self.char_id,
            "name": self.name,
            "persona": self.persona,
            "backstory": self.backstory,
            "speaking_style": self.speaking_style,
            "voice_id": self.voice_id,
            "avatar_emoji": self.avatar_emoji,
            "greeting": self.greeting,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Character:
        return cls(
            char_id=d.get("char_id", uuid.uuid4().hex[:12]),
            name=d.get("name", "未命名角色"),
            persona=d.get("persona", ""),
            backstory=d.get("backstory", ""),
            speaking_style=d.get("speaking_style", ""),
            voice_id=d.get("voice_id", ""),
            avatar_emoji=d.get("avatar_emoji", ""),
            greeting=d.get("greeting", "你好！"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )
