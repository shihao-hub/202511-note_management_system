from functools import partial

import pyperclip
from nicegui import ui
from nicegui.events import GenericEventArguments, ValueChangeEventArguments
from fastapi.requests import Request

from models import Note, Attachment, NoteDetailRenderTypeEnum, NoteTypeMaskedEnum
from utils import refresh_page, register_find_button_and_click, go_main, go_add_note, go_edit_note, go_get_note
from services import NoteService, AttachmentService, UserConfigService
from views import View, Controller, delete_note, HeaderView, build_footer, see_attachment
from settings import dynamic_settings, ENV
from log import logger

@ui.page("/get_note", title="笔记详情")
async def page_get_note(request: Request, note_id: int, notify_from: str = None):
    # [question] 新增 page 导致点击时页面需要刷新，有没有更流畅的办法呢？有的，定义一个 div，然后通过调用 clear 方法，重新构建 div

    await HeaderView.create()
    await build_footer()

    # if notify_from == "add_note":
    #     # timer 会在页面加载完毕后才开始计时
    #     ui.timer(0, lambda: ui.notify("保存笔记成功！", type="positive"), once=True)

    def copy_note(text):
        pyperclip.copy(text)
        ui.notify("复制到剪切板成功")

    async with UserConfigService() as service:
        render_type = await service.get_value("note_detail_render_type")
        autogrow = await service.get_value("note_detail_autogrow")

    # render_type = NoteDetailRenderTypeEnum.MARKDOWN.value
    logger.debug("render_type: {}", render_type)
    logger.debug("autogrow: {}", autogrow)

    async with NoteService() as service:
        result = await service.get(note_id)
        note = result.unwrap()

    logger.debug(f"note_id: {note_id}")

    with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl py-6"):
        with ui.row().classes("w-full items-center gap-x-3 mb-6"):
            arrow_left_btn = ui.button(icon="mdi-arrow-left", on_click=go_main)
            arrow_left_btn.props("flat round").classes("text-gray-700 hover:bg-gray-100")
            ui.label("笔记详情").classes("text-xl font-bold text-gray-900")

            register_find_button_and_click("Escape", arrow_left_btn.id)

        card = ui.card().classes("w-full rounded-xl shadow-md border border-gray-200 overflow-hidden")
        with card, ui.column().classes("w-full px-5 py-6"):
            # 标题行
            with ui.row().classes("w-full items-center justify-between mb-4 flex-nowrap"):
                title = ui.label(note.title).classes("text-gray-900 font-bold text-2xl leading-tight")
                # todo: 能否设置都能选中复制？好痛苦，浏览器真是个伟大的技术发明，多年的迭代，真复杂啊
                # [textarea readonly 情况下，无法选中复制，label 也是](https://lxblog.com/qianwen/share?shareId=b5a8b90e-bef0-4605-8921-05de37afd4bd)
                title.style("user-select: text; cursor: text;")
                title.classes("truncate flex-shrink min-w-0")  # 允许收缩到小于内容宽度
                title.tooltip(note.title)

                # todo: copy_btn 改为 menu（选项弹窗也可以），支持复制、修改渲染样式等
                # todo: 监听 esc 键，点击屏幕的返回键

                async def show_option_dialog():
                    with (
                        ui.dialog() as dialog,
                        ui.card().classes("min-w-48 max-w-64 p-4"),
                        ui.column().classes(
                            "w-full flex items-center justify-between "
                            "p-4 border-2 border-dashed rounded-sm "
                        )
                    ):
                        # [2025-11-15] 不需要这个，但是需要支持详情页面标题支持复制
                        # copy_btn = ui.button(icon="mdi-content-copy")
                        # copy_btn.classes("text-[10px]").props("flat dense color=grey")
                        # copy_btn.on("click", partial(copy_note, text=f"{title.text}\n\n{get_content_text()}"))
                        # copy_btn.tooltip("复制标题和正文")

                        # todo: 抽成函数
                        # todo: select 和 profile 这个语法还是太乱了，还是需要入门前端才行
                        #       任何一门技术还得是专精方向学习才行，虽然有些工具也有部分能力，但是还是太窄了

                        logger.debug("render_type: {}, autogrow: {}", render_type, autogrow)
                        with ui.row().classes("w-full flex items-center justify-between"):
                            ui.label("渲染模式：").tooltip("笔记正文的渲染模式")

                            async def on_change(e: ValueChangeEventArguments):
                                if e.value == render_type:
                                    return
                                async with UserConfigService() as service_:
                                    await service_.set_value("note_detail_render_type", e.value)
                                dialog.close()
                                await refresh_page()

                            ui.select(NoteDetailRenderTypeEnum.values(), value=render_type,
                                      on_change=on_change).classes("flex-grow")

                        with ui.row().classes("w-full flex items-center justify-between"):
                            ui.label("自动增长：").tooltip("笔记正文是否自动伸长")

                            async def on_autogrow_change(e: ValueChangeEventArguments):
                                if e.value == autogrow:
                                    return
                                async with UserConfigService() as service_:
                                    await service_.set_value("note_detail_autogrow", e.value)
                                dialog.close()
                                await refresh_page()

                            ui.select({True: "是", False: "否"}, value=autogrow, on_change=on_autogrow_change).classes(
                                "flex-grow")

                    dialog.open()

                menu_btn = ui.button(icon="menu", on_click=show_option_dialog)
                menu_btn.classes("text-[12px]").props("flat dense color=grey")
                menu_btn.classes("flex-shrink-0")  # 禁止收缩

            # 内容文本区
            content_container = ui.element("div").classes("w-full ")
            if not autogrow:
                content_container.classes("max-h-64 overflow-y-auto ")  # 64 好，可以显示编辑按钮
            else:
                pass

            with content_container:
                if render_type == NoteDetailRenderTypeEnum.MARKDOWN.value:
                    content = ui.markdown(note.content).classes("w-full")

                    def get_content_text():
                        return content.content

                    # 自定义 Markdown 字体大小等样式
                    ui.add_css("""
                        .nicegui-markdown h1 { font-size: 1.6rem; }
                        .nicegui-markdown h2 { font-size: 1.4rem; }
                        .nicegui-markdown h3 { font-size: 1.25rem; }
                        .nicegui-markdown h4 { font-size: 1.1rem; }
                        .nicegui-markdown h5 { font-size: 1.0rem; }
                        .nicegui-markdown h6 { font-size: 0.9rem; }
                    """)

                    # ui.markdown 的链接需要 new_tab
                    ui.add_head_html("<script>{0}</script>".format(ENV.get_template("open_external_link.js").render()))
                else:
                    content = ui.label(note.content).classes("w-full").style("white-space: pre-wrap")

                    def get_content_text():
                        return content.text

            content.style("user-select: text; cursor: text;")

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
                    button = ui.button("查阅附件", on_click=partial(see_attachment, note_id=note_id, detail_page=True))
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
                    edit_button = ui.button("编辑", icon="mdi-square-edit-outline", on_click=edit_on_click)
                    edit_button.props("flat dense").classes("text-blue-600")

                    register_find_button_and_click("o", edit_button.id, is_ctrl=True)

                    delete = ui.button("删除", icon="mdi-trash-can-outline",
                                       on_click=partial(delete_note, note_id=note_id, notify_from="get_note__delete"))
                    delete.props("flat dense color=red").classes("text-red-600 hover:text-red-700")
