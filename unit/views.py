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
import functools
import os
import re
import shutil
import sys
import tempfile
from abc import ABC, abstractmethod, ABCMeta
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Type, Self, TypeVar, Dict, Generic, get_args, get_origin, ForwardRef

import numpy as np
import aiofiles
import pandas as pd
import matplotlib.pyplot as plt
import pyperclip
from nicegui import ui, run
from nicegui.events import UploadEventArguments

from utils import extract_urls, refresh_page, DeepSeekClient, go_main, go_add_note, is_valid_filename, go_get_note
from utils.tkinter_ui import create_tk_root, import_filedialog, import_messagebox
from services import AttachmentService, NoteService, UserConfigService
from models import NoteTypeMaskedEnum, Attachment
from settings import dynamic_settings
from components import LoadingOverlay, AboutDialog, TextDialog
from log import logger

# region - template

V = TypeVar("V", bound="View")
C = TypeVar("C", bound="Controller")


# [note] 此处 Controller 暂时只是作为 View 回调等函数的存放处，实际上 MVC 的 VC 交互绝非如此（至少目前这样使用对我而言够了）
# [note] 不得不说，models services views controllers MSVC 太好用了！

# fixme: [2025-12-02] 实践发现，由于目前是将回调函数（协程）放在 C 中，那么回调共享 C 或 V 的 self.xxx 时，会出问题的吧？
#                     ui.page 中 C V 会初始化，所以不同 ui.page 中不需要考虑共享的问题，但是同一个 ui.page 的不同协程中
#                     必须考虑这种场景... 这叫做`跨事件/协程共享`，要考虑共享的值是否是线程/协程安全的！ThreadLocal/ContextVar
# 题外话，不得不说 Java 新版本确实成熟，但是你能保证你去的项目组是新版本 Java 吗？
# Python 还是太尴尬了，高性能、高并发等领域（项目体量变大）容易出问题，Go 天生适合高并发领域，
# 不得不说，Python + Go 确实是不错的技术搭配，再深入一点就是 C++/Rust，妙哉，Python 适合作为
# 发散性桥梁。至于 Java，jdk17 jdk21 似乎确实不错，但是如果选择 Python 就不可能选择 Java！
# [note]
# 总结：
#       Python 保底，Go 进阶，C++/Rust 再进阶！（我未来的路）
#       Java 一路走到底，多和框架（Spring等）打交道！（我舍弃的路）
#       html css js 打基础，Vue React Vite 等工具来开发！（我兼职的路）
#       C/C++ 是计算机的基础，可以进行任何方向的开发（游戏、嵌入式等），但是不同方向之间其实都是有生殖隔离的！（我向往的路）
# 重要的参考链接：https://www.qianwen.com/chat/589a93ded3f747eda62f506b634e44cb（未来要反复阅读，不要忘了！）

class Controller[V]:
    """协调 Model 和 View，处理用户输入"""

    def __init__(self, view: V):
        self.view = view


class ViewMeta(ABCMeta):
    """视图通过元类解决 controller_class 自动初始化的问题，但是失败了，以后再研究（此处代码为 ai 生成）

    Python 元类：https://liaoxuefeng.com/books/python/oop-adv/meta-class/index.html

    """

    def __new__(mcs, name, bases, namespace, /, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # 安全获取 __orig_bases__
        orig_bases = getattr(cls, "__orig_bases__", None)
        if orig_bases is None:
            logger.debug("orig_bases is None")
            return cls

        # 查找 View[...] 中的泛型参数
        controller_type = None
        for base in orig_bases:
            origin = get_origin(base)
            logger.debug("origin: {}", origin)
            # 判断 origin 是否是 View 类：通过名称和模块
            if (
                    origin is not None
                    and getattr(origin, "__name__", None) == "View"
                    and getattr(origin, "__module__", None) == __name__  # 当前模块
            ):
                args = get_args(base)
                if args:
                    controller_type = args[0]
                    break

        if controller_type is None:
            raise TypeError(
                f"Class {name} inherits from View but does not specify a controller type (e.g., View[MyController])")

        # 解析 ForwardRef 或字符串引用
        if isinstance(controller_type, str):
            # 获取定义该类的模块的全局命名空间
            module_name = cls.__module__
            if module_name == "__main__":
                globalns = globals()
            else:
                globalns = sys.modules[module_name].__dict__

            controller_type = globalns.get(controller_type)
            if controller_type is None:
                raise NameError(f"Controller type '{controller_type}' not found in module {module_name}")
        elif isinstance(controller_type, ForwardRef):
            module_name = cls.__module__
            globalns = sys.modules[module_name].__dict__ if module_name != '__main__' else globals()
            # Python 3.10+ 使用 _evaluate；兼容旧版本可加判断
            controller_type = controller_type._evaluate(globalns=globalns, localns=None, recursive_guard=frozenset())

        if not isinstance(controller_type, type):
            raise TypeError(f"Resolved controller type must be a class, got {controller_type}")

        # 自动设置 controller_class
        cls.controller_class = controller_type
        logger.debug("controller_type: {}", controller_type)

        return cls


class View[C](ABC):
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
        if query_params:
            setattr(self, "_query_params", query_params)
        await self._pre_initialize()
        await self._initialize()
        await self._post_initialize()
        return self

    async def _pre_initialize(self):
        """初始化 UI 骨架前的设置"""
        # 推荐：变量初始化、ui.add_css、ui.add_head_html、ui.add_body_html，足矣
        # 类似事件监听等，不建议放在此处，最好和关联组件挨在一起

    async def _post_initialize(self):
        """初始化 UI 骨架后的设置"""
        # 最初打算用来执行 ui.add_head_html、ui.add_body_html 等函数的，但是实践发现，
        # 这两个函数最好在任何 await 操作之前执行，否则可能会添加失败，因为页面已经渲染出来了，
        # 而 nicegui 的组件似乎是通过 javascript 直接操作 dom 渲染出来的，所以没事

        # 现在打算用来存放部分访问数据库并刷新数据的逻辑

    @abstractmethod
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
    
在 View 子类的 _initialize 中构建 UI 骨架

在 Controller 子类中定义 UI 骨架涉及的回调和数据渲染与刷新等操作

"""


def sort_easyocr_results(results, y_threshold=15):
    """
    将 EasyOCR 的结果按视觉行顺序排序（从上到下，每行从左到右）

    :param results: EasyOCR 返回的列表，每个元素为 (bbox, text, prob)
                    bbox = [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    :param y_threshold: 判断是否属于同一行的最大 y 差值（像素），根据图像调整
    :return: 按行拼接的字符串列表，如 ["第一行文本", "第二行文本", ...]
    """
    if not results:
        return []

    # 提取每块文本的：平均 y（行位置）、最小 x（列位置）、文本内容
    blocks = []
    for bbox, text, _ in results:
        # 计算 y_center（四个点 y 的平均值）
        y_coords = [point[1] for point in bbox]
        x_coords = [point[0] for point in bbox]
        y_center = sum(y_coords) / len(y_coords)
        x_min = min(x_coords)
        blocks.append((y_center, x_min, text))

    # 按 y_center 从小到大排序（从上到下）
    blocks.sort(key=lambda b: b[0])

    # 按 y 分组（相近 y 视为同一行）
    lines = []
    current_line = []
    last_y = blocks[0][0]

    for y, x, text in blocks:
        if abs(y - last_y) <= y_threshold:
            current_line.append((x, text))
        else:
            # 结束当前行
            current_line.sort(key=lambda t: t[0])  # 按 x 从左到右
            line_text = " ".join(t[1] for t in current_line)
            lines.append(line_text)
            # 开始新行
            current_line = [(x, text)]
            last_y = y

    # 处理最后一行
    if current_line:
        current_line.sort(key=lambda t: t[0])
        line_text = " ".join(t[1] for t in current_line)
        lines.append(line_text)

    return lines


def easyocr_read_file(filepath: str, langs=None):
    """局部函数或 lambda 函数等无法被 pickle 序列化，即不能跨进程，所以提取出来作为模块级顶层全局函数"""
    import easyocr
    if langs is None:
        langs = ["ch_sim", "en"]
    reader = easyocr.Reader(langs)
    logger.debug("filepath: {}", filepath)
    return reader.readtext(filepath)


# endregion

# region - build_softmenu


def build_softmenu(icon="mdi-note", size="16px", color="blue-600") -> ui.button:
    """构建软件菜单

    非通用，主要是软件 icon 处支持点击显示菜单

    """

    # [step] 搜索 ui.icon 的资料 -> 参考 Quasar 的图标文档来查看所有可用的图标（https://quasar.dev/vue-components/icon -> https://pictogrammers.com/library/mdi/icon/note/）
    # [step] ai: nicegui 如何设置 ui.label 和 ui.icon 的大小和颜色？
    #        an: https://lxblog.com/qianwen/share?shareId=5e5d87f2-45af-4b86-80ad-aaf02de189dd

    async def on_settings_click():
        dialog = ui.dialog(value=True)
        async with UserConfigService() as service:
            config = await service._get_user_config()  # test
            profile = config.profile

        # todo: 确定一下这种固定 px 是否存在问题，比如不同人的电脑！
        with dialog, ui.card().classes("min-w-[350px] max-w-[500px]"):
            json_content = {
                "array": [1, 2, 3],
                "boolean": True,
                "color": "#82b92c",
                None: None,
                "number": 123,
                "object": {
                    "a": "b",
                    "c": "d",
                },
                "time": 1575599819000,
                "string": "Hello World",
            }
            # test
            json_content = profile
            editor = ui.json_editor({"content": {"json": json_content}},
                                    on_select=None,
                                    on_change=None)
            editor.classes("w-full")

            editor.props(f'locale="zh-CN"')

    menu_button = ui.button(icon=icon).props(f"flat dense size={size} color={color}")
    with menu_button:
        with ui.menu(), ui.list():
            ui.menu_item("主页", on_click=lambda: ui.navigate.to("/"))

            ui.separator()
            ui.menu_item("关于", auto_close=False,
                         on_click=lambda: AboutDialog(
                             app_name="笔记管理系统",
                             version=dynamic_settings.version,
                             author="心悦卿兮",
                             description="一个基于 NiceGUI 构建的桌面级 Web 应用",
                             value=True
                         ))

            ui.separator()
            ui.menu_item("设置", auto_close=False, on_click=on_settings_click)

            ui.separator()
            ui.menu_item("使用介绍", auto_close=False,
                         on_click=lambda: TextDialog(content=dynamic_settings.intruction_content,
                                                     title="使用介绍", value=True))

        with ui.context_menu(), ui.list():
            ui.menu_item("待办事项", on_click=lambda: ui.navigate.to("/todolist"))

            # todo: 未来主页可以用卡片式进入那个功能，header 右侧就加个返回主页就行了！

            ui.separator()
            ui.menu_item("重构前瞻", on_click=lambda: ui.navigate.to("/note/index"))

            ui.separator()
            ui.menu_item("备忘录", on_click=lambda: ui.navigate.to("/memo/index"))

            ui.separator()
            url = "https://zhuanlan.zhihu.com/p/200757887"
            ui.menu_item("会了吧", on_click=lambda: ui.navigate.to(url, new_tab=True))

            # [note] 一个 menu_item 既要展开子菜单，又要响应点击，这是冲突的
            # with ui.menu_item("关于", auto_close=False).classes("items-center justify-between"):
            #     # ui.icon("keyboard_arrow_right") # 有点丑啊
            #     with ui.menu().props("anchor=\"top end\" self=\"top start\""), ui.list():
            #         ui.menu_item("作者")
            #         ui.menu_item("软件", on_click=show_about_dialog)

    return menu_button


# endregion

async def see_attachment(note_id: int, detail_page: bool = False):
    performed_deletion = False

    def create_card(attachment: Attachment):
        with ui.card().classes("w-full") as card:
            # [question] 这个 gap-32 是绝对值，适应性如何？
            with ui.row().classes("w-full flex items-center justify-between gap-32"):
                with ui.column().classes("gap-y-0"):
                    # [step] ai: ui.label("项目规划流程图.png") 我想设置最大显示长度 -> 设置最大宽度并启用文本截断

                    # todo: 使用 input 的话就可以直接编辑了，监听回车键，保存，然后修改数据库内容
                    main_title = ui.label(attachment.filename).classes("max-w-48 truncate text-ellipsis")
                    main_title.tooltip(attachment.filename)

                    if not detail_page:
                        async def modify_attchment_filename():
                            async def on_confirm_click():
                                if not new_filename.value:
                                    ui.notify("请输入新文件名", type="warning")
                                    return
                                if new_filename.value == main_title.text:
                                    ui.notify("新文件名和旧文件名不能相同", type="warning")
                                    return
                                filename = new_filename.value.strip()
                                # 获得旧文件名后缀
                                check_result = is_valid_filename(filename)
                                if check_result.is_err():
                                    ui.notify(f"修改失败，原因：{check_result.err()}", type="negative")
                                    return
                                async with AttachmentService() as service:
                                    old_filename = attachment.filename
                                    ext = os.path.splitext(old_filename)[1]
                                    if ext:
                                        filename = filename + ext
                                    logger.debug("ext: {}", ext)
                                    logger.debug("filename: {}", filename)
                                    result = await service.update(attachment.id, filename=filename)
                                    if result.is_err():
                                        ui.notify(f"错误：{result.err()}", type="negative")
                                    else:
                                        ui.notify("修改附件文件名成功！", type="positive")
                                        dialog.close()
                                        main_title.text = filename

                            with ui.dialog() as dialog, ui.card():
                                with ui.column().classes("pt-4 w-full"):  # border-2 border-dashed
                                    with ui.row().classes("w-full flex items-center justify-between"):
                                        ui.label("新文件名")
                                        new_filename = ui.input(placeholder="输入新文件名")
                                        new_filename.props("dense outlined autofocus")
                                        new_filename.on("keydown.enter", lambda: on_confirm_click())
                                    with ui.row().classes("w-full flex items-center justify-end"):
                                        confirm = ui.button("确定", on_click=on_confirm_click)
                                        confirm.props("unelevated color=primary")

                            dialog.open()

                        main_title.classes("cursor-pointer")
                        main_title.on("click", modify_attchment_filename)

                    sub_title_content = f"{attachment.size}b · {attachment.mimetype}"
                    sub_title = ui.label(sub_title_content)
                    sub_title.classes("max-w-32 truncate text-ellipsis text-gray-500 text-xs")
                    sub_title.tooltip(sub_title_content)

                    # todo: 实现点击复制文本内容并 ui.notify

                with ui.row().classes("gap-0"):
                    def see():
                        ui.navigate.to(f"/api/view_file?file_id={attachment.id}", new_tab=True)

                    # [2025-11-14] 暂且就通过这种方式实现吧
                    eye = ui.button(icon="mdi-eye-outline", on_click=see).props("flat dense")
                    eye.tooltip("查看或下载")

                    # [2025-11-14] 下载按钮暂且无效，目前没想到什么好办法
                    # ui.button(icon="mdi-download-outline").props("flat dense")

                    async def on_delete():
                        async with AttachmentService() as service:
                            result = await service.delete(attachment.id)
                            if result.is_err():
                                ui.notify(f"删除文件失败，原因：{result.err()}", type="negative")
                            else:
                                ui.notify("删除文件成功", type="positive")
                                card.delete()
                                nonlocal performed_deletion
                                performed_deletion = True

                    # todo: 查看详情页面不支持删除（置灰 + 不可点击）
                    delete = ui.button(icon="mdi-trash-can-outline")
                    delete.props("flat dense").classes("text-red")
                    if detail_page:
                        delete.disable()  # disable() 会自动添加禁用样式（置灰）并阻止点击事件
                    else:
                        delete.on("dblclick", on_delete)
                        delete.tooltip("双击删除")

                # todo: 此处可以存放一个隐藏组件，用于展开查看文件内容（只支持预览图片）
        return card

    async def preview_images():
        with ui.dialog(value=True), ui.card().classes("w-[500px] h-[500px]"):
            # dialog 好像只能这么大？可恶... 得解决
            ui.image("docs/images/page_add_note.png").classes("w-[500px] h-[500px]")

    # ====== ui ====== #
    with ui.dialog() as dialog, ui.card():
        with ui.row().classes("w-full flex items-center justify-between"):
            ui.label("附件列表")
            ui.button("预览图片", on_click=preview_images).props("flat color=grey").tooltip("弹窗预览所有附件图片")
            ui.button(icon="mdi-close", on_click=dialog.close).props("flat")

        ui.separator()

        async with AttachmentService() as service:
            result = await service.get_attachments_by_note_id(note_id)
            attachments = result.unwrap_or_else([])

        with ui.column().classes("w-full items-center px-3 py-1 gap-y-2 min-h-16 min-w-64 max-h-64 overflow-y-auto"):
            for _attachment in attachments:
                create_card(_attachment)

        ui.separator()

        with ui.row().classes("w-full flex items-center justify-end"):
            async def on_close():
                dialog.close()

                # 判断如果进行了删除操作，则刷新页面
                # [note] 随便一个软件细节都很多啊，所以软件开发反倒不是重要的，而是设计，否则开发一半还得修改难受死了！
                if performed_deletion:
                    await refresh_page()

            ui.button("关闭", on_click=on_close)

    dialog.open()


async def build_footer():
    # [css note] ui.header 的阴影效果无用，ui.footer 还得用经典效果
    with ui.footer().classes("bg-white border-t border-gray-200") as footer:
        pass


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


class HeaderController(Controller["HeaderView"]):
    async def on_toolkit_btn_click(self):
        # todo: ui.dialog 的宽度到底咋设置的？真麻烦啊...
        #       nicegui 简单吗？简单！难吗？难！...
        #       道与术，术才是根基啊，nicegui 是简单，但是也很难...
        #       关于道与术，之前看到知乎的一篇文章，就是描述深入底层学习的好处...文章在哪，之后找一找吧...
        #       虽然我之前就说明，nicegui 界面只要能用就行，但是这种基础的宽度设置... 唉！前端不入门 nicegui 终究不是正道！
        #       [设置class好像无效一样](https://www.qianwen.com/share?shareId=55f9876a-1fe5-4751-ab08-57c8846c2b24)
        #       还是建议学 vue/react 等，学完再来思考 nicegui，这玩意，太尴尬了...它需要懂前端，而且隐藏了细节，修改样式很困难...
        #       建议先入门 vue，然后去使用 quasar...
        #       !!! quasar 组件实在是好多好用的，可惜英语不好，唉...
        #       nicegui 资料太少了！！！

        # 太坑爹了，感觉首先要学的是如何通过 F12 查看各种属性...
        # 研究半天，终于解决了！
        # classes("w-[60vw] !max-w-none") 可以替代 style，内联优先级 > class 但是 class 设置 ! 可以提高优先级！

        with ui.dialog(value=True), ui.card().classes(
                "w-[60vw] !max-w-none "
                "bg-gray-900 text-green-400 font-mono rounded-none border border-gray-700 "
        ):
            def execute_command(command: str):
                command = command.strip()
                if not command:
                    return
                log_view.push(f"$ {command}")
                # todo: 模拟一个建议的控制台，通过输入命令的方式使用一些工具！
                #       视频参考：https://v.douyin.com/mpmhZ5QTYrE/
                # 感慨啊，程序员真得足够热爱才行...而且还有足够的自信和耐心，欧洲高福利国家确实容易出厉害的程序员
                if command == "help":
                    log_view.push("可用命令: help, echo <text>, date, clear")
                elif command.startswith("echo "):
                    log_view.push(command[5:])
                elif command == "date":
                    log_view.push(str(datetime.now()))
                elif command == "clear":
                    log_view.clear()
                    log_view.push("欢迎使用 NiceGUI Terminal！输入 help 查看帮助。")
                elif match := re.match(r"^read\s+(.+)$", command.strip()):
                    filepath = match.group(1)
                    # 简单测试一下而已... 挺麻烦的... 当然主要是解析 command，按空格切割差不多
                    try:
                        log_view.push(Path(filepath).read_text(encoding="utf-8"))
                    except Exception as e:
                        log_view.push(f"错误：{e}")
                else:
                    log_view.push(f"未识别的命令: {command}")
                command_input.value = ""

            log_view = ui.log(max_lines=100).classes("w-full h-80 bg-gray-900 text-green-400 p-3 overflow-y-auto")
            # [Colors](https://tailwindcss.com/docs/colors#default-color-palette)
            command_input = ui.input(placeholder="输入命令...").classes(
                "w-full mt-2rounded-none p-2 "
                "border border-gray-700 "
                "bg-gray-900 text-green-400 "
            ).props('input-style="color: oklch(79.2% 0.209 151.711);"') \
                .on("keydown.enter", lambda e: execute_command(e.sender.value))

            log_view.push("欢迎使用 NiceGUI Terminal！输入 help 查看帮助。")

    async def visualize(self):
        with ui.dialog(value=True) as dialog, ui.card():  # "h-[800px]" 单独的这个 classes 可以生效
            # with ui.matplotlib(figsize=(3, 2)).figure as fig:
            #     x = np.linspace(0.0, 5.0)
            #     y = np.cos(2 * np.pi * x) * np.exp(-x)
            #     ax = fig.gca()
            #     ax.plot(x, y, "-")

            # 参考一下：https://www.qianwen.com/share?shareId=c807c63b-366d-46dc-89b0-21fe1d639399

            # 假设你有一个 DataFrame df，包含 "created_at" 列（字符串或 datetime）
            # 这里我们模拟一些数据
            data = {
                "created_at": pd.date_range("2025-11-01", periods=100, freq="H").repeat(3)
            }
            # todo: 对于后端 web 程序员来说，pandas 是最有价值的库（相对于 numpy 和 matplotlib）
            #       只需掌握 pandas 核心能力即可
            df = pd.DataFrame(data)

            # 转换为 datetime 并重采样绘图
            df["created_at"] = pd.to_datetime(df["created_at"])
            ts = df.set_index("created_at").resample("D").size()

            # 使用 ui.pyplot 显示图表
            with ui.pyplot(figsize=(10, 6)):
                ts.plot(kind="line", marker="o")
                plt.title("Daily Counts")
                plt.xlabel("Date")
                plt.ylabel("Count")
                plt.grid(True)

    async def show_link_collection(self):
        class events:  # noqa
            @staticmethod
            async def paste():
                text = pyperclip.paste()
                link.value += text

            @staticmethod
            async def confirm():
                async def delay():
                    dialog.close()
                    await refresh_page()

                if not text.value or text.value.strip() == "":
                    ui.notify(f"文本不能为空", type="warning")
                    return
                if not link.value:
                    ui.notify(f"链接不能为空", type="warning")
                    return

                # 提取 link 中的链接
                urls = extract_urls(link.value)
                if not urls:
                    ui.notify(f"未提取到有效链接，请重新输入", type="negative")
                    link.value = ""
                    return

                for i, url in enumerate(urls):
                    urls[i] = f"{i + 1}. {url}"

                async with NoteService() as note:
                    result = await note.create(**dict(
                        title=text.value,
                        content="\n".join(urls),
                        note_type=NoteTypeMaskedEnum.HYPERLINK
                    ))
                    if result.is_err():
                        ui.notify(f"错误，原因：{result.err()}", type="negative")
                        return
                    ui.notify("新建超链接成功", type="positive")
                    ui.timer(0.5, delay, once=True)

            @staticmethod
            async def ai_generate():
                if not link.value:
                    ui.notify("链接不能为空", type="warning")
                    return

                try:
                    # [2025-12-10] 实践发现，pyside 会导致闪烁，还是不靠谱，套壳的话，推荐还是 electron 吧（native 启动太慢了）
                    # self.view.loading_overlay.show()
                    generate_btn.props("loading")
                    confirm_btn.props("disable")
                    async with DeepSeekClient() as client:
                        result = await client.ai_generate_text(link.value)
                        if result.is_err():
                            ui.notify(f"生成失败，原因：{result.err()}", type="negative")
                        else:
                            ui.notify(f"生成文本成功！", type="positive")
                            text.value = result.value
                except Exception as e:
                    logger.error(e)
                finally:
                    # self.view.loading_overlay.hide()
                    generate_btn.props(remove="loading")
                    confirm_btn.props(remove="disable")

        dialog = ui.dialog().props("persistent")
        with dialog, ui.card().classes("pb-2"):
            # [step] ai answer: 右上角关闭按钮（用绝对定位）| [question] 绝对布局到底咋布局的？| [do] 当前 dialog 的布局我看起来还可以接受
            with ui.row().classes("w-full flex justify-end items-center pr-4"):
                ui.icon("close").classes("cursor-pointer text-blue text-lg") \
                    .classes("cursor-pointer rounded-lg hover:bg-gray-200 ") \
                    .on("click", dialog.close)

            # 该结构参考石墨文档的插入超链接的选项，虽然石墨文档的页面更舒服
            # todo: 桌面组件建议可以参看石墨文档（或者其他软件）看看它们是如何组织组件的、如何利用空间的。哈哈，比如上传附件，限制 10MB，我的项目也可以限制 10MB
            with ui.grid(columns=4).classes("items-center"):
                # --- 文本:文本输入框 1:3
                ui.label("文本").classes("text-center col-span-1")
                text = ui.input(placeholder="输入文本").props("dense").classes("col-span-3") \
                    .on("keydown.enter", events.confirm)

                # --- 链接:链接输入框 1:3
                ui.label("链接").classes("text-center col-span-1") \
                    .tooltip("可以输入长文本，保存时会自动提取所有链接")
                link = ui.input(placeholder="输入链接").props("dense").classes("col-span-3") \
                    .on("keydown.enter", events.confirm)
                with link, ui.context_menu():
                    ui.menu_item("粘贴", on_click=events.paste).tooltip("追加到末尾")

                # --- 4 份均可单独塞一个按钮
                ui.space().classes("col-span-2")
                generate_btn = ui.button("生成", on_click=events.ai_generate) \
                    .props("flat").tooltip("基于链接AI生成文本")
                confirm_btn = ui.button("确定", on_click=events.confirm).props("flat")

        dialog.open()


class HeaderEvents:
    def __init__(self, view: "HeaderView"):
        self.view = view

    async def import_note(self):
        """导入笔记"""
        # 弹窗选择笔记，然后导入（对于弹窗来说，不用担心 tkinter 阻塞主线程，阻塞了没什么影响的）
        filedialog = import_filedialog()
        with create_tk_root():
            filepath = filedialog.askopenfilename(
                title="选择要上传的笔记文件",
                filetypes=[
                    ("文本文件", "*.txt *.md *.markdown"),
                    ("Markdown 文件", "*.md *.markdown"),
                    ("纯文本文件", "*.txt"),
                    ("所有文件", "*.*")
                ]
            )

        if not filepath:
            ui.notify("没有选择任何文件")
            return

        title = os.path.splitext(os.path.basename(filepath))[0] + "【笔记导入】"
        content = Path(filepath).read_text(encoding="utf-8")

        async with NoteService() as service:
            await service.create(title=title, content=content)
            ui.notify("笔记导入成功！", type="positive")
            ui.timer(0.5, refresh_page, once=True)

    async def batch_exports(self):
        """将所有笔记（普通笔记和超链接）导出为 markdown 文件，并存储到指定目录中"""

        async def export():
            # todo: 检测 C/D 开头，否则需要设置一个默认导出位置，建议是 C 盘的 Documents 等
            try:
                export_dir = Path(export_dir_input.value) / "notes"
                if not export_dir.exists():
                    export_dir.mkdir(parents=True)
            except Exception as e:
                logger.error("{}({})", e, type(e).__name__)
                ui.notify(f"导出目录创建失败，原因：{e}", type="negative")
                return
            try:
                # 迭代遍历所有普通笔记，并写入 export_dir 中，存在则覆盖，不存在则写入, 文件名格式为：{note_id}.md
                async with NoteService() as note_service:
                    result = await note_service.list_all()
                    if result.is_err():
                        ui.notify(f"获取笔记失败，原因：{result.err()}", type="negative")
                        return
                    notes = result.unwrap()
                    for note in notes:
                        async with aiofiles.open(export_dir / f"{note.id}.md", "w", encoding="utf-8") as f:
                            await f.write(f"标题：{note.title}\n\n\n\n正文：\n\n{note.content}")
            except Exception as e:
                logger.error("{}({})", e, type(e).__name__)
                ui.notify(f"导出笔记失败，原因：{e}", type="negative")
            else:
                ui.notify(f"导出笔记成功，共导出 {len(notes)} 条笔记，导出位置：{export_dir}", type="positive")
                dialog.close()

        with ui.dialog(value=True).props("persistent") as dialog, ui.card():
            export_dir_input = ui.input("导出目录", placeholder="请输入正确格式的目录")
            with ui.row().classes("w-full justify-end"):
                ui.button("取消", on_click=dialog.close).props("flat")
                ui.button("确定", on_click=export).props("flat")

    async def ocr(self):
        file = {}

        try:
            import easyocr
        except ImportError as e:
            ui.notify("OCR 识别模块未安装，请先安装 easyocr 模块", type="negative")
            return

        async def on_upload(e: UploadEventArguments):
            file.clear()
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(e.content.read())
                temp_filepath = temp_file.name
            file["filepath"] = temp_filepath
            file["name"] = e.name
            file["type"] = e.type

        async def do_ocr():
            if not file:
                ui.notify("请先上传文件", type="negative")
                return
            try:
                recognition_btn.props("loading")
                cancel_btn.props("disable")
                results = await run.cpu_bound(easyocr_read_file, file["filepath"])
                result_area.clear()
                # todo: 即使调用 sort_easyocr_results 也没办法让结构合理，这时候超小模型就派上用场了
                with result_area:
                    ui.code("\n".join(sort_easyocr_results(results, y_threshold=15))).classes("w-3xl")
            except Exception as e:
                logger.error("{}({})", e, type(e).__name__)
                ui.notify(f"OCR 识别失败，原因：{e}", type="negative")
            finally:
                upload.reset()  # todo: 阅读 quasar 文档和 nicegui 源代码，弄明白 upload 的细节
                recognition_btn.props(remove="loading")
                cancel_btn.props(remove="disable")
                os.remove(file["filepath"])
                file.clear()

        # fixme: 其实直接让现成的 ai 服务帮你 ocr 更好，这个 easyocr 还是太轻量了，准确度也就那样
        with ui.dialog(value=True).props("persistent") as dialog, ui.card().classes("items-center !max-w-none"):
            # todo: 实现方便的粘贴上传（使用 ui.keyboard() 及其参数 js_handler 实现）
            #       话说，js 我目前确实只能算是半入门，因为连基础的前端事件都没有了解多少
            upload = ui.upload(
                max_file_size=10 * 1024 * 1024,
                on_upload=on_upload,
                auto_upload=True,
                label="上传图片"
            ).props("accept='.jpg, .png, image/*'")
            result_area = ui.column().classes("w-full items-center")
            with ui.row().classes("w-full justify-end"):
                cancel_btn = ui.button("取消", on_click=dialog.close).props("flat")
                recognition_btn = ui.button("识别", on_click=do_ocr).props("flat")


class HeaderView(View["HeaderController"]):
    controller_class = HeaderController

    async def _initialize(self):
        self.events = HeaderEvents(self)
        self.list_btn_active = ui.context.client.page.path == "/"
        self.create_btn_active = ui.context.client.page.path == "/add_or_edit_note"

        self.loading_overlay = LoadingOverlay()

        # [step] 使用 ui.icon 找到的图标不生效，发现需要导入
        # <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@7.4.47/css/materialdesignicons.min.css" />
        # <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
        ui.add_head_html("""
        <link rel="stylesheet" href="/static/materialdesignicons.min.css" />
        """)

        # [css note] bg-white 背景白色，shadow-sm 加一个微妙的阴影，header 看起来浮在内容上方，自然形成边界
        with ui.header().classes("bg-white shadow-sm py-3") as header:
            with ui.row().classes("w-full mx-auto max-w-7xl flex justify-between items-center px-4 sm:px-6 md:px-8"):
                with ui.row().classes("items-center gap-x-1"):
                    build_softmenu()
                    ui.label("笔记管理系统").classes("text-xl font-bold text-gray-800 cursor-pointer") \
                        .on("click", lambda: ui.navigate.to("/"))

                ui.space()

                with ui.row().classes("items-center gap-x-1"):
                    if os.environ.get("MKDOCS_PORT"):
                        url = f"http://localhost:{os.environ["MKDOCS_PORT"]}"
                        ui.button("实验室", on_click=lambda: ui.navigate.to(url)).props("flat")
                    else:
                        ui.button("实验室").props("flat")
                    ui.button("可视化", on_click=self.controller.visualize).props("flat")
                    ui.button("工具集", on_click=self.controller.on_toolkit_btn_click).props("flat")

                    with ui.button("更多").props("flat"), \
                            ui.menu(), ui.column().classes("gap-y-0"):
                        # todo: 附件新增 ocr_text 字段，将附件图片进行后台 ocr 处理（backendtasks?）| 新增通用图片上传入口
                        ui.button("图片查询").classes("w-full").props("flat")
                        # todo: 新增选择文件或保存文件的通用功能（推荐 tkinter + native）
                        ui.button("图片识别", on_click=self.events.ocr).classes("w-full").props("flat") \
                            .tooltip("OCR 图片识别、PDF 识别并导出文本或者直接弹窗预览文本")
                        ui.button("批量导出", on_click=self.events.batch_exports).classes("w-full").props("flat")
                        ui.button("笔记导入", on_click=self.events.import_note).classes("w-full").props("flat")

                ui.space()

                with ui.row().classes("flex justify-between items-center"):
                    with ui.row().classes("gap-x-2"):
                        list_btn = ui.button("列表视图", on_click=go_main, icon="mdi-format-list-bulleted")
                        list_btn.props("unelevated flat dense")
                        list_btn.classes(
                            "text-sm font-medium text-gray-700 "
                            "bg-gray-100 hover:bg-gray-200 "
                            "px-3 py-1.5 rounded-lg"
                        )
                        # [question] 测试发现，bg-black bg-blue 能生效，带数字却不生效，而 bg-gray-200 带数字却生效
                        create_btn = ui.button("新建笔记", on_click=go_add_note, icon="mdi-square-edit-outline")
                        create_btn.props("unelevated flat dense")
                        create_btn.classes(
                            "text-sm font-medium text-gray-700 "
                            "bg-gray-100 hover:bg-gray-200 "
                            "px-3 py-1.5 rounded-lg"
                        )

                        async def show_title_view():
                            async def create_item(note: NoteService.NotePreview):
                                with ui.item():
                                    with ui.item_section().props("avatar"):
                                        ui.item_label(str(note.id)) \
                                            .classes("cursor-pointer") \
                                            .on("click", partial(go_get_note, note.id)) \
                                            .tooltip("跳转至详情页")
                                    with ui.item_section():
                                        truncated_content = note.content[:200]
                                        if truncated_content.strip():
                                            truncated_content += "..."
                                        with ui.item_label(note.title).classes("cursor-pointer") \
                                                .on("click", partial(go_get_note, note.id)):
                                            ui.tooltip(truncated_content).props("max-width=50vw")

                            with ui.dialog(value=True), ui.card():
                                # todo: 可以添加个搜索按钮
                                with ui.list().props("separator"):
                                    async with NoteService() as service:
                                        note_previews = await service.get_no_content_notes()
                                    for note in note_previews:
                                        await create_item(note)

                        with list_btn, ui.context_menu():
                            ui.menu_item("标题视图", auto_close=False, on_click=show_title_view)

                        # [step] ai: nicegui ui.menu 能不能实现右键点击的时候才显示
                        with create_btn, ui.context_menu():
                            # todo: 列表视图添加筛选，Note 表也要新增笔记类型，默认筛选的是 default 类型，其他类型都是不支持筛选的
                            ui.menu_item("新建超链接", auto_close=False).on_click(self.controller.show_link_collection)

                        if self.list_btn_active:
                            list_btn.classes("bg-gray-200")
                        if self.create_btn_active:
                            create_btn.classes("bg-gray-200")
