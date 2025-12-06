"""
周期性异步清理数据库工具，主要由 AI 生成，功能上已满足需求，那么这就该是好功能（不要在意细节，多加点日志打印吧）

使用案例：

from nicegui import app

@app.on_startup
async def startup_event():
    await cleanup.start()

@app.on_shutdown
async def shutdown_event():
    await cleanup.stop()

"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Sequence

from loguru import logger
from sqlalchemy import select, delete

from services import Attachment
from models import AsyncSessionLocal


class _Cleanup:
    """清理服务

    通过 asyncio. create_task 启动一个死循环任务（但存在自动挂起），定期执行清理任务。

    注意，该类**没有启动新的线程**！仍然在事件循环中执行，不过稍微有点复杂（相对于启线程而言）

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

        logger.info(f"🧹 清理服务已启动，间隔: {self.interval_seconds} 秒")
        self.is_running = True
        self.task = asyncio.create_task(self._run_cleanup_loop())

    async def stop(self):
        """停止清理服务"""
        if not self.is_running:
            logger.info("⏹️ 清理服务早已停止")
            return

        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 清理服务已停止")

    async def _run_cleanup_loop(self):
        """运行清理循环"""
        while self.is_running:
            try:
                # [knowledge] 虽然事件循环全靠主循环，但是由于此处有 await asyncio.sleep(...)，所以不会长时间占用 cpu 即阻塞
                await asyncio.sleep(self.interval_seconds)
                await self._cleanup_expired_items()  # 先睡眠再执行，不要刚启动就执行
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
