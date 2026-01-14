import asyncio
import functools
import threading
from collections import namedtuple
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Any, TypeVar, List, Dict

from unqlite import UnQLite, Collection, Cursor
from async_lru import alru_cache
from nicegui import ui
from watchfiles import awatch

from utils import get_thread_pool_executor, asyncify
from log import logger

class AsyncUnQLite:
    DEFAULT_DB_PATH = "memo.unqlite"

    # [unqlite](https://github.com/symisc/unqlite)
    # todo: 确定一下这个类的可行性

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._local = threading.local()  # 每个线程独立实例（这个方式也不需要锁了）
        self._executor = get_thread_pool_executor(thread_name_prefix="AsyncUnQLite")

    def _get_db(self) -> UnQLite:
        """获取当前线程的 UnQLite 实例（懒加载）"""
        if not hasattr(self._local, "db"):
            self._local.db = UnQLite(self.db_path)
        return self._local.db

    async def collection_store(self, collection_name: str, records: List[Dict]) -> None:
        """向集合插入记录列表"""

        def _sync_store():
            db = self._get_db()
            col = db.collection(collection_name)
            if not col.exists():
                col.create()
            col.store(records)

        await asyncify(_sync_store)

    async def collection_fetch(self, collection_name: str, record_id: int) -> Dict | None:
        """按 ID 获取单条记录（ID 从 0 开始）"""

        def _sync_fetch():
            db = self._get_db()
            col = db.collection(collection_name)
            if not col.exists():
                return None
            try:
                return col.fetch(record_id)
            except IndexError:
                return None

        return await asyncify(_sync_fetch)

    async def collection_all(self, collection_name: str) -> List[Dict]:
        """获取集合所有记录"""

        def _sync_all():
            db = self._get_db()
            col = db.collection(collection_name)
            if not col.exists():
                return []
            return col.all()

        return await asyncify(_sync_all)

    async def collection_filter(self, collection_name: str, predicate: Callable[[Dict], bool]) -> List[Dict]:
        """按条件过滤（注意：predicate 必须是 pickleable 或在线程内定义）"""

        def _sync_filter():
            db = self._get_db()
            col = db.collection(collection_name)
            if not col.exists():
                return []
            return [doc for doc in col.all() if predicate(doc)]

        return await asyncify(_sync_filter)

    async def close(self):
        """关闭线程池（可选）"""
        self._executor.shutdown(wait=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@asynccontextmanager
async def get_unqlite_db(db_path: str = AsyncUnQLite.DEFAULT_DB_PATH):
    db = await asyncify(lambda: UnQLite(db_path))
    yield db
    await asyncify(db.commit)
    await asyncify(db.close)


# endregion


@ui.page("/memo/index", title="备忘录")
async def page():
    ui.add_css("""
    <style>
    .memo-scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
    }
    
    .memo-scrollbar-hide::-webkit-scrollbar {
    display: none;
    }
    </style>
    """)

    # [QItem 组件体系](https://www.qianwen.com/share?shareId=7f567d82-bd1a-4eef-858f-46889caa3bab)
    # todo: 我想实现这个 card 的拖拽效果
    with ui.card().classes("mx-auto rounded-xl m-0 p-0 w-96 gap-y-0"):
        with ui.row().classes("w-full items-center justify-between bg-blue-400 rounded-t-xl py-0.5"):
            with ui.row().classes("items-center text-base gap-x-1 pl-2 py-1"):
                with ui.icon("folder_open", color="white", size="18px").classes("cursor-pointer"):
                    with ui.menu():
                        # ui.menu_item("上一页")
                        # ui.separator()
                        # ui.menu_item("下一页")
                        max_page = 5
                        if max_page <= 5:
                            ui.pagination(1, max_page, direction_links=False).props("")  # color=teal
                        else:
                            ui.pagination(1, max_page, direction_links=True).props("input")  # color=teal
                    with ui.context_menu():
                        ui.menu_item("主页", on_click=lambda: ui.navigate.to("/"))

                ui.label("备忘录").classes("text-white")
            with ui.button(icon="add").classes("rounded-t-xl pr-2").props("flat dense color=white"):
                ui.tooltip("新增备忘")  # .classes("bg-green-500 text-white")

        # overflow-y-auto overflow-x-hidden memo-scrollbar-hide
        with ui.list().classes("w-full").props("separator"):
            def create_item(title, content):
                with ui.item().classes("w-full"):
                    with ui.item_section():  # 无 props，主内容区
                        main = title
                        sub = content

                        ui.item_label(main).classes("truncate text-ellipsis").tooltip(main)
                        ui.item_label(sub).props("caption").classes("truncate text-ellipsis").tooltip(sub)
                    with ui.item_section().props("side"):
                        with ui.fab("more_vert").props("padding=4px flat"):
                            # todo: 编辑 -  查 改，删除 - 删
                            ui.fab_action("edit_square").props("flat").props("padding=4px").tooltip("编辑")
                            # todo: 能不能做到从 ui.list 中直接移除元素，不要重新构建 ui.list？
                            ui.fab_action("delete").props("flat").props("padding=4px").tooltip("删除")

            # todo: 实现分页效果，一页最多 8 个！
            async with get_unqlite_db() as db:
                co: Collection = await asyncify(db.collection, "memo2")
                await asyncify(co.create)
                memos: List[Dict] = await asyncify(co.all)
                for memo in memos:
                    create_item(memo.get("title", ""), memo.get("content", ""))

    # todo: nicegui 可以做到 sync 和 async 混杂编程，这不太好吧？
    #       猜测除了页面渲染，其他诸如回调都类似 fastapi 可以做到混杂编程
    #       而且页面渲染只要骨架搭建完毕，都不要担心阻塞问题？（猜测的）

    # mermaid_config = {
    #     'theme': 'default',  # 或 'dark', 'forest' 等
    #     'flowchart': {
    #         'useMaxWidth': False,  # 关键：允许图表超过默认最大宽度
    #         'curve': 'basis',  # 可选：更改连线样式
    #         'nodeSpacing': 50,  # 增加节点间距
    #         'rankSpacing': 50  # 增加层级间距
    #     },
    #     'fontSize': 16  # 增大字体大小
    # }

    # todo: 存放在一个 overflow-auto 的盒子中比较好，mermaid 需要 config 配置，classes 做不到
    # ui.mermaid("""
    # graph LR
    # A[数据库/日志] --> B{后端 API}
    # B -->|用 pandas 计算| C[JSON 数据]
    # C --> D[前端 Vue/React]
    # D -->|用 ECharts 渲染| E[交互式图表]
    # """, config=mermaid_config)

    # async with AsyncUnQLite() as db:
    #     # 插入数据
    #     await db.collection_store("users", [
    #         {"name": "Alice", "age": 25},
    #         {"name": "Bob", "age": 30}
    #     ])
    #
    #     # 获取所有
    #     all_users = await db.collection_all("users")
    #     print("All users:", all_users)
    #
    #     # 获取单条
    #     user0 = await db.collection_fetch("users", 0)
    #     print("User[0]:", user0)
    #
    #     # 过滤（注意：lambda 在某些环境下可能无法 pickle，建议用函数）
    #     def is_adult(u):
    #         return u.get("age", 0) >= 18
    #
    #     adults = await db.collection_filter("users", is_adult)
    #     print("Adults:", adults)

    # async with get_unqlite_db() as db:
    #     memo = await asyncify(db.collection, "memo")  # type:Collection
    #     await asyncify(memo.create)
    #     await asyncify(memo.delete, 0)
    #     memo_id = await asyncify(memo.store, {
    #         "title": "考核指标考核指标考核指标考核指标考核指标考核指标考核指标考核指标考核指标",
    #         "content": "20:13 【选题策划会】20:13 【选题策划会】20:13 【选题策划会】20:13 【选题策划会】20:13 "
    #     })
    #     print(memo_id)
    #     print(await asyncify(memo.all))
