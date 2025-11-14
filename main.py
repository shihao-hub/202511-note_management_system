import contextlib
import json
import math
import sys
import uuid
from functools import partial
from typing import Tuple

import pyperclip
from addict import Dict as Addict
from nicegui import ui, app, native
from nicegui.events import GenericEventArguments
from fastapi.requests import Request
from loguru import logger
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# python-doenv 设置环境变量
load_dotenv(".env")

# 设置 jinja2 模板目录
env = Environment(loader=FileSystemLoader("./templates"))

# 项目的包建议放在最下面执行，这样最稳当
from api import fastapi_app
from models import Note, Attachment, init_db
from utils import cleanup, DeepSeekClient, RateLimiter, show_about_dialog, show_text_dialog
from services import NoteService, AttachmentService
from settings import dynamic_settings, PAGE_SIZE

# [note][2025-11-13] 初版完成后，通义非深度思考模式：
#                    `使用 tailwindcss、quasar 美化下面的 nicegui 代码，要求只修改修改样式`
#                    `我希望在 不改动逻辑结构 的前提下，仅通过 Tailwind CSS 和 Quasar 风格来美化这段 NiceGUI 代码`

# [note] 重点笔记，可以非深度思考模式问 ai 一些 tailwind css 元素问题，不要太复杂，很好用！
# [note] 前端在开发阶段要求可用即可，如骨架、按钮响应等，关键还是进行后端部分的开发！

# pyinstaller（注意 sqlalchemy 搭配 alembic 的主动迁移命令，导致打包后出错，需要考虑如何解决，虽然复制一个无数据 db 即可解决）
try:
    import addict
    import aiosqlite
    import loguru
    import alembic
    import sqlalchemy
    import sqlalchemy_utc
    import fastapi
    import jinja2
except ImportError as exception:
    logger.error(exception)

# 移除默认的日志处理器
logger.remove()
# 控制台输出 - 彩色，简洁格式
logger.add(
    sys.stdout,
    format="<c>{time:YYYY-MM-DD HH:mm:ss.SSS}</c> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}",
    level="DEBUG",
    colorize=True,
    backtrace=True,
    diagnose=True
)
# 详细日志文件 - 包含所有级别
logger.add(
    "debug.log",
    format="<c>{time:YYYY-MM-DD HH:mm:ss.SSS}</c> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    backtrace=True,
    diagnose=True
)


def build_header() -> ui.header:
    # [step] 使用 ui.icon 找到的图标不生效，发现需要导入
    ui.add_head_html("""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@mdi/font@7.4.47/css/materialdesignicons.min.css" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    """)

    list_btn_active = ui.context.client.page.path == "/"
    # todo: 暂时无法区分 新增和编辑，未来显然应该拆分 page，本来就耦合严重
    create_btn_active = ui.context.client.page.path == "/add_or_edit_note"

    # [css note] bg-white 背景白色，shadow-sm 加一个微妙的阴影，header 看起来浮在内容上方，自然形成边界
    with ui.header().classes("bg-white shadow-sm py-3") as header:
        with ui.row().classes("w-full mx-auto max-w-7xl flex justify-between items-center px-4 sm:px-6 md:px-8"):
            with ui.row().classes("items-center gap-x-1"):
                # [step] 搜索 ui.icon 的资料 -> 参考 Quasar 的图标文档来查看所有可用的图标（https://quasar.dev/vue-components/icon -> https://pictogrammers.com/library/mdi/icon/note/）
                # [step] ai: nicegui 如何设置 ui.label 和 ui.icon 的大小和颜色？
                #        an: https://lxblog.com/qianwen/share?shareId=5e5d87f2-45af-4b86-80ad-aaf02de189dd
                # ui.icon(name="mdi-note", size="28px").classes("text-blue-600")
                with ui.button(icon="mdi-note").props("flat dense size=16px color=blue-600"):
                    with ui.menu(), ui.list():
                        ui.menu_item("主页", on_click=go_main)
                        ui.separator()
                        ui.menu_item("关于", auto_close=False, on_click=show_about_dialog)
                        ui.separator()

                        def on_click():
                            show_text_dialog(
                                content=dynamic_settings.intruction_content,
                                title="使用介绍",
                            )

                        ui.menu_item("使用介绍", auto_close=False, on_click=on_click)

                        # [note] 一个 menu_item 既要展开子菜单，又要响应点击，这是冲突的
                        # with ui.menu_item("关于", auto_close=False).classes("items-center justify-between"):
                        #     # ui.icon("keyboard_arrow_right") # 有点丑啊
                        #     with ui.menu().props("anchor=\"top end\" self=\"top start\""), ui.list():
                        #         ui.menu_item("作者")
                        #         ui.menu_item("软件", on_click=show_about_dialog)

                ui.label("笔记管理系统").classes("text-xl font-bold text-gray-800")

            # 占位符（保持右侧对齐）
            ui.space()

            with ui.row().classes("flex justify-between items-center"):
                # placeholder

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

                    if list_btn_active:
                        list_btn.classes("bg-gray-200")
                    if create_btn_active:
                        create_btn.classes("bg-gray-200")

    return header


def build_footer() -> ui.footer:
    # [css note] ui.header 的阴影效果无用，ui.footer 还得用经典效果
    with ui.footer().classes("bg-white border-t border-gray-200") as footer:
        pass

    return footer


def go_main():
    ui.navigate.to("/")


def go_add_note():
    ui.navigate.to(f"/add_or_edit_note?temporary_uuid={uuid.uuid4()}")


def go_edit_note(note_id: int):
    ui.navigate.to(f"/add_or_edit_note?note_id={note_id}&temporary_uuid={uuid.uuid4()}")


def go_get_note(note_id: int):
    ui.navigate.to(f"/get_note?note_id={note_id}")


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

                    # todo: 查看详情页面不支持删除（置灰即可）
                    ui.button(icon="mdi-trash-can-outline", on_click=on_delete).props("flat dense").classes("text-red")

                # todo: 此处可以存放一个隐藏组件，用于展开查看文件内容（只支持预览图片）
        return card

    # ====== ui ====== #                
    with ui.dialog() as dialog, ui.card():
        with ui.row().classes("w-full flex items-center justify-between"):
            ui.label("附件列表")
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
                    await ui.run_javascript("location.reload()")

            ui.button("关闭", on_click=on_close)

    dialog.open()


with open("test_notes.json", "r", encoding="utf-8") as f:
    notes_json = Addict(json.load(f))


@ui.page("/get_note", title="笔记详情")
async def page_get_note(request: Request, note_id: int):
    # [question] 新增 page 导致点击时页面需要刷新，有没有更流畅的办法呢？有的，定义一个 div，然后通过调用 clear 方法，重新构建 div

    build_header()
    build_footer()

    async def get_note():
        async with NoteService() as service:
            # [knowledge] [Rust 的 Result 类型详解](https://lxblog.com/qianwen/share?shareId=c6059ca1-51c6-4424-876d-6e2019bfb925)
            result = await service.get(note_id)
            logger.debug("result: {}", result)
            return result.unwrap()

    note: Note | Addict = await get_note()
    logger.debug(f"note_id: {note_id}")

    with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl py-6"):
        with ui.row().classes("w-full items-center gap-x-3 mb-6"):
            button = ui.button(icon="mdi-arrow-left", on_click=go_main)
            button.props("flat round").classes("text-gray-700 hover:bg-gray-100")
            ui.label("笔记详情").classes("text-xl font-bold text-gray-900")

        card = ui.card().classes("w-full rounded-xl shadow-md border border-gray-200 overflow-hidden")
        with card, ui.column().classes("w-full px-5 py-6"):
            def copy_note(text):
                pyperclip.copy(text)
                ui.notify("复制到剪切板成功")

            # 标题行
            with ui.row().classes("w-full items-center justify-between mb-4"):
                title = ui.label(note.title).classes("text-gray-900 font-bold text-2xl leading-tight")
                copy_btn = ui.button(icon="mdi-content-copy")
                copy_btn.classes("text-[10px]").props("flat dense color=grey")

            # 内容文本区
            markdown = ui.label(note.content).style("white-space: pre-wrap")
            markdown.classes("w-full max-h-96 overflow-y-auto ")  # max-h-128 舒服一点

            # 自定义 Markdown 字体大小等样式
            ui.add_css("""
                .nicegui-markdown h1 { font-size: 1.6rem; }
                .nicegui-markdown h2 { font-size: 1.4rem; }
                .nicegui-markdown h3 { font-size: 1.25rem; }
                .nicegui-markdown h4 { font-size: 1.1rem; }
                .nicegui-markdown h5 { font-size: 1.0rem; }
                .nicegui-markdown h6 { font-size: 0.9rem; }
            """)

            # copy_btn.on("click", partial(copy_note, text=f"{title.text}\n\n{markdown.content}"))

            # [step] ai: ui.textarea 最下面的虚线可以隐藏吗？通过设置 autogrow 自动变化，会隐藏 resize 控件
            # todo: relative 是什么？absolute 又是什么？
            # with ui.element("div").classes("w-full relative"):
            #     textarea = ui.textarea(value=note.content)
            #     textarea.classes("w-full bg-transparent max-h-48 overflow-y-auto ")  # overflow-x-hidden min-h-32
            #     textarea.props("readonly hide-bottom-space autogrow no-resize")

            # 这个导致 overflow-x 的出现，算了，这个删掉吧，或者找个更好的方法去实现
            # with textarea.add_slot("append"):
            #     copy = ui.button(icon="mdi-content-copy", on_click=partial(copy_note, text=textarea.value))
            #     copy.classes("text-[10px] -mr-1 -mb-1").props("flat dense color=grey")

            # 悬浮按钮（绝对定位）
            # copy_btn = ui.button(icon="mdi-content-copy", on_click=partial(copy_note, text=note.content))
            # copy_btn.classes("absolute bottom-2 right-2 z-10")
            # copy_btn.props("flat dense color=grey size=sm")

            # todo: 目前这种情况看起来还算舒适，但是文章过长该如何是好呢？需要解决这个问题...
            #       直接 menu 吧，放在标题后面，哈哈
            # textarea = ui.textarea(value=note.content)
            # textarea.classes("w-full bg-transparent")
            # textarea.props("readonly hide-bottom-space autogrow")
            # with textarea.add_slot("append"):
            #     copy = ui.button(icon="mdi-content-copy", on_click=partial(copy_note, text=textarea.value))
            #     copy.classes("text-[10px] -mr-1 -mb-1").props("flat dense color=grey")

            # 附件区域
            with ui.column().classes("w-full mt-6 mb-4"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("附件").classes("font-medium text-gray-800")
                    button = ui.button("查阅附件", on_click=partial(see_attachment, note_id=note_id))
                    button.props("flat icon-right=mdi-chevron-right dense").classes("text-blue-600")

                async with AttachmentService() as service:
                    result = await service.count_attachment(note_id)
                    ui.label(f"{result.unwrap()} 个附件").classes("text-sm text-gray-500 mt-1")

            ui.separator().classes("my-4")

            # 底部元信息与操作按钮
            with ui.row().classes("w-full items-center justify-between mt-4"):
                ui.label(f"创建于：{note.created_at} · 更新于：{note.updated_at}").classes("text-sm text-gray-500")

                with ui.row().classes("items-center gap-x-2"):
                    edit_on_click = partial(go_edit_note, note_id=note_id)
                    button = ui.button("编辑", icon="mdi-square-edit-outline", on_click=edit_on_click)
                    button.props("flat dense").classes("text-blue-600")

                    async def delete_note():
                        async def confirm():
                            async with NoteService() as service:
                                result = await service.delete(note_id)
                                if result.is_ok():
                                    dialog.close()
                                    # 删除笔记确实需要强制返回，除非调用 navigate 传查询参数（延迟 ui.timer 不行），让 page 来弹通知，但是那太搞了吧...
                                    ui.notify(f"删除笔记成功！", type="positive")
                                    ui.timer(0.8, lambda: go_main(), once=True)
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

                    delete = ui.button("删除", icon="mdi-trash-can-outline", on_click=delete_note)
                    delete.props("flat dense color=red").classes("text-red-600 hover:text-red-700")


@ui.page("/add_or_edit_note", title="新增或编辑笔记")
async def page_add_or_edit_note(request: Request, temporary_uuid: str, note_id: int = None):
    """

    :param request: fastapi Request
    :param note_id: note_id 存在为编辑，不存在为新增
    :param temporary_uuid: 供新增使用，为了定位到上传的附件
    """

    # ====== 涉及 header, footer, add_css, add_head_html ====== #

    build_header()
    build_footer()

    ui.add_css("""
    .nms-drag-area.nms-dragover {
        border: 2px dashed #4a90e2;
        background-color: #f0f7ff;
        transition: all 0.2s;
    }
    """)

    def create_upload_attachment_card() -> Tuple:
        """创建当前页面的上传附件 card，目前的设定该函数只能在初始化阶段使用一次"""

        # todo: 确定一下将内部函数统一放在函数最上面，是否可能存在错误？python 的闭包和 js 类似，但是 python 的闭包存在不少坑

        def delay_register():
            # 由于未能找到 python 层面的 preventDefault，所以需要在 DOM 加载后通过 js 层调用 preventDefault，
            # 而 ui.timer 似乎比 DOMContentLoaded 更晚，不然 drop 事件会在 js 层之前注册，依旧无效了

            def on_dragover(e: GenericEventArguments):
                # logger.debug("python dragover event: add nms-dragover class")

                # dragover 会被反复触发，是否会导致添加一堆重复 class？
                card.classes("nms-dragover")

            def on_dragenter(e: GenericEventArguments):
                logger.debug("python dragenter event: add nms-dragover class")

                # logger.debug("e.args: {}", e.args)

                # isTrusted: False 表示这个事件不是由用户直接触发的，而是由程序代码触发的
                if not e.args["isTrusted"]:
                    # logger.debug("111")
                    # card.classes("bg-blue-500")
                    logger.debug("card: {}", id(card))

            def on_dragleave(e: GenericEventArguments):
                # logger.debug("python dragleave event: remove nms-dragover class")

                card.classes(remove="nms-dragover")

            def on_drop(e: GenericEventArguments):
                # logger.debug("python drop event: remove nms-dragover class")

                card.classes(remove="nms-dragover")

            card.on("dragover", on_dragover)
            card.on("dragleave", on_dragleave)
            # card.on("dragenter", on_dragenter)  # 这个似乎没什么用
            card.on("drop", on_drop)

        async def on_nms_upload_success(e: GenericEventArguments):
            logger.debug("upload success")
            ui.notify("文件上传成功", type="positive")
            # 上传成功（非保存页面），应该使用 temporary_uuid 查询数量（注意，这编辑和新增耦合严重，需要考虑解决...）
            async with AttachmentService() as attachment_service:
                existing_count = 0
                logger.debug("note_id: {}", note_id)
                if note_id is not None:
                    existing_result = await attachment_service.count_attachment(note_id)
                    if existing_result.is_err():
                        ui.notify(f"上传失败，原因：{result.err()}", type="negative")
                        return
                    existing_count = existing_result.unwrap()
                temporary_result = await attachment_service.count_attachment_by_temporary_uuid(temporary_uuid)
                if temporary_result.is_err():
                    ui.notify(f"查询临时附件失败：{temporary_result.err()}", type="negative")
                    return
                count = temporary_result.unwrap() + existing_count
                card_label.text = dynamic_settings.attachment_upload_text.format(count)

        # ====== 开始构建 ui 骨架 ====== #

        with ui.card().classes(
                "w-full rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 "
                "flex flex-col items-center justify-center py-4 px-4 "
                "transition-colors duration-200 ease-in-out cursor-pointer "
                "hover:border-gray-400 hover:bg-gray-100 "
                "nms-drag-area"
        ) as card:
            with ui.row().classes("mb-3"):
                ui.icon(name="mdi-attachment", size="28px").classes("text-gray-500")
            card_label = ui.label(dynamic_settings.attachment_upload_text.format(0))
            card_label.classes("text-gray-500 text-center text-sm max-w-xs nms-drag-area")

            # region - 拖拽上传文件

            # 延迟注册拖拽相关事件，主要是修改 css 样式
            ui.timer(0, delay_register, once=True)

            # 监听自定义事件，该事件由 js 层触发
            card.on("nms_upload_success", on_nms_upload_success)

            # 拖拽上传的 js 层代码
            rendered_js = env.get_template("drag_upload.js").render({"container_id": card.id})
            ui.add_head_html(f"<script>{rendered_js}</script>")

            # endregion

        return card, card_label, on_nms_upload_success

    # request type: <class 'starlette.requests.Request'>
    logger.debug("request type: {}", type(request))
    logger.debug("note_id: {}", note_id)

    # note_id 不存在，才是新增笔记页面
    is_add_note_page = True if note_id is None else False

    if is_add_note_page:
        ui.page_title("新增笔记")
    else:
        ui.page_title("编辑笔记")

    # 遮罩背景：纯毛玻璃效果（无背景色）
    with ui.element("div").classes(
            "fixed inset-0 flex items-center justify-center z-50"
    ).style("backdrop-filter: blur(2px); display: none;") as loading_overlay:
        with ui.card().classes("p-6 shadow-lg rounded-lg bg-white flex flex-col items-center"):
            ui.spinner(size="lg")
            loading_label = ui.label("处理中...").classes("mt-4 text-gray-700")

    # todo: show_loading 和 hide_loading 可以使用 contextmanager 管理一下
    def show_loading(message: str = "处理中..."):
        loading_label.set_text(message)
        loading_overlay.style("display: flex;")  # 显示

    def hide_loading():
        loading_overlay.style("display: none;")

    with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl py-6"):
        with ui.row().classes("w-full items-center gap-x-3 mb-6"):
            # [step] ai: ui.icon(name="mdi-arrow-left", size="24px") 可以点击吗？发现 icon 其实是字体，所以改完颜色居然还是默认蓝色

            def on_click():
                # [2025-11-14] 实践发现，访问详情页很别扭呀
                if is_add_note_page:
                    go_main()
                else:
                    go_get_note(note_id)
                # go_main()

            return_btn = ui.button(icon="mdi-arrow-left", on_click=on_click)
            return_btn.props("flat round").classes("text-gray-700 hover:bg-gray-100")
            if is_add_note_page:
                ui.label("新增笔记").classes("text-xl font-bold text-gray-900")
            else:
                ui.label("编辑笔记").classes("text-xl font-bold text-gray-900")

        _card = ui.card().classes("w-full rounded-xl shadow-md border border-gray-200 overflow-hidden")
        with _card, ui.column().classes("w-full px-5 py-6"):
            title = ui.input(placeholder="输入笔记标题...")
            title.classes("w-full text-lg font-medium placeholder:text-gray-400").props("dense")

            async def ai_generate_title():
                if not content.value:
                    ui.notify("正文内容为空，无法生成", type="negative")
                    return
                show_loading("正在生成标题...")
                async with DeepSeekClient() as client:
                    result = await client.ai_generate_title(content.value)
                    if result.is_ok():
                        title.value = result.unwrap()[:100]  # 过长截断
                    else:
                        ui.notify(f"ai 生成出错，原因：{result.err()}", type="negative")
                    hide_loading()

            with title.add_slot("append"):
                with ui.button(icon="menu").classes("text-[10px] -mr-1 -mb-1").props("flat dense color=grey"):
                    with ui.menu():
                        ai_menu_item = ui.menu_item("ai 生成标题", on_click=ai_generate_title)
                        ai_menu_item.tooltip("根据正文内容，让 ai 生成合适的标题")

            content = ui.textarea(placeholder="输入笔记内容...")
            content.classes("w-full mt-4 placeholder:text-gray-400").props("autogrow")

            # [2025-11-13] 本来放在最下面的，导致数据显示有延迟，不可以放在最下面
            # todo: 将数据获取和前端渲染分离开
            count = None
            if not is_add_note_page:
                async with NoteService() as service:
                    result = await service.get_note_with_attachments(note_id)
                    if result.is_err():
                        # todo: 应该弹全局错误弹窗
                        raise Exception(result.err())
                    note = result.unwrap()
                    logger.debug("note: {}", note)
                    attachments = note.attachments

                title.value = note.title
                content.value = note.content

                logger.debug("attachments: {}", attachments)
                count = len(attachments)

            with ui.column().classes("w-full mt-6 gap-y-4"):
                # 附件标题与上传按钮
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("附件").classes("font-medium text-gray-800")
                    # button = ui.button("上传附件", icon="mdi-upload", on_click=lambda: None)
                    # button.props("flat dense").classes("text-blue-600")
                    button = ui.button("查阅附件", on_click=partial(see_attachment, note_id=note_id))
                    button.props("flat icon-right=mdi-chevron-right dense").classes("text-blue-600")

                # todo: upload_attachment_card 需要支持点击然后出现上传的文件弹窗！
                upload_attachment_card, upload_attachment_card_label, on_nms_upload_success = create_upload_attachment_card()

                if not is_add_note_page:
                    upload_attachment_card_label.text = dynamic_settings.attachment_upload_text.format(count)

                # 保存按钮
                with ui.row().classes("w-full justify-end mt-6") as row:
                    rate_limter = RateLimiter(dynamic_settings.save_note_cooldown)

                    async def save_note():
                        if not title.value:
                            ui.notify("标题不能为空", type="negative")
                            return
                        if not content.value:
                            ui.notify("内容不能为空", type="negative")
                            return

                        if not rate_limter.allow():
                            ui.notify(f"操作太频繁，请稍后再试", type="negative")
                            return

                        # 新增页面，有 temporary_uuid，需要更新 attachment
                        # 编辑页面，没有 temporary_uuid 有 note_id，不必考虑 attachment，上传文件时即绑定
                        if is_add_note_page:
                            async with NoteService() as note_service:
                                result = await note_service.create(title=title.value, content=content.value)
                                if result.is_err():
                                    ui.notify(f"错误：{result}", type="negative")
                                else:
                                    # note 创建完毕，由于上传附件不是在保存时统一上传，所以保存时，需要更新附件表
                                    instance = result.unwrap()
                                    async with AttachmentService() as attachment_service:
                                        await attachment_service.update_by_temporary_uuid(temporary_uuid, **dict(
                                            note_id=instance.id,
                                            temporary_uuid=None
                                        ))

                                    # 新增笔记页面需要清空
                                    if is_add_note_page:
                                        title.value = ""
                                        content.value = ""
                                        upload_attachment_card_label.text = (dynamic_settings.attachment_upload_text
                                                                             .format(0))
                                    ui.notify("保存笔记成功！", type="positive")
                                    # 保存笔记不是特别需要强制返回吧，而且这个延迟太不动态了，很难受
                                    # 想迅速响应的话，可以让 ui.notify 在 go_main 调用后执行？主要是进入新页面后弹出来也还好
                                    # ui.timer(0.8, lambda: go_main(), once=True)
                        else:
                            async with NoteService() as service:
                                result = await service.update(note_id, title=title.value, content=content.value)
                                if result.is_ok():
                                    async with AttachmentService() as attachment_service:
                                        await attachment_service.update_by_temporary_uuid(temporary_uuid, **dict(
                                            note_id=note_id,
                                            temporary_uuid=None
                                        ))
                                    ui.notify(f"编辑笔记成功！", type="positive")
                                    # 编辑完毕，滚动到页面顶部
                                    await ui.run_javascript("window.scrollTo(0, 0);")
                                else:
                                    ui.notify(f"编辑笔记失败，原因：{result.err()}", type="positive")

                    # todo: 监听 ctrl + s，自动调用 save_note 函数

                    async def on_keydown(e):
                        logger.debug("on keydown")
                        logger.debug("e: {}", e)

                        # s -> 83
                        if e.args.get("ctrlKey") and e.args.get("keyCode") == 83:
                            await save_note()

                    # 测试发现，input 元素获得焦点后，这个才能生效
                    # ui.on("keydown", on_keydown)

                    save_btn = ui.button("保存笔记", on_click=save_note).props("unelevated")
                    save_btn.classes("px-6 py-2 bg-blue-600 text-white hover:bg-blue-700")  # rounded-2xl

                    ui.on("nms_ctrl_s_pressed", lambda: ui.notify("收到 Ctrl+S！"))

                    ui.add_head_html("<script>{0}</script>".format(env.get_template("key_pressed.js").render({
                        "save_btn_id": save_btn.id,
                        "content_id": content.id,
                    })))

                    content.on("nms_upload_success", on_nms_upload_success)


@ui.page("/", title="笔记管理系统")
async def page_main():
    # request
    # logger.debug("request type: {}", type(request))

    # ====== 开始构建 ui（我将使用 `[step]` 详细记录自己的开发过程，step 代指我在编写这段代码，行动上做了什么） ====== #

    # [step] 使用 region 进行注释拆分的时候发现页面结构基本按照下列方式分层，故而拆分成函数
    build_header()
    build_footer()

    async def build_table(table, current_page: int = 1, search_content: str | None = None) -> ui.element:
        """page_main:build_table"""

        # todo: 骨架与实现推荐拆分（临时设想）

        async def create_add_note_card() -> ui.card:
            # 末尾要求也有一个 card，但是这个 card 是虚线外框，内部一个大大的 + 按钮，下面为新建笔记标题和点击创建新笔记的副标题
            # 结构满足我的要求，但是在的位置不对，新建笔记太麻烦了，除非分页展示，否则无意义
            with ui.card().classes(
                    "shadow-md rounded-xl "
                    "border-dashed border-2 border-gray-200 "
                    "bg-white p-6 "
                    "flex flex-col justify-center items-center "
            ) as card:
                with ui.column().classes("flex items-center gap-y-2"):
                    button = ui.button(icon="add", on_click=go_add_note).props("round flat dense")
                    button.classes("text-3xl text-blue-500 bg-blue-50 text-blue-600")

                    ui.label("新建笔记").classes("text-lg font-medium text-gray-800 mt-2")

                    ui.label("点击创建新笔记").classes("text-gray-500 text-sm")
            return card

        async def create_card(note: Note, attachment_count: int) -> ui.card:
            with ui.card().classes(
                    "shadow-lg rounded-xl border border-gray-200 bg-white overflow-hidden") as card:
                with ui.column().classes("w-full p-4"):  # 增加内边距，移除冗余 flex（ui.column 已是 flex）
                    # [step] ai: ui.row() 默认使用 display: flex; flex-wrap: wrap（允许换行），所以需要 flex-nowrap
                    with ui.row().classes(
                            "w-full items-center justify-between mb-3 whitespace-nowrap flex-nowrap"):
                        # 允许收缩，但最小为 0，配合 truncate 实现弹性截断
                        label = ui.label(note.title)
                        label.classes("text-lg font-semibold text-gray-800 truncate min-w-0")
                        label.tooltip(note.title)
                        # 固定不换行、紧凑显示
                        # label = ui.label(str(note.created_at))
                        # label.classes("text-sm text-gray-500 whitespace-nowrap flex-shrink-0")
                        # label.tooltip(str(note.created_at))

                    # todo: 依旧存在 bug，文本每行长一点，浏览器也没有放大，就会出现不会自动延展动态换行的情况
                    #       很特别，第二天我发现，是 markdown 内容的原因，感觉和特殊字符有关
                    lines = 3
                    line_height = 1.5
                    total_height = (lines + 1) * line_height  # 多加一行才行，这个 total_height 是固定了高度
                    with ui.element("div").style(f"""
                         height: {total_height}em;
                         overflow: hidden;
                         display: flex;
                         align-items: flex-start;
                         justify-content: flex-start;
                     """):
                        # ui.markdown(note.content) # markdown 会渲染一些东西，摘要页面原始一点比较好
                        ui.label(note.content).style("""
                            display: -webkit-box;
                            -webkit-line-clamp: {lines};
                            -webkit-box-orient: vertical;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            line-height: {line_height};
                            word-break: break-word;
                        """.format(lines=lines, line_height=line_height))
                        """使用 -webkit-line-clamp 实现真正的多行省略

                        效果说明：
                        - 超出 3 行 的内容会被隐藏
                        - 最后一行末尾会自动显示 真实的 ... 省略号
                        - 不需要额外遮罩层，干净简洁

                        word-break: break-word 防止 Markdown 中有 长无空格字符串（如 URL），可能会撑破容器。

                        """

                    # 底部行：附件数量 + 查看按钮
                    with ui.row().classes(
                            "w-full items-center justify-between mt-3 pt-3 border-t border-gray-100"):
                        label = ui.label(f"{attachment_count} 个附件 · {str(note.created_at)}")
                        label.classes("text-sm text-gray-600 whitespace-nowrap flex-shrink-0")
                        eye = ui.button(icon="mdi-eye-outline", on_click=partial(go_get_note, note_id=note.id))
                        eye.props("flat round dense").classes("text-gray-500 hover:text-blue-600")
                        """Quasar props + Tailwind hover 效果"""
            return card

        # ====== build ui ====== #

        # todo: 能否实现先渲染，数据到了再更新呢？

        # [clear + rebuild 可能存在的问题](https://lxblog.com/qianwen/share?shareId=4f727c46-84a9-436d-801b-2ccfac158908)
        # - 视觉闪烁、位置跳动
        # - 用户快速点击时可能触发多次异步操作（竞态条件）

        with table:
            search_filter = None
            if search_content:
                search_filter = Addict(search_content=search_content)

            async with NoteService() as service:
                result = await service.count_note(search_filter=search_filter)
                total_pages = max(1, math.ceil(result.unwrap() / PAGE_SIZE))

                notes = await service.get_notes(page=current_page, search_filter=search_filter)

            with ui.grid(columns=3).classes("w-full gap-4"):
                async with AttachmentService() as attachment_service:
                    for note in notes:
                        result = await attachment_service.count_attachment(note.id)
                        attachment_count = result.unwrap()
                        await create_card(note, attachment_count)

                # [2025-11-14] 这个高度会动态变化，不好处理
                # await create_add_note_card()

            # 分页控件
            with ui.row().classes("w-full justify-center items-center gap-2 mt-2"):
                prev_btn = ui.button(icon="mdi-arrow-left").classes(
                    "px-4 py-2 text-gray-800 "
                    "rounded-lg shadow-sm border border-gray-300 "
                    "transition duration-150 ease-in-out"
                ).props("flat dense")

                # [note] [2025-11-14] 由于每次点击按钮，整个 table 会被清空，所以节流操作无意义
                # prev_btn_rate_limter = RateLimiter(1)
                async def on_prev_btn_click():
                    # if not prev_btn_rate_limter.allow():
                    #     ui.notify(f"操作太频繁，请稍后再试", type="negative")
                    #     return

                    next_page = current_page - 1
                    if next_page < 1:
                        return

                    nonlocal table
                    table.clear()
                    table = await build_table(table, current_page=next_page, search_content=search_content)

                prev_btn.on_click(on_prev_btn_click)

                page_label = ui.label(f"Page {current_page} of {total_pages}").classes(
                    "text-gray-700 font-medium px-3 py-2 "
                    "bg-white rounded-lg shadow-sm "
                    "border border-gray-200"
                )

                next_btn = ui.button(icon="mdi-arrow-right").classes(
                    "px-4 py-2 text-gray-800 "
                    "rounded-lg shadow-sm border border-gray-300 "
                    "transition duration-150 ease-in-out"
                ).props("flat dense")

                # next_btn_rate_limter = RateLimiter(1)
                async def on_next_btn_click():
                    # if not next_btn_rate_limter.allow():
                    #     ui.notify(f"操作太频繁，请稍后再试", type="negative")

                    next_page = current_page + 1
                    if next_page > total_pages:
                        return

                    nonlocal table
                    table.clear()
                    table = await build_table(table, current_page=next_page, search_content=search_content)

                next_btn.on_click(on_next_btn_click)

        return table

    # [note] 由于 nicegui 简单但是也复杂，任何技术妄图说掌握是不可能的，为此我选择按照个人理解先搭建骨架
    with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl") as content:
        # [step] 前往 tailwind css 官网搜索，解决元素分布问题
        # [css note] flex 似乎必须添加，因为 items-center justify-between 都需要基于 flex，w-full 的目的是继承父容器宽度，这样直接展开了
        with ui.row().classes("w-full flex items-center justify-between"):
            ui.label("我的笔记").classes("text-xl font-bold text-gray-900")

            ui.space()

            with ui.row():
                # [step] ai: ui.input(placeholder="搜索笔记...") 能不能在左侧添加一个搜索icon
                with ui.input(placeholder="搜索笔记...") as search_input:
                    # search_input.classes("border rounded-lg") # 四周有线，四角椭圆
                    with search_input.add_slot("prepend"):
                        ui.icon("mdi-magnify").classes("ml-2")
                    with search_input.add_slot("append"):
                        clear_icon = ui.icon("close", size="18px").classes(
                            "mr-2 cursor-pointer "
                            "text-gray-400 "
                            "rounded-lg hover:bg-gray-200 "
                        )

                        async def on_click():
                            if not search_input.value:
                                return
                            search_input.value = ""
                            nonlocal table
                            table.clear()
                            await build_table(table, search_content=search_input.value)

                        clear_icon.on("click", on_click)

                # 监听回车键
                async def on_enter_pressed():
                    logger.debug("on_enter_pressed called")
                    nonlocal table
                    table.clear()
                    await build_table(table, search_content=search_input.value)

                # todo: 新增一个搜索创建时间和更新时间的选项
                search_input.on("keydown.enter", on_enter_pressed)

                # [question] value 能否类似 django 的 choices，一个是指代符号，一个是 human text
                def on_change():
                    # todo: 实现 value 切换导致下面的 table 刷新（说起 table，nicegui 有 table 扩展库诶）
                    # todo: 尝试使用 bind_value 函数 + 使用那个双向绑定库
                    pass

                select = ui.select(["全部笔记", "最近编辑", "有附件"], value="全部笔记", on_change=on_change)
                select.classes("min-w-24")
                # todo: 暂且隐藏该功能
                select.visible = False

        # [note] 经验告诉我，选择 ui.row 比较好，而不是 ui.grid
        # [note] grid 整个偏左，最开始设置 mx-auto 但是不太好，w-full 直接动态展开，还不错

        table = ui.column().classes("w-full")
        await build_table(table)

        # table = ui.grid(columns=3).classes("w-full")
        # await build_table(table)


@app.on_startup
async def startup_event():
    logger.debug("app - startup")
    await init_db()
    await cleanup.start()


@app.on_shutdown
async def shutdown_event():
    logger.debug("app - shutdown")
    await cleanup.stop()


if __name__ in {"__main__", "__mp_main__"}:
    # [knowledge] 在创建 NiceGUI 应用时保留 FastAPI 的文档路由（不要让 nicegui 接管根路径）
    app.mount("/api", fastapi_app)

    props = Addict()
    props.title = "笔记管理系统"
    props.host = "localhost"

    # todo: 添加 static 路由和文件，解决 cdn 需要挂 vpn 的问题


    if not getattr(sys, "frozen", False):
        import os
        import argparse

        # NiceGUI 使用 webview 或内置 CEF 启动原生窗口，可通过下列环境变量开启底层日志
        os.environ["PYWEBVIEW_LOG"] = "debug"
        os.environ["CEFPYTHON_LOG_SEVERITY"] = "info"

        # [pyinstaller 之程序立即退出的根本原因](https://lxblog.com/qianwen/share?shareId=a439527a-cf57-4902-9cca-0cc1172191d3)
        parser = argparse.ArgumentParser()
        parser.add_argument("--native", action="store_true", default=False)
        args = parser.parse_args()

        props.native = args.native
        props.window_size = None
        if props.native:
            props.window_size = (1200, 900)

        ui.run(
            title=props.title,
            host=props.host,
            port=8000,
            native=props.native,
            window_size=props.window_size,
            uvicorn_reload_includes="*.py, *.js, *.json"
        )
    else:
        logger.debug("nicegui-pack application startup!")
        port = native.find_open_port()
        logger.debug("启动端口：{}", port)
        ui.run(
            title=props.title,
            host=props.host,
            port=port,
            native=True,
            window_size=(1200, 900),
            fullscreen=False,
            reload=False
        )
