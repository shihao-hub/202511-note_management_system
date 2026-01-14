import logging
import math
from functools import partial
from typing import List, Dict, Tuple

import pyperclip
from nicegui import ui

from models import Note
from views import HeaderView, View, Controller, build_softmenu
from services import NoteService, AttachmentService, UserConfigService
from log import logger

# [note] v1.1.3 版已完成，本文件是在它之后开发的。开始考虑页面样式和代码逻辑如何组织了。
#        1. **ui 界面通过 Pixso AI 生成并截图发送给千问**：`nicegui如何实现？左侧列表右侧正文，类似 obsidian 那样`
#        2. 该界面对目前的我而言，还算理想，比我第一版扣子生成的好多了（AI 是炼金术吧、提示词是咒语吧）
#        3. **只需要使用 nicegui 基础组件和 tailwind css**（需要系统学习）即可实现不错的页面了！前端开发美观才是关键之一！
#        4. **数据库表设计**也是可以让 ai 设计的，但是终究需要优秀的提示词
#        5. 可以尝试让 **ai 根据你的需求生成提示词**，你再去问 ai 让它生成设计图/网页
#        6. 直接找网上的 ui 界面（单一组件元素也可以）**让支持多模态的 ai 分析并生成**（比如用 tailwind css 生成）
#        7. **审美不行**，建议任何功能，优先找 nicegui 自带组件，然后找 quasar，接着让 ai 找现成方案，最后才是让 ai 自己写。
#        8. todo: 需要实现笔记标记功能，先考虑置顶功能吧！


# todo: 拦截 nicegui 自带的错误 page，要求错误的时候，header 依旧保留

# todo: 此处差不多等于重新开发了一个页面了，所以配置项得好好设计一下了！建议直接从 configs.lua 文件中导入！
#       这个页面我真的满意，太舒服了，ai 设计好截图发给 ai，接下来我微调骨架，然后写交互和后端逻辑即可！

# todo: 一些回调相关逻辑，可以考虑部分使用 js 实现，而不是 python 代码，这样一来软件不需要重新编译了！

# todo: 能不能使用 nicegui 实现一个兼容 PC 和移动端的文件存储系统？能方便上传、预览、下载、删除就行（当然需要登录系统、权限分层）


class HyperlinkNoteController(Controller["HyperlinkNoteView"]):
    async def list_note_and_attachment_count(self, page: int | None = None) -> List[Tuple[Note, int]]:
        res = []
        async with NoteService() as note_service:
            notes = await note_service.get_notes(page=page)
        for note in notes:
            async with AttachmentService() as attachment_service:
                attachment_count = (await attachment_service.count_attachment(note.id)).unwrap()
                res.append((note, attachment_count))
        return res

    async def get_total_pages(self):
        async with UserConfigService() as user_config_service:
            page_size = await user_config_service.get_page_size()
        async with NoteService() as note_service:
            count_note = (await note_service.count_note()).unwrap()
        return math.ceil(count_note / page_size)

    async def choose_note(self, note: Note):
        logger.debug("[choose_note] note.id: {}", note.id)
        self.view.title_input.value = note.title
        self.view.content_input.value = note.content


class HyperlinkNoteView(View["HyperlinkNoteController"]):
    controller_class = HyperlinkNoteController

    async def _pre_initialize(self):
        await super()._pre_initialize()
        ui.add_css("""
        .nicegui-upload-scrollable .q-uploader__list {
            max-height: 120px;       /* 最大高度 */
            overflow-y: auto;        /* 垂直滚动 */
            padding-right: 8px;      /* 可选：为滚动条留空间 */
        }
        """)

    async def _initialize(self):
        # 单纯构建左侧列表右侧正文的面板
        # with ui.left_drawer(fixed=False):
        #     with ui.list().classes("w-full"):
        #         with ui.card().classes("w-full"):
        #             ui.button("项A")
        #         with ui.card().classes("w-full"):
        #             ui.button("项B")

        def copy_note(text):
            pyperclip.copy(text)
            ui.notify("复制到剪切板成功", type="positive")

        with ui.row().classes("w-full h-[750px] bg-gray-50"):  # h-screen h-[750px]
            # --- 左侧栏
            """
            [ 外层容器：h-full, flex flex-col ]
            │
            ├── [ scroll_area: flex-1 → 自动占满中间剩余空间，可滚动 ]
            │   ├── note card 1
            │   ├── note card 2
            │   └── ...
            │
            └── [ pagination: mt-auto → 固定在底部，不滚动 ]
            """
            # [note] border border-red-500 / bg-blue-200 可以用来调试使用，查看元素大小
            with ui.column().classes("w-80 h-full bg-white border-r border-gray-200 p-0 "):
                # --- 列表容器
                with ui.card().classes("w-full h-full flex flex-col p-0 gap-0"):
                    # --- 顶部工具栏：搜索框 + 菜单按钮
                    with ui.row().classes("w-full p-2 items-center gap-2 border-b border-gray-200"):
                        # --- 搜索框
                        self.search_input = ui.input(placeholder="搜索笔记...").classes("flex-1 text-sm").props("dense")
                        with self.search_input.add_slot("prepend"):
                            ui.icon("mdi-magnify").classes("ml-2")
                        with self.search_input.add_slot("append"):
                            clear_icon = ui.icon("close", size="18px").classes(
                                "mr-2 cursor-pointer "
                                "text-gray-400 "
                                "rounded-lg hover:bg-gray-200 "
                            )
                        # --- 菜单按钮（用图标按钮节省空间）
                        # todo: 此处将添加很多功能，太多了就加个更多选项打开个 dialog 折中一下吧，比如：
                        #       1. 分页按钮（上一页下一页）
                        #       2. 配置项页面
                        #       3. 按类别筛选功能
                        #       4. 排序功能
                        #       5. 全量导出/导出当前选中的文件
                        #       注意，菜单默认的显然也有点丑，再让 ai 帮帮忙吧！比如设计右键样式~
                        #       more_vert 也是 ai 生成的，真不错啊，见了世面
                        with ui.button(icon="more_vert").props("flat dense"):
                            pass  # 可绑定菜单逻辑

                    # --- 笔记滚动区域
                    with ui.scroll_area().classes("w-full flex-1 p-0 "):
                        with ui.column().classes("w-full") as self.note_container:
                            await self.show_notes(current_page=None, height="")

                        # current_page=None, height="" -> 取消分页（暂时取消，因为目前实现的问题太多！）
                        # .props("input") 刚好，但是默认更好看点吧，可惜会展开，建议最大页数 5 的时候用默认的，大于用现在的
                        # with ui.row().classes("w-full justify-center py-2 mt-auto"):
                        #     p = ui.pagination(1, await self.controller.get_total_pages(),
                        #                       direction_links=True,
                        #                       on_change=lambda e: self.show_notes(current_page=e.value)).props("input")

            # --- 右侧主内容区
            with ui.column().classes("flex-1 p-6 overflow-y-auto"):
                with ui.row().classes("w-full justify-between"):
                    ui.label("编辑笔记").classes("text-xl font-bold mb-4")

                    # --- 操作按钮
                    with ui.row().classes("mb-6 gap-x-0"):
                        # todo: Unicode 字体图标足以啊！压根不需要找图标了，我的天，好东西
                        ui.button("💾 保存", color="positive").classes("mr-2")
                        ui.button("🗑️ 删除", color="negative").classes("mr-2")
                        ui.button("👁️ 预览", color="primary")

                # --- 标题输入
                with ui.row().classes("w-full items-center mb-4"):
                    ui.label("标题").classes("font-medium w-20")
                    self.title_input = ui.input(value="【示例数据】项目会议记录").classes("flex-1")
                    # "📋 复制",
                    ui.button(icon="content_copy").on_click(partial(copy_note, self.title_input.value)) \
                        .props("flat dense color=grey").classes("text-[10px]")

                # --- 内容区域
                with ui.row().classes("w-full items-center mb-4"):
                    ui.label("内容").classes("font-medium w-20")
                    self.content_input = ui.textarea(
                        value="【示例数据】2023年6月15日 项目进度会议\n\n与会人员：\n- 张经理\n- 李工程师\n- 王设计师\n- 刘测试\n\n会议内容：\n1. 项目进度回顾\n  - 前端界面开发完成80%",
                        placeholder="请输入笔记内容...",
                    ).classes("flex-1 min-h-40").props("rows=14")
                    ui.button(icon="content_copy").on_click(partial(copy_note, self.content_input.value)) \
                        .props("flat dense color=grey").classes("text-[10px]")

                # --- 提示信息
                ui.label("💡 提示：您可以粘贴图片到内容区域，系统将自动上传作为附件") \
                    .classes("w-full text-sm text-gray-600 bg-blue-50 p-3 rounded-md text-center")

                # --- 附件区域
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("附件 (3)").classes("font-medium")
                    ui.button("📎 管理附件", color="gray").classes("px-3 py-1")

                # --- 图片附件预览
                # with ui.row().classes("gap-4"):
                #     for i in range(3):
                #         ui.image(f"https://picsum.photos/seed/{i}/300/200").classes("w-60 h-32 object-cover rounded")

                # --- 添加图片上传功能（可选）
                with ui.row().classes("w-full mt-4 justify-center"):
                    ui.upload(label="上传附件").on_upload(lambda e: print(e.content)).classes("w-full")

    async def show_notes(self, current_page: int | None = 1, width: str = "w-[286px]", height: str = "h-[153px]"):
        self.note_container.clear()
        with self.note_container:
            note_and_attachment_count_list = await self.controller.list_note_and_attachment_count(
                page=current_page)
            for note, attachment_count in note_and_attachment_count_list:
                summary = note.content[:50]
                # todo: 解决固定 px 的弊端，响应式才正确，w 暂时解决不了，但是 h 呢？还是说可能需要涉及计算...
                # todo: 分页组件如何才能固定在一个位置啊？其实也不能说 nicegui 不适合复杂项目，
                #       而是如果真要复杂项目你至少懂前端吧？那如果懂前端，为什么要使用 nicegui？！
                #       所以我觉得，nicegui 本就不是给复杂交互设计的，而是你个工科审美人，
                #       看着摆放组件位置，实现你需要的功能就行了！
                with ui.card().classes(
                        f"{width} {height} border-b hover:bg-gray-100 cursor-pointer transition-colors p-4 "
                ) as note_card:
                    # todo: tailwind 与 css 原理必须找视频看一下，这纯 ai 炼金加个人瞎猜啊，这边 w-64 刚好正常，w-full 却导致水平溢出...
                    with ui.row().classes("w-full items-start gap-0"):
                        ui.label(note.title).classes("font-semibold text-lg flex-1 truncate") \
                            .tooltip(note.title)
                    ui.label(summary).classes("text-sm text-gray-600 mt-1 truncate w-full") # .tooltip(summary)
                    with ui.row().classes("w-full text-xs text-gray-500 mt-1 justify-between"):
                        with ui.row().classes("gap-x-0 items-center"):
                            ui.icon("calendar_today").classes("mr-1")
                            ui.label(str(note.updated_at)).tooltip("上次编辑时间")
                        with ui.row().classes("gap-x-0 items-center"):
                            ui.icon("attach_file").classes("ml-2 mr-1")
                            ui.label(f"{attachment_count}个附件")
                    note_card.on("click", partial(self.controller.choose_note, note))


@ui.page("/note/index")
async def page_get_hyperlink_note():
    ui.add_head_html("""
    <link rel="stylesheet" href="/static/materialdesignicons.min.css" />
    """)

    with ui.header().classes("bg-white shadow-sm py-3") as header:
        with ui.row().classes("w-full flex justify-between items-center px-2 sm:px-4 md:px-6"):
            with ui.row().classes("items-center gap-x-1"):
                build_softmenu()
                ui.label("笔记管理系统").classes("text-xl font-bold text-gray-800")

            ui.space()

            with ui.row().classes("flex justify-between items-center"):
                pass
    await HyperlinkNoteView.create()
