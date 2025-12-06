"""
ai 相关工具

"""
import asyncio
import os
import traceback
import functools
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypedDict, Dict, Union, List

from loguru import logger
from aiohttp import ClientSession, ClientTimeout
from result import Result, Ok, Err
from openai import AsyncOpenAI
from gradio_client import Client, handle_file, FileData

from .mediator import get_thread_pool_executor


class AIHandlerResponseTypedDict(TypedDict):
    source: str
    response: str
    raw: Dict | None  # 待定，暂不使用


class AsyncAIHandler(ABC):
    """设计模式 - 责任链模式（但是不够完整，目前够用了）"""

    def __init__(self):
        self._next_handler: Union["AsyncAIHandler", None] = None

    def set_next(self, handler: "AsyncAIHandler") -> "AsyncAIHandler":
        """设置在此之后的下一个处理器"""
        self._next_handler = handler
        return handler

    @abstractmethod
    async def handle(self, prompt: str) -> AIHandlerResponseTypedDict | None:
        """待实现的处理器执行逻辑"""
        # [2025-11-19] 目前默认都是非流式的
        # todo: 注意，这个责任链不够完善，因为 handle 默认还需要自己执行一些代码，不好


class LocalOllamaHandler(AsyncAIHandler):
    url = "http://localhost:11434/api/generate"
    timeout = 8  # 等待响应返回时间（因为非流式，而且本地 ollama 可能还存在响应时间）
    model = "qwen2.5:3b"
    stream = False

    async def handle(self, prompt: str) -> AIHandlerResponseTypedDict | None:
        try:
            logger.debug("[LocalOllamaHandler:handle] 🔄 尝试调用本地 Ollama (localhost:11434)...")
            payload = {"model": LocalOllamaHandler.model, "prompt": prompt, "stream": LocalOllamaHandler.stream}
            async with ClientSession() as session:
                async with session.post(
                        LocalOllamaHandler.url,
                        json=payload,
                        timeout=ClientTimeout(total=LocalOllamaHandler.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Ollama 返回的是单个 JSON 对象（非流式）
                        logger.debug("[LocalOllamaHandler:handle] ✅ 本地 Ollama 成功响应")
                        result: AIHandlerResponseTypedDict = {
                            "source": f"local-ollama/{LocalOllamaHandler.model}",
                            "response": data.get("response", ""),
                            "raw": data
                        }
                        return result
                    else:
                        text = await response.text()
                        logger.debug(
                            f"[LocalOllamaHandler:handle] ⚠️ 本地 Ollama 返回错误状态码 {response.status}: {text}")
        except Exception as e:
            logger.error(f"[LocalOllamaHandler:handle] ❌ 本地 Ollama 请求失败: {e}")

        if self._next_handler:
            return await self._next_handler.handle(prompt)

        return None


class DeepSeekHandler(AsyncAIHandler):
    async def handle(self, prompt: str) -> AIHandlerResponseTypedDict | None:
        try:
            logger.debug("[DeepSeekHandler:handle] 🔄 尝试调用 DeepSeek ...")
            async with DeepSeekClient() as client:
                text_result = await client.ask_ai(prompt)
            if text_result.is_err():
                raise Exception(text_result.err())
            text = text_result.unwrap()
            logger.debug("[DeepSeekHandler:handle] ✅ DeepSeek 成功响应")
            result: AIHandlerResponseTypedDict = {
                "source": f"deepseek/{client.model}",
                "response": text,
                "raw": None
            }
            return result
        except Exception as e:
            logger.error(f"[DeepSeekHandler:handle] ❌ DeepSeek 请求失败: {e}")
            logger.error(traceback.format_exc())

        if self._next_handler:
            return await self._next_handler.handle(prompt)

        return None


@functools.lru_cache(maxsize=None)
def build_ai_chain() -> AsyncAIHandler:
    """构建 ai 调用链"""
    # https://lxblog.com/qianwen/share?shareId=efdbbb73-3dbb-48a2-b3a4-46d26472965b
    handlers: List[AsyncAIHandler] = [
        LocalOllamaHandler(),
        DeepSeekHandler(),
    ]
    # 链接处理器
    for i in range(len(handlers) - 1):
        handlers[i].set_next(handlers[i + 1])
    return handlers[0]


class DeepSeekClient:
    def __init__(self, model: str = "deepseek-chat"):
        self.model = model

        # 使用懒加载，避免项目无法启动
        self._api_key: str | None = None
        self._client: AsyncOpenAI | None = None

    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not self._api_key:
                raise ValueError("API key must be provided via argument or DEEPSEEK_API_KEY environment variable.")
        return self._api_key

    @property
    def client(self):
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        return self._client

    async def __aenter__(self) -> "DeepSeekClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.close()
        return False

    async def ask_ai(self, user_content: str, *, system_content: str = "") -> Result[str, str]:
        try:
            params = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"{user_content}"},
                ],
                stream=False
            )
            response = await self.client.chat.completions.create(**params)  # messages 的格式会提示错误，所以选择这样处理
            text = response.choices[0].message.content.strip()
            # logger.debug("[_ai_generate] text: {}", text)
            return Ok(text)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def ai_generate_title(self, user_content: str) -> Result[str, str]:
        # 临时的
        system_content = """
        你是一位文本总结专家，你需要将用户发送的内容总结成一个简短的标题（不要超过 200 个字符）
        """
        return await self.ask_ai(user_content, system_content=system_content)

    async def ai_generate_text(self, user_content: str) -> Result[str, str]:
        # 临时的
        system_content = """
        你是一位文本总结专家，你需要将用户发送的内容总结成一个简短的标题（不要超过 200 个字符）
        """
        return await self.ask_ai(user_content, system_content=system_content)


async def audio_to_text_by_qwen3_asr(audio_file_path: str | Path):
    """音频转文字"""
    logger.debug("正在处理音频文件：{}", audio_file_path)
    url = "https://qwen-qwen3-asr-demo.ms.show/"
    client = Client(url)
    job = client.submit(
        audio_file=handle_file(audio_file_path),
        context="",
        language="auto",
        enable_itn=False,
        api_name="/asr_inference"
    )
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(get_thread_pool_executor(), lambda :job.result())
    logger.debug("api 返回结果：{}", result)
    return result[0] if result else ""
