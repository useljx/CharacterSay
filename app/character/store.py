"""角色持久化存储 —— 基于 JSON 文件，带内存缓存 + 延迟写入。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.character.models import Character
from app.core.config import settings


class CharacterStore:
    """角色的 JSON 文件存储层。

    - 内存缓存避免频繁磁盘 IO
    - 延迟写入（防抖 1.5s）合并多次修改
    - 原子写入（先写 tmp 再替换）防止文件损坏
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir is None:
            storage_dir = settings.resolved_character_path
        self._dir = Path(storage_dir)
        self._file = self._dir / "characters.json"
        self._cache: list[dict] | None = None
        self._dirty = False
        self._debounce_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> list[dict]:
        if self._cache is None:
            self._dir.mkdir(parents=True, exist_ok=True)
            if self._file.exists():
                with self._file.open("r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            else:
                self._cache = []
            self._dirty = False
        return self._cache

    def _persist_sync(self) -> None:
        if not self._dirty or self._cache is None:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)
        tmp.replace(self._file)
        self._dirty = False

    def _persist(self) -> None:
        self._dirty = True
        self._schedule_debounce()

    def _schedule_debounce(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            return

        async def _debounce():
            await asyncio.sleep(1.5)
            self._persist_sync()

        try:
            loop = asyncio.get_running_loop()
            self._debounce_task = loop.create_task(_debounce())
        except RuntimeError:
            self._persist_sync()

    def flush(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            self._debounce_task = None
        self._persist_sync()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[Character]:
        return [Character.from_dict(r) for r in self._ensure_loaded()]

    def get_by_id(self, char_id: str) -> Character | None:
        for r in self._ensure_loaded():
            if r.get("char_id") == char_id:
                return Character.from_dict(r)
        return None

    def get_by_name(self, name: str) -> Character | None:
        for r in self._ensure_loaded():
            if r.get("name") == name:
                return Character.from_dict(r)
        return None

    def add(self, character: Character) -> None:
        records = self._ensure_loaded()
        records.append(character.to_dict())
        self._persist()

    def update(self, character: Character) -> None:
        character.touch()
        records = self._ensure_loaded()
        for i, r in enumerate(records):
            if r.get("char_id") == character.char_id:
                records[i] = character.to_dict()
                self._persist()
                return
        raise KeyError(f"char_id={character.char_id} 不存在，无法更新")

    def delete(self, char_id: str) -> None:
        records = self._ensure_loaded()
        new_records = [r for r in records if r.get("char_id") != char_id]
        if len(new_records) != len(records):
            self._cache = new_records
            self._persist()

    def count(self) -> int:
        return len(self._ensure_loaded())
