"""LLM 客户端 —— 支持角色扮演的流式对话。"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import settings


class LLMClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self._model = settings.llm_model

    @property
    def model(self) -> str:
        return self._model

    def update_config(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    # ------------------------------------------------------------------
    # 角色对话（流式）
    # ------------------------------------------------------------------

    async def answer_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        history: list[dict[str, str]] | None = None,
    ):
        """流式生成角色回复，逐 token yield。

        参数
        ----
        user_message : str
            用户说的话（ASR 识别的文本）。
        system_prompt : str
            角色 system prompt（由 CharacterManager 构建）。
        history : list[dict] | None
            历史对话 [{"q": "...", "a": "..."}, ...]。
        """
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

        if history:
            for h in history[-5:]:
                messages.append({"role": "user", "content": h.get("q", "")})
                messages.append({"role": "assistant", "content": h.get("a", "")})

        messages.append({"role": "user", "content": user_message})

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.8,       # 角色扮演需要略高的创造性
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ------------------------------------------------------------------
    # 非流式对话
    # ------------------------------------------------------------------

    async def answer(
        self,
        user_message: str,
        system_prompt: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """非流式生成角色回复。"""
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            for h in history[-5:]:
                messages.append({"role": "user", "content": h.get("q", "")})
                messages.append({"role": "assistant", "content": h.get("a", "")})
        messages.append({"role": "user", "content": user_message})

        return await self._chat_with_messages(messages)

    # ------------------------------------------------------------------
    # 通用对话（配置窗口测试用）
    # ------------------------------------------------------------------

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "你是一个友好、有帮助的 AI 助手。",
    ) -> str:
        """通用对话接口（非流式）。用于配置窗口的模型测试。"""
        return await self._chat_with_messages([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "你是一个友好、有帮助的 AI 助手。",
    ):
        """通用对话接口（流式）。"""
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.8,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ------------------------------------------------------------------
    # 底层
    # ------------------------------------------------------------------

    async def _chat_with_messages(self, messages: list[dict]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.8,
        )
        return (response.choices[0].message.content or "").strip()
