"""

Model：数据结构、数据库交互、基础数据操作，不依赖其他层（最底层）
Service：业务逻辑、跨模型协调、事务处理，依赖 Model，不依赖 Controller/View

Controller：接收请求、调用 Service、准备响应数据，依赖 Service，能直接操作 View（不负责渲染细节，只处理逻辑并决定“展示什么”）
View：渲染界面/序列化响应，依赖 Controller 提供的数据（不包含业务逻辑，只负责展示和用户交互）

在目前的理解下，Controller 和 View 的界限不会太分明，所以我选择将二者耦合在一个文件中。

而且 View 不是必须拥有 Controller 的！（其实还是推荐的，建议加个规则，比如构建 UI 的代码超过 100 行之类的情况必须拆分了）

我的 Controller 的目的是将 View 直接调用 Service 的部分抽离出来（也没必要完全抽离出来），
主要遵循的还是骨架和血肉分离原则，以提高代码可读性和可定位性，尽量让骨架的定义位于一个函数中！


"""

from typing import Type, Self, TypeVar, Dict

from loguru import logger
from nicegui import ui

from services import NoteService

# region - template

V = TypeVar("V", bound="View")
C = TypeVar("C", bound="Controller")


class Controller[V]:
    """协调 Model 和 View，处理用户输入"""

    def __init__(self, view: V):
        self.view = view


class View[C]:
    """负责用户界面展示"""
    controller_class: Type[C]
    _controller: C
    _query_params: Dict

    @property
    def controller(self) -> C:
        if not hasattr(self, "controller_class"):
            exc = NotImplementedError("controller_class has not been initialized")
            logger.error(exc)
            raise exc
        if not hasattr(self, "_controller") or self._controller is None:
            self._controller = self.controller_class(self)
        return self._controller

    @property
    def query_params(self) -> Dict:
        """nicegui 的查询参数"""
        if not hasattr(self, "_query_params") or self._query_params is None:
            exc = NotImplementedError("_query_params has not been initialized")
            logger.error(exc)
            raise exc
        return self._query_params

    @classmethod
    async def create(cls, query_params: Dict | None = None):
        """异步工厂方法"""
        self = cls()
        setattr(self, "_query_params", query_params)
        await self._initialize()  # self._build_ui()
        return self

    async def _initialize(self):
        """初始化 UI 骨架"""
        raise NotImplementedError


"""
使用示例：
class ExampleView(View["ExampleController"]):
    controller_class = ExampleController
    async def _initialize(self) -> None:
        pass

class ExampleController(Controller["ExampleView"]):
    pass
"""


# endregion


async def delete_note(note_id: int, delay: bool = True, notify_from: str = None):
    async def confirm():
        async with NoteService() as service:
            result = await service.delete(note_id)
            if result.is_ok():
                dialog.close()
                # 删除笔记确实需要强制返回，除非调用 navigate 传查询参数（延迟 ui.timer 不行），让 page 来弹通知，但是那太搞了吧...
                ui.notify(f"删除笔记成功！", type="positive")
                if delay:
                    # 为什么这个延迟可以不让页面白屏？不是延迟才去访问吗？那么访问的时候才会渲染那个页面啊...
                    ui.timer(0.8, lambda: ui.navigate.to("/"), once=True)
                else:
                    ui.timer(0.3, lambda: ui.navigate.to("/"), once=True)
                    # ui.navigate.to("/")

                # if notify_from in ["get_note__delete", "home__delete"]:
                #     ui.navigate.to(f"/?notify_from={notify_from}")
                # else:
                #     ui.navigate.to("/")
            else:
                ui.notify(f"删除笔记 {note_id} 失败，原因：{result.err()}", type="negative")

    # ┌─────────────────────┐
    # │   Are you sure?     │
    # ├─────────────────────┤
    # │ [confirm]  [cancel] │
    # └─────────────────────┘
    dialog = ui.dialog()
    with dialog, ui.card().classes("rounded-xl shadow-lg border border-gray-200 p-5 max-w-sm"):
        with ui.column().classes("items-center text-center gap-3"):
            with ui.row().classes("items-center p-4"):
                ui.icon("warning_amber", size="2rem").classes("text-yellow-500")
                ui.label("确认删除").classes("text-lg font-semibold text-gray-800")
            ui.label("此操作不可恢复，请确认是否删除该笔记？").classes("text-gray-600 text-sm")
            with ui.row().classes("gap-3 mt-4"):
                confirm_btn = ui.button("确认", icon="delete", on_click=confirm)
                confirm_btn.props("flat dense color=red").classes("px-4")
                cancel_btn = ui.button("取消", icon="close", on_click=dialog.close)
                cancel_btn.props("flat color=grey").classes("px-4")

    dialog.open()
