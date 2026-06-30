"""音频模型接口 —— 预留 TTS 接入点。

使用方式:
    1. 实现 AudioModel 的子类（如 VolcTTSModel, AzureTTSModel）
    2. 在 controller 中替换: controller.audio_model = MyTTSModel()
    3. controller 在收到 LLM 回答后会自动调用 synthesize() 并播放

当前 DummyAudioModel 为占位实现，不产生任何音频输出。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AudioModel(ABC):
    """TTS / 语音合成模型抽象接口。

    所有音频模型必须实现此接口。
    controller 通过此接口与音频模型解耦。
    """

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str = "") -> bytes:
        """将文本转换为音频字节。

        参数
        ----
        text : str
            要合成的文本（角色回答）。
        voice_id : str
            音色预设 ID，对应角色配置中的 voice_id 字段。

        返回
        ----
        bytes
            PCM 16-bit 单声道音频数据（或 WAV 格式）。
        """
        ...

    @abstractmethod
    async def list_voices(self) -> list[dict]:
        """返回可用的音色列表。

        返回格式:
            [{"voice_id": "...", "name": "...", "gender": "...", "description": "..."}, ...]
        """
        ...

    @property
    @abstractmethod
    def supported(self) -> bool:
        """是否加载了真实的音频模型实现。"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称（用于 UI 显示）。"""
        ...


class DummyAudioModel(AudioModel):
    """占位音频模型 —— 不产生任何音频输出。

    后续接入真实 TTS 服务时，替换为此类的子类即可。
    """

    @property
    def supported(self) -> bool:
        return False

    @property
    def model_name(self) -> str:
        return "未配置（占位模型）"

    async def synthesize(self, text: str, voice_id: str = "") -> bytes:
        raise NotImplementedError("音频模型未配置 —— 请实现 AudioModel 子类并注入 controller")

    async def list_voices(self) -> list[dict]:
        return []
