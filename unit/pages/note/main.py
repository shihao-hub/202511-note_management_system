import math
import re
import cProfile
import pstats
from functools import partial
from typing import Tuple, Dict, List, Literal, Callable, Sequence
from datetime import datetime

from nicegui import ui
from nicegui.events import GenericEventArguments, ValueChangeEventArguments
from fastapi.requests import Request

from models import Note, NoteTypeMaskedEnum
from utils import (
    show_config_dialog, go_edit_note, go_get_note, refresh_page,
    get_async_runner, RateLimiter, print_interval_time, IntervalTimer,
    extract_urls, extract_bracketed_content
)
from services import NoteService, AttachmentService, UserConfigService, TagService
from views import View, Controller, delete_note, HeaderView, build_footer
from log import logger


class PageMainController(Controller["PageMainView"]):
    def __init__(self, view: "PageMainView"):
        super().__init__(view)
        self.search_input_rate_limter = RateLimiter(cooldown_seconds=2)

    async def get_current_page(self):
        async with UserConfigService() as service:
            return await service.get_value("current_page")

    async def set_current_page(self, current_page: int):
        async with UserConfigService() as service:
            return await service.set_value("current_page", current_page)

    async def on_eye_btn_click(self, note_id: int):
        async with NoteService() as service:
            await service.incr_visit(note_id)
        go_get_note(note_id=note_id)

    async def get_tag_select(self):
        async with UserConfigService() as service:
            return await service.get_value("tag_select")

    async def on_clear_icon_click(self):
        logger.debug("[on_clear_icon_click] start")
        if not self.view.search_input.value:
            return
        self.view.search_input.value = ""
        async with UserConfigService() as service:
            await service.set_value("search_content", self.view.search_input.value)
        await self.view.rebuild_table()

    async def new_generate_tags(self):
        # [2025-12-11] make it work! -> 将 Tag 存储于 Tag 表中，并更新 note_id 字段
        # 1. select id, title from note
        # 2. 提取标签并创建标签，得到 Tag 表数据，但是这次需要添加 note_id 字段
        # 完毕，旧数据兼容可以通过这样实现，但是更简单的办法是删除此处的功能，通过脚本去处理数据库数据...
        pass

    async def generate_tags(self):
        async with NoteService() as note_service:
            titles = await note_service.get_titles()

        extracted_tags = set()
        for title in titles:
            extracted_tags.update(extract_bracketed_content(title))
        logger.debug("extracted_tags: {}", extracted_tags)
        invalid_tags = set()
        has_new_tag = False
        async with TagService() as tag_service:
            for tag in extracted_tags:
                # 长度大于 6 生成失败（这个长度是六个中文字符，在 UTF-8 编码下：一个常见的中文汉字通常占用 3 个字节）
                if len(tag.encode("utf-8")) > 18:
                    invalid_tags.add(tag)
                    continue
                if await tag_service.create_tag_if_not_exists(tag):
                    has_new_tag = True
        # logger.debug("invalid_tags: {}", invalid_tags)
        if invalid_tags:
            ui.notify("存在超出 6 个字符的无效标签，已忽略", type="warning")

        if has_new_tag:
            self.view.tag_select.build_select_ui.refresh()
            ui.notify("生成标签成功", type="positive")
        else:
            ui.notify("生成标签成功，但是没有新标签", type="positive")

    async def on_search_input_keydown_enter(self):
        if not self.search_input_rate_limter.allow():
            ui.notify(f"操作太频繁，请稍后再试", type="negative")
            return
        await self.set_search_content(self.view.search_input.value)
        await self.view.rebuild_table()

    async def on_select_change(self, e: ValueChangeEventArguments):
        # todo: 实现 value 切换导致下面的 table 刷新（说起 table，nicegui 有 table 扩展库诶）
        # todo: 尝试使用 bind_value 函数 + 使用那个双向绑定库？

        async with UserConfigService() as user_config_service:
            await user_config_service.set_value("home_select_option", e.value)

        await self.view.rebuild_table()

    async def get_home_select_option(self):
        # todo: 由于这个可能会被 select 的
        async with UserConfigService() as user_config_service:
            return await user_config_service.get_value("home_select_option")

    async def get_search_content(self) -> str:
        async with UserConfigService() as user_config_service:
            search_content = await user_config_service.get_value("search_content")
        return search_content or ""

    async def set_search_content(self, search_content: str):
        async with UserConfigService() as user_config_service:
            await user_config_service.set_value("search_content", search_content)

    async def on_search_input_change(self, e: ValueChangeEventArguments):
        # 注意，目前是直接尝试刷数据库，只要搜索框内容变了就刷数据库
        # 而且也正是基于这一点，搜索框内容我没有传递，而是直接读数据库
        # await self.set_search_content(e.value)
        # [2025-12-01] 按下回车的时候设置比较好
        pass

    async def get_note_number(self):
        async with UserConfigService() as user_config_service:
            note_type = await user_config_service.get_value("home_select_option")
        async with NoteService() as note_service:
            return (await note_service.count_note({"note_type": note_type})).unwrap()

    async def refresh_note_number_label(self):
        self.view.note_number_lable.text = f"（共 {await self.get_note_number()} 条）"


class PageMainView(View["PageMainController"]):
    controller_class = PageMainController

    async def _pre_initialize(self):
        await super()._pre_initialize()

    async def _post_initialize(self):
        await super()._post_initialize()

    async def _initialize(self) -> None:
        with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl") as self.content:
            with ui.row().classes("w-full flex items-center justify-between"):
                with ui.row().classes("flex items-center justify-center gap-x-0"):
                    ui.label("我的笔记").classes("text-xl font-bold text-gray-900")
                    # --- 笔记数量
                    self.note_number_lable = ui.label(f"（共 {await self.controller.get_note_number()} 条）") \
                        .classes("text-sm text-gray-500 ml-2")
                ui.space()
                with ui.row().classes("items-center"):
                    # --- 搜索笔记
                    with ui.input(placeholder="搜索笔记...",
                                  on_change=self.controller.on_search_input_change) as search_input:
                        self.search_input = search_input
                        with search_input.add_slot("prepend"):
                            ui.icon("mdi-magnify").classes("ml-2")
                        with search_input.add_slot("append"):
                            clear_icon = ui.icon("close", size="18px").classes(
                                "mr-2 cursor-pointer "
                                "text-gray-400 "
                                "rounded-lg hover:bg-gray-200 "
                            )
                            clear_icon.on("click", self.controller.on_clear_icon_click)
                        search_input.value = await self.controller.get_search_content()
                        search_input.on("keydown.enter", self.controller.on_search_input_keydown_enter)

                    # --- 笔记筛选
                    ui.select(NoteTypeMaskedEnum.to_dict(),
                              value=await self.controller.get_home_select_option(),
                              on_change=self.controller.on_select_change).classes("min-w-24")

                    # --- 标签筛选
                    # 实践和测试发现，将 class TagSelect 移出当前作用域，build_select_ui.refresh() 会导致元素消失...
                    # 但是再次测试发现，又一切正常了，奇怪...
                    self.tag_select = await self.TagSelect.create(self)
                    self.tag_select.build_select_ui()

                    # --- 时间筛选
                    class TestTimeValue:
                        def __init__(self):
                            self.value = datetime.now()

                    test_time_value = TestTimeValue()
                    with ui.button(icon="edit_calendar").classes("").props("flat dense") as date_icon:
                        with ui.menu().props("no-parent-event") as menu:
                            ui.date().bind_value(test_time_value)
                            date_icon.on("click", menu.toggle)

            # todo: 将 rebuild_table 考虑拆分，按上面的样子平铺开来（即尽量做到骨架由当前函数构建，血肉拆分出去）
            self.table = ui.column().classes("w-full")
            await self.rebuild_table()

    class TagSelect:
        """封装成类，解决 @ui.refreshable 无法修饰异步函数的问题

        Details:
            1. 通过异步类工厂函数创建，其他方式创建是错误的（这一点似乎无法从语法层面限制）
            2. 对外提供被 @ui.refreshable 的 build_select_ui 方法，它是同步方法
            3. ui.select 值的刷新是通过调用 build_select_ui.refresh() 实现的
            4. self.tags 即当前实例变量是通过守护线程将异步转同步实现的（是否是最佳实践存疑）
            5. 可能的最佳实践：将 self.tags 与 ui.select 通过值的双向绑定实现动态刷新

        """

        @classmethod
        async def create(cls, view: "PageMainView", *args, **kwargs):
            instance = cls()
            await instance._initialize(view, *args, **kwargs)
            return instance

        async def _initialize(self, view: "PageMainView", *args, **kwargs):
            self.view = view
            self.tags = []

        async def _refresh_tag(self):
            self.tags.clear()
            self.tags.append("(null)")
            async with TagService() as tag_service:
                db_tags = await tag_service.get_tags(order_by="name")
                db_tags.sort(key=len)
                self.tags.extend(db_tags)

        def _sync_refresh_tag(self):
            get_async_runner().run(self._refresh_tag())

        async def _on_value_change(self, e: ValueChangeEventArguments):
            async with UserConfigService() as service:
                await service.set_value("tag_select", e.value)
            await self.view.rebuild_table()

        async def _clear_tags(self):
            async with TagService() as service:
                await service.delete_all()
            async with UserConfigService() as user_config_service:
                await user_config_service.set_value("tag_select", "(null)")
            self.build_select_ui.refresh()
            ui.notify("清空标签成功", type="positive")

        def _get_tag_select_value(self):
            value = get_async_runner().run(self.view.controller.get_tag_select())
            if value not in self.tags:
                value = "(null)"
            return value

        @ui.refreshable
        def build_select_ui(self):
            logger.debug("[TagSelect:build_select_ui] start")
            self._sync_refresh_tag()
            value = self._get_tag_select_value()
            with ui.select(self.tags, value=value).classes("min-w-24") as select, ui.context_menu():
                select.on_value_change(self._on_value_change)

                # [双向绑定和单向绑定有啥区别](https://www.qianwen.com/share?shareId=30196424-f58d-45b4-871c-1237b3aba1a1)
                # 实践发现，绑定的是 value，options 没法绑定
                # select.bind_value_from()

                ui.menu_item("生成标签", on_click=self.view.controller.generate_tags).tooltip("扫描所有笔记的标题")

                ui.separator()
                ui.menu_item("清空标签", on_click=self._clear_tags).tooltip("清空现在生成的所有标签")

    async def _create_table_card(self, note: Note, attachment_count: int) -> ui.card:
        def create_abstract_element():
            """使用 -webkit-line-clamp 实现真正的多行省略

            效果说明：
            - 超出 3 行 的内容会被隐藏
            - 最后一行末尾会自动显示 真实的 ... 省略号
            - 不需要额外遮罩层，干净简洁

            word-break: break-word 防止 Markdown 中有 长无空格字符串（如 URL），可能会撑破容器。

            """

            # fixme: 依旧存在 bug，文本每行长一点，浏览器也没有放大，就会出现不会自动延展动态换行的情况
            lines = 3
            line_height = 1.5
            total_height = (lines + 1) * line_height  # 多加一行才行，这个 total_height 是固定了高度
            with ui.element("div").style(f"""
                 height: {total_height}em;
                 overflow: hidden;
                 display: flex;
                 align-items: flex-start;
                 justify-content: flex-start;
             """) as abstract_element:
                # markdown 会渲染一些东西，摘要页面原始一点比较好
                ui.label(note.content).style("""
                    display: -webkit-box;
                    -webkit-line-clamp: {lines};
                    -webkit-box-orient: vertical;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    line-height: {line_height};
                    word-break: break-word;
                """.format(lines=lines, line_height=line_height))
            return abstract_element

        async def show_filter_dialog(title: str):
            with ui.dialog(value=True) as dialog, ui.card(), ui.column():
                # todo: 建议用 table 吧，常规增删改查，建议一律 table，毕竟我没什么设计思维
                with ui.grid(columns=3).classes("w-64 gap-2 border-2 rounded-sm p-4"):
                    # todo: 参考鱼皮的代码小抄，实现标签添加和显示
                    for tag in extract_bracketed_content(title):
                        ui.button(tag)
                with ui.row().classes("w-full items-center justify-center"):
                    ui.button("取消", on_click=dialog.close).props("flat dense")
                    ui.button("保存").props("flat dense")

        with ui.card().classes("shadow-lg rounded-xl border border-gray-200 bg-white overflow-hidden") as card:
            with ui.column().classes("w-full p-4"):
                # flex-nowrap -> 不允许换行 | truncate min-w-0 -> 允许收缩，但最小为 0，配合 truncate 实现弹性截断
                with ui.row().classes("w-full items-center justify-between mb-2 whitespace-nowrap flex-nowrap "):
                    ui.label(note.title).classes("text-base font-semibold text-gray-800 ""truncate min-w-0 ") \
                        .tooltip(note.title)
                    ui.button(icon="filter").props("flat dense size=12px color=black") \
                        .tooltip("筛选标签").on("click", partial(show_filter_dialog, title=note.title))

                # --- 摘要
                abstract_element = create_abstract_element()
                # abstract_element.classes("border-b border-gray-100 pb-0 mb-0")

                # todo: 添加标签，但是布局变换很难受，不如直接一个小按钮然后弹窗支持编辑和修改吧！
                # with ui.row().classes("w-full py-0 my-0"):
                #     ui.button("知乎").props("flat dense color=grey").classes("text-sm text-gray-300")

                # --- 底部行：附件数量和更新时间、查看按钮、编辑按钮、更多按钮
                with ui.row().classes(
                        "w-full items-center justify-between "
                        "border-t border-gray-100 flex-nowrap"
                ):
                    # NOTE: 试图使用 .classes("hidden sm:inline") 做到 >sm 显示，但是实测发现，只有 inline sm:hidden 能生效... 我无语了，真对吗？也没人能讨论，唉。只能实现默认显示变大隐藏吗？
                    with ui.row().props("dense").classes(
                            "text-sm text-gray-600 "
                            "whitespace-nowrap flex-shrink-0 "
                            "gap-x-0 "
                    ):
                        ui.label(f"{attachment_count} 个附件")
                        ui.label("·").classes("px-1")
                        ui.label(f"{note.updated_at}").tooltip("上次编辑时间")
                    with ui.row().classes("items-center justify-between gap-x-0 flex-nowrap"):
                        # --- 查看按钮
                        eye_btn = ui.button(icon="mdi-eye-outline") \
                            .on_click(partial(self.controller.on_eye_btn_click, note_id=note.id)) \
                            .props("flat round dense").classes("text-gray-500 hover:text-blue-600 ")

                        async with NoteService() as service:
                            visit = await service.get_visit(note.id)
                            eye_btn.tooltip(f"访问次数：{visit}")

                        # --- 编辑按钮
                        ui.button(icon="mdi-square-edit-outline") \
                            .on_click(partial(go_edit_note, note_id=note.id, source="home_edit")) \
                            .props("flat round dense").classes("text-gray-500 hover:text-blue-600")

                        # --- 更多选项按钮
                        # props 是 quasar 框架的属性，优先级高于 classes
                        with ui.fab("mdi-dots-vertical", direction="up").props("flat padding=4px"):
                            ui.fab_action("mdi-trash-can-outline") \
                                .on_click(partial(delete_note, note_id=note.id, delay=False)) \
                                .props("flat round dense").classes("text-gray-500 hover:text-blue-600") \
                                .tooltip("删除")

                            ui.fab_action("mdi-chart-line") \
                                .props("flat round dense").classes("text-gray-500 hover:text-blue-600") \
                                .tooltip("访问量可视化")

                            # 每个笔记都可以设置截止日期和优先级等，然后通过主页渲染出来图形，表现出来笔记的急迫性（暂时没想出来咋表达）
                            ui.fab_action("mdi-calendar-alert") \
                                .props("flat round dense").classes("text-gray-500 hover:text-blue-600") \
                                .tooltip("截止日期提醒")

        return card

    async def _create_paging_control(self, current_page: int, total_pages: int):
        """分页控件，可能具有普遍性"""
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

                # 在分页组件中进行用户数据更新
                await self.controller.set_current_page(next_page)
                await self.rebuild_table(current_page=next_page)

            prev_btn.on_click(on_prev_btn_click)

            page_label = ui.label(f"Page {current_page} of {total_pages}").classes(
                "text-gray-700 font-medium px-3 py-2 "
                "bg-white rounded-lg shadow-sm "
                "border border-gray-200 "
                "cursor-pointer "
            )

            async def on_page_label_click():
                async with UserConfigService() as service:
                    page_size = await service.get_page_size()
                    await show_config_dialog({
                        "每页最大数量": {
                            "options": list(map(lambda x: x * 1, range(1, 30 + 1))),
                            "option_name": "page_size",
                            "default": page_size
                        },
                    })

            page_label.on("click", on_page_label_click)

            # todo: page_label 支持点击修改信息

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
                # 在分页组件中进行用户数据更新
                await self.controller.set_current_page(next_page)
                await self.rebuild_table(current_page=next_page)

            next_btn.on_click(on_next_btn_click)

    async def _create_hyperlink_table(self, parent: ui.element, notes: Sequence[Note]):
        with parent, ui.grid(columns=2).classes("w-full mx-auto"):
            for note in notes:
                with ui.card().classes("w-full max-w-full overflow-auto"), \
                        ui.list().classes("w-full"), \
                        ui.item().classes("w-full pr-1"):
                    with ui.item_section().classes("flex w-full gap-y-2"):
                        with ui.row().classes("w-full items-center justify-between"):
                            # truncate 控制超出省略，但是需要 w-full 限制，否则会自动拉伸
                            title = ui.label(note.title).classes("w-[60%] truncate cursor-pointer").tooltip(note.title)
                            title.on("click", partial(self.controller.on_eye_btn_click, note_id=note.id))
                            with ui.row().classes("items-center gap-x-0"):
                                with ui.dropdown_button("超链接", auto_close=True).props("flat"):
                                    urls = extract_urls(note.content)
                                    for url in urls:
                                        with ui.item(on_click=lambda url=url: ui.navigate.to(url, new_tab=True)) \
                                                .classes("text-sm text-blue-600 hover:bg-gray-100 items-center"):
                                            ui.label(url).classes("max-w-64 truncate").tooltip("点击跳转")
                                # with ui.button(icon="mdi-dots-vertical").props("flat dense"), ui.menu():
                                #     ui.menu_item("查看", partial(self.controller.on_eye_btn_click, note_id=note.id))
                                #     ui.separator()
                                #     ui.menu_item("编辑", partial(go_edit_note, note_id=note.id, source="home_edit"))
                                # ui.button(icon="mdi-eye-outline") \
                                #     .on_click(partial(self.controller.on_eye_btn_click, note_id=note.id)) \
                                #     .props("flat round dense").classes("text-gray-500 hover:text-blue-600 ") \
                                #     .tooltip("查看详情")

    @print_interval_time
    async def rebuild_table(self,
                            current_page: int | None = None,
                            filters: Dict | None = None):
        """

        :param current_page: 当前页号
        :param filters: 更多过滤，未来可能会删除重构
        :return:
        """
        # [2025-11-23] 点击返回按钮到主页时，延迟感很明显，想知道为什么...
        #              分页为 6 的时候就能明显的感觉到了（耗时已经接近 100ms 了）
        #              分页为 3 耗时大概 50 ms
        #              分页为 30 耗时大概 450 ms -> 优化为 200 ms
        #              但是我没能看到有什么优化的可能...
        #              优化完成！Attachment 表存二进制数据的原因！通过添加索引的方式暂时解决了！未来绝不允许在数据库中添加大于 100KB 的二进制数据！

        self.table.clear()
        await self.controller.refresh_note_number_label()

        # 从 user.profile 中取值
        if current_page is None:
            current_page = await self.controller.get_current_page()
        if not isinstance(current_page, int):
            current_page = 1

        filters = filters or {}

        # todo: 骨架与实现推荐拆分（临时设想）
        #       到底咋实现呢？Controller 层？View 层？
        # todo: 能否实现先渲染，数据到了再更新呢？

        # [clear + rebuild 可能存在的问题](https://lxblog.com/qianwen/share?shareId=4f727c46-84a9-436d-801b-2ccfac158908)
        # - 视觉闪烁、位置跳动
        # - 用户快速点击时可能触发多次异步操作（竞态条件）

        # region - build search_filter
        search_filter = {}

        async with UserConfigService() as user_config_service:
            home_select_option = await user_config_service.get_value("home_select_option")
            tag_select = await user_config_service.get_value("tag_select")
            search_filter["note_type"] = home_select_option
            search_filter["tag_select"] = tag_select

            # 搜索框的搜索内容（self.search_input.value），但是目前搜索框数据会快速同步至数据库，该字段可能可以删除，通过缓存和延时同步实现
            search_filter["search_content"] = await user_config_service.get_value("search_content")

            page_size = await user_config_service.get_page_size()

        search_filter.update(filters)
        # endregion

        # todo: 解决每次都要建立数据库链接的问题，__aenter__ 是有弊端的，缓存在这里没有派上什么用场，看样子 Service 设计的不行
        note_type = await self.controller.get_home_select_option()
        is_default = note_type == NoteTypeMaskedEnum.DEFAULT
        is_hyperlink = note_type == NoteTypeMaskedEnum.HYPERLINK
        is_bookmark = note_type == NoteTypeMaskedEnum.BOOKMARK

        async with NoteService() as service:
            result = await service.count_note(search_filter=search_filter)
            total_pages = max(1, math.ceil(result.unwrap() / page_size))
            # 避免页号溢出，从而得以支撑起将 current_page 存储于 user.profile 的能力
            # 目前只有用户选择翻页时才会更新 profile 中的 current_page 值，其余情况按下面这样处理
            if total_pages < current_page:
                current_page = 1
            notes = await service.get_notes(
                page=current_page,
                search_filter=search_filter,
                to_paginate=is_default
            )

        # 超链接模式重构 table
        if is_hyperlink:
            await self._create_hyperlink_table(self.table, notes)
            return
        elif is_bookmark:
            # todo: 参考火狐的书签，实现一个类似的功能
            return

        with self.table:
            profiler = cProfile.Profile()
            profiler.enable()
            with IntervalTimer() as timer_outer:
                # with ui.grid(columns=3).classes("w-full gap-4"):
                with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"):
                    async with AttachmentService() as attachment_service:
                        # [note][2025-11-23] 测试发现，最耗时的在这里 -> 进一步发现是 count_attachment 的问题 -> 添加索引
                        for note in notes:
                            with IntervalTimer(log_enabled=False) as timer:
                                result = await attachment_service.count_attachment(note.id)
                                attachment_count = result.unwrap()
                                await self._create_table_card(note, attachment_count)
                                timer.print(prefix="for note in notes", suffix=f"note.id: {note.id}")
                timer_outer.print(prefix="build ui.grid")
            profiler.disable()
            stats = pstats.Stats(profiler)
            stats.sort_stats("cumtime")  # ncalls/tottime/percall/cumtime/percall 排序用
            stats.print_stats(10)  # 不传参代表全部输出，传参代表前 X 行

            await self._create_paging_control(current_page, total_pages)


@ui.page("/", title="笔记管理系统")
async def page_main(request: Request, search_content: str = "", notify_from: str = None):
    # ====== 开始构建 ui（我将使用 `[step]` 详细记录自己的开发过程，step 代指我在编写这段代码，行动上做了什么） ====== #

    # [step] 使用 region 进行注释拆分的时候发现页面结构基本按照下列方式分层，故而拆分成函数
    await HeaderView.create()
    await build_footer()

    # todo: 这种行为如果能封装降低使用复杂度和耦合度，那也可以接受！
    # if notify_from in ["get_note__delete", "home__delete"]:
    #     ui.timer(0, lambda: ui.notify(f"删除笔记成功！", type="positive"), once=True)

    await PageMainView.create()
