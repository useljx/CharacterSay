"""角色管理器 —— 管理当前激活角色和 LLM prompt 构建。"""

from __future__ import annotations

from pathlib import Path

from app.character.models import Character
from app.character.store import CharacterStore
from app.core.config import settings


class CharacterManager:
    """角色管理器。

    - 从存储中加载角色列表
    - 管理当前激活的角色
    - 为 LLM 构建角色 system prompt
    """

    def __init__(self, store: CharacterStore | None = None) -> None:
        self._store = store or CharacterStore()
        self._active: Character | None = None

    # ------------------------------------------------------------------
    # CRUD 代理
    # ------------------------------------------------------------------

    @property
    def store(self) -> CharacterStore:
        return self._store

    def list_all(self) -> list[Character]:
        return self._store.list_all()

    def get(self, char_id: str) -> Character | None:
        return self._store.get_by_id(char_id)

    def add(self, character: Character) -> None:
        self._store.add(character)

    def update(self, character: Character) -> None:
        self._store.update(character)

    def delete(self, char_id: str) -> None:
        if self._active and self._active.char_id == char_id:
            self._active = None
        self._store.delete(char_id)

    # ------------------------------------------------------------------
    # 激活角色
    # ------------------------------------------------------------------

    @property
    def active(self) -> Character | None:
        return self._active

    def set_active(self, char_id: str) -> Character:
        """设置当前激活角色。返回激活的角色对象。"""
        char = self._store.get_by_id(char_id)
        if char is None:
            raise KeyError(f"角色不存在: {char_id}")
        self._active = char
        return char

    def set_active_by_name(self, name: str) -> Character | None:
        """按名称设置激活角色。找不到返回 None。"""
        char = self._store.get_by_name(name)
        if char:
            self._active = char
        return char

    def auto_activate(self) -> Character | None:
        """自动激活角色:
        1. 优先按 .env 中的 ACTIVE_CHARACTER 加载
        2. 否则激活列表中的第一个
        3. 列表为空则返回 None
        """
        all_chars = self.list_all()
        if not all_chars:
            return None

        target = settings.active_character
        if target:
            for c in all_chars:
                if c.name == target or c.char_id == target:
                    self._active = c
                    return c

        # 回退到第一个
        self._active = all_chars[0]
        return self._active

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def build_system_prompt(self, character: Character | None = None) -> str:
        """根据角色人设构建 LLM system prompt。

        不指定 character 则使用当前激活角色。
        """
        char = character or self._active
        if char is None:
            return "你是一个友好的 AI 对话助手。请用自然、亲切的语气与用户交流。"

        parts: list[str] = [
            f"你现在扮演【{char.name}】。请完全以这个角色的身份与用户对话。",
            f"角色性格：{char.persona}" if char.persona.strip() else "",
            f"背景故事：{char.backstory}" if char.backstory.strip() else "",
            f"说话风格：{char.speaking_style}" if char.speaking_style.strip() else "",
            "",
            "重要规则：",
            "- 始终保持角色一致，不要跳出角色。",
            "- 不要提及你是一个 AI 模型。",
            "- 回答简洁自然，控制在 30-60 秒口述长度。",
            "- 根据角色性格自然地使用语气词和表情。",
            "- 如果用户说的话与角色世界无关，以角色的方式自然回应即可。",
        ]
        return "\n".join(p for p in parts if p)

    def build_greeting(self, character: Character | None = None) -> str:
        """获取角色的招呼语。"""
        char = character or self._active
        if char and char.greeting.strip():
            return char.greeting
        return "你好！很高兴和你聊天。"

    # ------------------------------------------------------------------
    # 导入/导出
    # ------------------------------------------------------------------

    def import_from_json(self, file_path: str | Path) -> int:
        """从 JSON 文件批量导入角色。返回导入数量。"""
        import json
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        data = json.loads(p.read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else [data]
        count = 0
        for item in entries:
            char = Character.from_dict(item)
            existing = self._store.get_by_name(char.name)
            if existing:
                char.char_id = existing.char_id  # 同名视为更新
                self._store.update(char)
            else:
                self._store.add(char)
            count += 1
        self._store.flush()
        return count

    def export_to_file(self, file_path: str | Path) -> int:
        """将当前所有角色导出到 JSON 文件。"""
        import json
        data = [c.to_dict() for c in self.list_all()]
        Path(file_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return len(data)
