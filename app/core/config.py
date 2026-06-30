from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # ---- 应用 ----
    app_name: str = "CharacterSay"
    sample_rate: int = 16000
    channels: int = 1
    block_seconds: float = 0.5
    input_device: str | None = None
    debug: bool = True

    # ---- 火山引擎 ASR ----
    volc_app_id: str = ""
    volc_access_token: str = ""
    volc_ws_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

    # ---- LLM 配置 ----
    llm_api_key: str = ""
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_model: str = "doubao-seed-character-260628"

    # ---- 角色配置 ----
    active_character: str = "default"
    character_path: str = ""

    @property
    def resolved_character_path(self) -> Path:
        """返回角色的 JSON 存储目录（绝对路径）。"""
        if self.character_path:
            return Path(self.character_path)
        return _PROJECT_ROOT / "characters"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def save_to_env(cls, updates: dict) -> None:
        """将指定键值写入 .env 文件。已存在的键原位更新；新键追加到末尾。"""
        if not _ENV_PATH.exists():
            lines: list[str] = []
        else:
            lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

        updated_keys: set[str] = set()

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                lines[i] = f"{key}={updates[key]}\n"
                updated_keys.add(key)

        for key, value in updates.items():
            if key not in updated_keys:
                lines.append(f"{key}={value}\n")

        _ENV_PATH.write_text("".join(lines), encoding="utf-8")


settings = Settings()
