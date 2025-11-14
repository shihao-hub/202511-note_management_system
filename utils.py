import functools
import inspect
import os
import asyncio
from typing import List, Sequence, Callable, Annotated
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_scoped_session, AsyncSession
from openai import OpenAI, AsyncOpenAI
from nicegui import background_tasks, ui
from result import Result, Ok, Err

from models import AsyncSessionLocal, Attachment


class MiscUtils:
    pass


# region - template

class _Cleanup:
    """清理服务

    通过 asyncio. create_task 启动一个死循环任务，定期执行清理任务

    """

    def __init__(self, interval_seconds: int = 5 * 60):
        self.interval_seconds = interval_seconds
        self.is_running = False
        self.task = None

    async def start(self):
        """启动清理服务"""
        if self.is_running:
            logger.warning("清理服务已经在运行中")
            return

        logger.info(f"清理服务已启动，间隔: {self.interval_seconds} 秒")
        self.is_running = True
        self.task = asyncio.create_task(self._run_cleanup_loop())

    async def stop(self):
        """停止清理服务"""
        if not self.is_running:
            logger.info("清理服务早已停止")
            return

        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("清理服务已停止")

    async def _run_cleanup_loop(self):
        """运行清理循环"""
        while self.is_running:
            try:
                # [knowledge] 虽然事件循环全靠主循环，但是由于此处有 await asyncio.sleep(...)，所以不会长时间占用 cpu 即阻塞
                await asyncio.sleep(self.interval_seconds)
                await self._cleanup_expired_items()  # 不要刚启动就执行
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理过程中发生错误: {e}")
                await asyncio.sleep(60)  # 出错后等待 1 分钟再重试

    async def _get_items_to_delete(self, session) -> Sequence[Attachment]:
        five_minutes_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        stmt = select(Attachment).where(Attachment.note_id.is_(None) & (Attachment.created_at <= five_minutes_ago))
        result = await session.execute(stmt)
        items_to_delete = result.scalars().all()
        if not items_to_delete:
            logger.debug("没有找到需要清理的临时记录")
        return items_to_delete

    async def _delete_items(self, session):
        # 五分钟内被创建的不要删（但是这同样要求前端需要提示呢，否则有点难受）
        five_minutes_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        stmt = delete(Attachment).where(Attachment.note_id.is_(None) & (Attachment.created_at <= five_minutes_ago))
        await session.execute(stmt)
        await session.commit()

    async def _cleanup_expired_items(self):
        """清理临时项"""
        try:
            async with AsyncSessionLocal() as session:
                items_to_delete = await self._get_items_to_delete(session)

                if not items_to_delete:
                    return

                await self._delete_items(session)

                logger.info(f"成功删除 {len(items_to_delete)} 条临时记录")

                # 记录详细信息（可选）
                for item in items_to_delete:
                    logger.debug(f"删除记录: id={item.id}, name={item.filename}, "
                                 f"note_id={item.note_id}, temporary_uuid={item.temporary_uuid}")

        except Exception as e:
            logger.error(f"清理数据库时发生错误: {e}")
            raise

    async def cleanup_now(self) -> int:
        """立即执行一次清理，返回删除的记录数"""
        async with AsyncSessionLocal() as session:
            items_to_delete = await self._get_items_to_delete(session)

            if not items_to_delete:
                return 0

            await self._delete_items(session)

            return len(items_to_delete)


cleanup = _Cleanup()


class DeepSeekClient:
    def __init__(self, model: str = "deepseek-chat"):
        self.model = model

        self.api_key = os.environ.get("DEEPSEEK_API_KEY")

        if not self.api_key:
            raise ValueError("API key must be provided via argument or DEEPSEEK_API_KEY environment variable.")

        self.client: AsyncOpenAI | None = None

    async def __aenter__(self) -> "DeepSeekClient":
        self.client = AsyncOpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.close()
        return False

    async def ai_generate_title(self, content: str) -> Result[str, str]:
        try:
            system_content = """
            你是一位文本总结专家，你需要将用户发送的内容总结成一个简短的标题（不要超过 200 个字符）
            """
            params = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"{content}"},
                ],
                stream=False
            )
            response = await self.client.chat.completions.create(**params)  # messages 的格式会提示错误，所以选择这样处理
            text = response.choices[0].message.content.strip()
            logger.debug("[ai_generate_title] text: {}", text)
            return Ok(text)
        except Exception as e:
            logger.error(e)
            return Err(str(e))


# todo: 改成装饰器
class RateLimiter:
    """速率限制器"""

    def __init__(self, cooldown_seconds: float):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._last_call = datetime.min.replace(tzinfo=timezone.utc)

    def allow(self) -> bool:
        """返回是否允许执行操作"""
        now = datetime.now(timezone.utc)
        # 其实 now - last_call 大于 cooldown 即可（理解成技能冷却结束）
        logger.debug("now - self._last_call: {} s", (now - self._last_call).total_seconds())
        if self._last_call + self.cooldown <= now:
            self._last_call = now
            return True
        return False

    def time_until_next_allowed(self) -> float:
        """返回还需等待多少秒（用于提示）"""
        now = datetime.now(timezone.utc)
        next_time = self._last_call + self.cooldown
        return max(0.0, (next_time - now).total_seconds())


def show_about_dialog(
        title: str = "关于",
        app_name: str = "笔记管理系统",
        version: str = "v1.0.0",
        description: str = "一个基于 NiceGUI 构建的桌面级 Web 应用",
        author: str = "心悦卿兮",
        license_text: str = "MIT License",
        icon: str = "info",
        website: str | None = None,
):
    """显示统一风格的 关于 对话框

    由 通义千问 生成，还不错，很有参考价值

    """
    with ui.dialog() as dialog, ui.card().classes("p-6 min-w-[350px] max-w-[500px]"):
        # 标题栏
        with ui.row().classes("w-full items-center mb-2"):  # mb-4(margin bottom)
            ui.icon(icon, size="24px").classes("mr-2 text-primary")
            ui.label(title).classes("text-h6 font-bold")

        # 内容区
        ui.label(app_name).classes("text-h5 font-bold ")  # mt-2(margin top)
        ui.label(f"版本: {version}").classes("text-caption text-grey-7 dark:text-grey-4")
        ui.separator().classes("my-3")

        ui.label(description).classes("mt-2 leading-tight")

        # 元信息（作者、网站等）
        with ui.column().classes("mt-4 gap-1 text-sm"):
            if author:
                ui.label(f"作者: {author}")
            if website:
                with ui.link(website, website).classes("text-primary hover:underline") as link:
                    link.props("target=\"_blank\"")

                    if license_text:
                        ui.label(f"许可证: {license_text}")

        # 关闭按钮
        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("关闭", on_click=dialog.close).props("outline padding=\"sm\"")

    dialog.open()


def show_text_dialog(
        content: str,
        title: str = "文本框"
):
    dialog = ui.dialog()
    with dialog, ui.card().classes("p-6 min-w-[350px] max-w-[500px]"):
        with ui.row().classes("w-full items-center mb-2"):  # mb-4(margin bottom)
            ui.icon("mdi-card-text-outline", size="24px").classes("mr-2 text-primary")
            ui.label(title).classes("text-h6 font-bold")

        # [note] textarea 似乎无法轻易控制宽高
        # ui.textarea(value=content).classes("w-full mb-6").props("readonly outlined ")

        # ui.markdown(content).classes("w-full")

        # [step] ai: [pre-wrap pre-line](https://lxblog.com/qianwen/share?shareId=520cd53e-04aa-427e-a97b-f67449f8a7f5)
        ui.label(content).classes("w-full mb-6 border-2 border-dashed rounded-sm p-4").style("white-space: pre-wrap")

    dialog.open()


# endregion


# [2025-11-13] 装饰 save_note 时，出现了问题：
#              RuntimeError: The current slot cannot be determined because the slot stack for this task is empty.
#              This may happen if you try to create UI from a background task.
#              To fix this, enter the target slot explicitly using `with container_element:`.
#              已解决，大概是因为被装饰后找不到其所在容器了，所以需要新增第二个参数
def debounce(delay: float, parent: ui.element, preventing: Annotated[Callable, "防抖成功的执行函数"] = None):
    """通用防抖装饰器

    Details:
        1. 返回一个装饰器 decorator
        2. 返回的装饰器 decorator 将传入的参数 func 封装成 wrapper 再返回
        3. wrapper 会先判断任务是否存在，如果存在且未完成，则立刻终止。
           如果任务不存在，则创建任务，创建的任务会睡眠 delay s 再执行任务

    Digression:
        1. 注意区别防抖和节流，
           防抖：高频触发 → 只执行最后一次（等待静默期后执行）
           节流：高频触发 → 固定间隔执行一次（如每 0.5s 最多执行一次）

    Usage:
        @debounce(0.5, row, preventing=lambda: ui.notify("触发防抖机制，保存失败", type="negative"))

    """

    def decorator(func):
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"被装饰的函数 '{func.__name__}' 不是 async 函数。@debounce 仅支持 async def 定义的协程函数。")

        task = None

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal task
            if task is not None and not task.done():
                if preventing is not None:
                    preventing()
                task.cancel()

            async def debounced_call():
                await asyncio.sleep(delay)
                with parent:
                    await func(*args, **kwargs)

            task = asyncio.create_task(debounced_call())
            logger.debug("task type: {}, {}", type(task), task)

        return wrapper

    return decorator
