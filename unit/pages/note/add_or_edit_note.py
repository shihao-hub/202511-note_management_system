import asyncio
import uuid
from functools import partial
from pathlib import Path
from typing import Literal, Tuple, Dict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pyperclip
from aiohttp import ClientSession
from nicegui import ui
from nicegui.events import GenericEventArguments, ValueChangeEventArguments
from fastapi import Request

from models import NoteTypeMaskedEnum
from views import HeaderView, build_footer, see_attachment
from utils import go_main, go_get_note, DeepSeekClient, register_find_button_and_click, RateLimiter, build_ai_chain, \
    go_edit_note
from services import AttachmentService, NoteService, UserConfigService
from settings import dynamic_settings, ENV
from views import View, Controller
from log import logger


class PageAddOrEditNoteController(Controller["PageAddOrEditNoteView"]):
    def __init__(self, view: "PageAddOrEditNoteView"):
        super().__init__(view)
        self.save_note_rate_limter = RateLimiter(dynamic_settings.save_note_cooldown)
        self._create_initial_values()

    def _create_initial_values(self):
        # 保存初始值，用于检测是否有变化
        self.initial_title = ""
        self.initial_content = ""

    def _sync_initial_values(self, *, title: str, content: str):
        self.initial_title = title
        self.initial_content = content

    async def on_content_value_change(self, e: ValueChangeEventArguments):
        # todo: 确定一下这个是否会导致卡顿呢？
        self.view.content_preview.content = e.value

    async def _show_unsaved_dialog(self):
        with ui.dialog(value=True) as dialog, ui.card():
            with ui.row().classes("w-full items-center justify-center"):
                ui.label("笔记未保存，是否保存？")
            with ui.row().classes("w-full items-center justify-center"):
                async def on_save_click():
                    await self.save_note()
                    dialog.close()
                    await self.on_arrow_left_btn_click(skip_check=True)

                ui.button("保存", on_click=on_save_click).props("flat")

                async def on_cancel_click():
                    dialog.close()
                    await self.on_arrow_left_btn_click(skip_check=True)

                ui.button("不保存", on_click=on_cancel_click).props("flat")

                ui.button("取消", on_click=dialog.close).props("flat")

    async def init_title_and_content(self):
        logger.debug("[init_title_and_content] start")
        async with NoteService() as service:
            # [2025-11-20] 附件数量单独获取，故添加了 selectinload_enable = False，避免查管理表
            result = await service.get_note_with_attachments(self.view.note_id, selectinload_enable=False)
            if result.is_err():
                logger.error("{}", result.err())
                raise Exception(result.err())
            note = result.unwrap()
            logger.debug("note: {}", note)
            # attachments = note.attachments

        self.view.title.value = note.title
        self.view.content.value = note.content
        self.view.content_preview.content = note.content

        self._sync_initial_values(title=note.title, content=note.content)

    async def get_attachment_count(self, note_id: int):
        async with AttachmentService() as service:
            result = await service.count_attachment(note_id)
        logger.debug("result: {}", result)
        return result.unwrap()

    def has_title_or_content_changed(self):
        # 比较当前值与初始值，判断数据是否发生了变化：标题/正文（暂时忽略附件的判断，很麻烦...）
        return self.view.title.value != self.initial_title or self.view.content.value != self.initial_content

    async def on_arrow_left_btn_click(self, skip_check: bool = False):
        # [note] 实践发现，虽然回调有第一个参数 e，但是如果其他参数是 kwargs 即使没有那个 e 也可以
        if not skip_check and self.has_title_or_content_changed():
            await self._show_unsaved_dialog()
            return

        # [2025-11-14] 实践发现，访问详情页很别扭呀
        # [2025-11-17] 编辑页面新增来源：如果是直接点击主页的编辑按钮进去的，则返回到主页
        if self.view.is_add_note_page or self.view.source == "home_edit":
            go_main()
        else:
            go_get_note(self.view.note_id)

    async def toggle_recording(self):
        """切换录音状态"""
        # [2025-11-25] 功能未完善，暂且不生效
        if True:
            ui.notify("功能未完善，暂且不生效", type="info")

        # [2025-11-21] 之所以没有移动到 templates 目录下，是因为 ui.run_javascript 有返回值
        result = await ui.run_javascript(
            '''
            if (!window.nmsRecorder) {
                window.nmsRecorder = {isRecording: false, mediaRecorder: null, chunks: []};
            }

            if (!window.nmsRecorder.isRecording) {
                // 开始录音
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
                    window.nmsRecorder.mediaRecorder = new MediaRecorder(stream);
                    window.nmsRecorder.chunks = [];

                    window.nmsRecorder.mediaRecorder.ondataavailable = (e) => {
                        window.nmsRecorder.chunks.push(e.data);
                    };

                    window.nmsRecorder.mediaRecorder.onstop = async () => {
                        const blob = new Blob(window.nmsRecorder.chunks, {type: "audio/webm"});
                        const formData = new FormData();
                        formData.append("file", blob, "recording.webm");

                        // 上传到语音识别接口
                        try {
                            const response = await fetch("/api/speech_recognition", {
                                method: "POST",
                                body: formData
                            });

                            if (response.ok) {
                                const result = await response.json();
                                // 使用 emitEvent 将数据传递给 Python（题外话，ai 的强度很高啊）
                                emitEvent("nms_speech_recognized", {text: result.data});
                            } else {
                                console.log(response);
                                alert(`语音识别失败`);
                            }
                        } catch (error) {
                            console.error("上传音频失败:", error);
                            alert("上传音频失败: " + error.message);
                        }

                        // 停止所有音轨
                        stream.getTracks().forEach(track => track.stop());
                    };

                    window.nmsRecorder.mediaRecorder.start();
                    window.nmsRecorder.isRecording = true;
                    return "recording_started";
                } catch (error) {
                    console.error("无法访问麦克风:", error);
                    alert("无法访问麦克风: " + error.message);
                    return "error";
                }
            } else {
                // 停止录音
                window.nmsRecorder.mediaRecorder.stop();
                window.nmsRecorder.isRecording = false;
                return "recording_stopped";
            }
            ''', timeout=1.0)

        if result == "recording_started":
            ui.notify("开始录音...", type="info")
        elif result == "recording_stopped":
            ui.notify("处理中...", type="info")
        elif result == "error":
            ui.notify("无法访问麦克风", type="negative")

    async def on_speech_recognized(self, e: GenericEventArguments):
        """处理语音识别结果"""
        text = e.args.get("text", "")
        if text:
            # 将识别的文本追加到内容末尾
            current_content = self.view.content.value or ""
            self.view.content.value = current_content + ("\n" if current_content else "") + text
            ui.notify("语音识别成功", type="positive")
        else:
            ui.notify("未识别到内容", type="warning")

    async def ai_generate_title(self):
        if not self.view.content.value or self.view.content.value.strip() == "":
            ui.notify("正文内容为空，无法生成", type="negative")
            return
        self.view.show_loading("正在生成标题...")
        try:
            chain = build_ai_chain()
            result = await chain.handle(f"""
                            你是一位文本总结专家，你需要将下面的内容总结成一个简短的标题（不要超过 100 个字符）：
                            {self.view.content.value}
                            """)
            self.view.title.value = result["response"][:100]  # 过长截断
        except Exception as e:
            logger.error(e)
            ui.notify(f"ai 生成出错，原因：{e}", type="negative")

        self.view.hide_loading()

    def show_export_dialog(self):
        """显示导出文件名输入对话框"""

        async def on_confirm():
            file_name = file_input.value.strip()
            if not file_name:
                return
            if not file_name.endswith('.txt'):
                file_name += '.txt'

            # todo: 校验 file_name 格式，要求满足 Windows 和 Linux 的文件格式
            file_content = f"{self.view.title.value}\n\n{self.view.content.value}"
            logger.debug("filename: {}", file_name)
            logger.debug("len(file_content): {}", len(file_content))

            # todo: 自动创建一下如何？
            dynamic_settings.export_dir.mkdir(parents=True, exist_ok=True)
            safe_file_path = dynamic_settings.export_dir / f"{uuid.uuid4()}-{file_name}"
            safe_file_path.write_text(file_content, encoding="utf-8")
            ui.notify(f"导出为：{Path.cwd() / safe_file_path}", type="positive")

            # try:
            #     safe_content = json.dumps(file_content)[1:-1]  # 转义
            #     js_code = f'''
            #         console.log(111);
            #         const blob = new Blob(["{safe_content}"], {{ type: "text/plain;charset=utf-8" }});
            #         const url = URL.createObjectURL(blob);
            #         const a = document.createElement("a");
            #         a.href = url;
            #         a.download = "{file_name}";
            #         document.body.appendChild(a);
            #         a.click();
            #         URL.revokeObjectURL(url);
            #         a.remove();
            #     '''
            #     await ui.run_javascript(js_code)
            # except Exception as e:
            #     logger.error(e)
            #     ui.notify(f"错误：{e}", type="negative")

            dialog.close()

        with ui.dialog(value=True) as dialog, ui.card():
            file_input = ui.input(label="文件名", value="导出内容.txt").props('autofocus')

            with ui.row():
                ui.button('确定', on_click=on_confirm)

                ui.button('取消', on_click=dialog.close)

    async def auto_periodic_save(self):
        """自动周期性保存"""

        # 标题为空，不保存
        if not self.view.title.value:
            return

        # todo: 确认一下，这种没有类型的情况下，代码是不是很难阅读
        await self.save_note(auto_save=True)

    async def save_note(self, auto_save: bool = False):

        if not self.view.title.value:
            ui.notify("标题不能为空", type="negative")
            return
        # 正文允许为空
        if self.view.content.value is None:
            self.view.content.value = ""

        # 自动保存 - 标题或内容未发生变化，不保存
        if auto_save and not self.has_title_or_content_changed():
            return

        if not self.save_note_rate_limter.allow():
            ui.notify(f"操作太频繁，请稍后再试", type="negative")
            return

        # todo: 将保存和编辑归一化，因为它们二者存在共性
        short_note_word_count_limit = 30

        # todo: 新增 + 编辑 + 自动保存 耦合严重，代码很难看

        try:
            # 新增页面，有 temporary_uuid，需要更新 attachment
            # 编辑页面，没有 temporary_uuid 有 note_id，不必考虑 attachment，上传文件时即绑定
            # [2025-11-23] Python try except 搭配 Rust Result 使用
            if self.view.is_add_note_page:
                # todo: 思考一下可拓展性，就是拿到一个需求之后，不要在原函数追加，而是新增函数？这是不是就是 Java 里面的多态啊，不得不说，还是需要有经验到一定程度才可以。（好麻烦，越来越复杂，而且你无法保证这个需求是否会被砍掉，但是你的代码已经固定）
                # if len(self.view.content.value) <= short_note_word_count_limit:
                #     pass

                async with NoteService() as note_service:
                    result = await note_service.create(title=self.view.title.value, content=self.view.content.value)
                if result.is_err():
                    raise Exception(f"错误：{result.err()}")

                # note 创建完毕，由于上传附件不是在保存时统一上传，所以保存时，需要更新附件表
                instance = result.unwrap()

                async with AttachmentService() as attachment_service:
                    await attachment_service.update_by_temporary_uuid(self.view.temporary_uuid, **dict(
                        note_id=instance.id,
                        temporary_uuid=None
                    ))

                # 新增笔记页面需要清空
                self.view.title.value = ""
                self.view.content.value = ""
                self.view.upload_attachment_card_label.text = dynamic_settings.attachment_upload_text.format(0)

                if not auto_save:
                    ui.notify("保存笔记成功！", type="positive")
                    # 建议直接跳转到编辑页面（使用发现，直接跳转 + 跳转后 notify 更好...）
                    ui.timer(0.5, lambda: go_edit_note(note_id=instance.id), once=True)
            else:
                async with NoteService() as service:
                    result = await service.update(self.view.note_id,
                                                  title=self.view.title.value,
                                                  content=self.view.content.value)
                    if result.is_err():
                        raise Exception(f"编辑笔记失败，原因：{result.err()}")
                    async with AttachmentService() as attachment_service:
                        await attachment_service.update_by_temporary_uuid(self.view.temporary_uuid, **dict(
                            note_id=self.view.note_id,
                            temporary_uuid=None
                        ))
                    if not auto_save:
                        ui.notify(f"编辑笔记成功！", type="positive")
        except Exception as e:
            ui.notify(f"{e}", type="negative")
            self.view.tip_label.text = f"（自动失败保存于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}）"
        else:
            self._sync_initial_values(title=self.view.title.value, content=self.view.content.value)

            # 自动保存 - 不必触发 ui.notify
            if auto_save:
                logger.debug("触发自动保存")
                # [note] datetime.now() 自动获取当地时间（但是数据库必须存储 UTC 时间，拿到后自动转当地时间）
                self.view.tip_label.text = f"（自动保存于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}）"

    async def get_note_content_rows(self) -> int:
        async with UserConfigService() as user_config_service:
            return await user_config_service.get_value("note_content_rows")

    async def on_nms_upload_success(self, e: GenericEventArguments):
        # [2025-11-20] 虽然目前该回调被两个地方使用，但是事件在 js 触发时，会指定元素触发的

        logger.debug("upload success")
        ui.notify("文件上传成功", type="positive")
        # 上传成功（非保存页面），应该使用 temporary_uuid 查询数量（注意，这编辑和新增耦合严重，需要考虑解决...）
        async with AttachmentService() as attachment_service:
            existing_count = 0
            logger.debug("note_id: {}", self.view.note_id)
            if self.view.note_id is not None:
                existing_result = await attachment_service.count_attachment(self.view.note_id)
                if existing_result.is_err():
                    ui.notify(f"上传失败，原因：{existing_result.err()}", type="negative")
                    return
                existing_count = existing_result.unwrap()
            temporary_result = await attachment_service.count_attachment_by_temporary_uuid(self.view.temporary_uuid)
            if temporary_result.is_err():
                ui.notify(f"查询临时附件失败：{temporary_result.err()}", type="negative")
                return
            count = temporary_result.unwrap() + existing_count
            self.view.upload_attachment_card_label.text = dynamic_settings.attachment_upload_text.format(count)

    def delay_register_drag_upload_events(self):
        # 由于未能找到 python 层面的 preventDefault，所以需要在 DOM 加载后通过 js 层调用 preventDefault，
        # 而 ui.timer 似乎比 DOMContentLoaded 更晚，不然 drop 事件会在 js 层之前注册，依旧无效了

        def on_dragover(e: GenericEventArguments):
            # logger.debug("python dragover event: add nms-dragover class")

            # dragover 会被反复触发，是否会导致添加一堆重复 class？
            self.view.upload_attachment_card.classes("nms-dragover")

        def on_dragenter(e: GenericEventArguments):
            # logger.debug("python dragenter event: add nms-dragover class")

            # logger.debug("e.args: {}", e.args)

            # isTrusted: False 表示这个事件不是由用户直接触发的，而是由程序代码触发的
            if not e.args["isTrusted"]:
                # logger.debug("111")
                # self.upload_attachment_card.classes("bg-blue-500")
                logger.debug("card: {}", id(self.view.upload_attachment_card))

        def on_dragleave(e: GenericEventArguments):
            # logger.debug("python dragleave event: remove nms-dragover class")

            self.view.upload_attachment_card.classes(remove="nms-dragover")

        def on_drop(e: GenericEventArguments):
            # logger.debug("python drop event: remove nms-dragover class")

            self.view.upload_attachment_card.classes(remove="nms-dragover")

        self.view.upload_attachment_card.on("dragover", on_dragover)
        self.view.upload_attachment_card.on("dragleave", on_dragleave)
        # self.upload_attachment_card.on("dragenter", on_dragenter)  # 这个似乎没什么用
        self.view.upload_attachment_card.on("drop", on_drop)


class PageAddOrEditNoteView(View["PageAddOrEditNoteController"]):
    controller_class = PageAddOrEditNoteController

    async def _pre_initialize(self):
        await super()._pre_initialize()

        ui.add_css("""
        .nms-drag-area.nms-dragover {
            border: 2px dashed #4a90e2;
            background-color: #f0f7ff;
            transition: all 0.2s;
        }
        """)

        self.note_id = self.query_params.get("note_id")
        self.temporary_uuid = self.query_params.get("temporary_uuid")
        self.source = self.query_params.get("source")
        self.is_add_note_page = True if self.note_id is None else False  # note_id 不存在，才是新增笔记页面

        # region - 遮罩背景：纯毛玻璃效果（无背景色）
        with ui.element("div").classes(
                "fixed inset-0 flex items-center justify-center z-50"
        ).style("backdrop-filter: blur(2px); display: none;") as self.loading_overlay:
            with ui.card().classes("p-6 shadow-lg rounded-lg bg-white flex flex-col items-center"):
                ui.spinner(size="lg")
                self.loading_label = ui.label("处理中...").classes("mt-4 text-gray-700")
        # endregion

        if self.is_add_note_page:
            ui.page_title("新增笔记")
        else:
            ui.page_title("编辑笔记")

        # region - 拖拽上传和粘贴长传

        # 注册，监听快捷键并触发自定义 nms_upload_success 事件
        ui.add_body_html("<script>{0}</script>".format(ENV.get_template("key_pressed.js").render({
            "save_btn_id": "save_btn",
            "content_id": "content",
        })))

        # 注册，拖拽上传
        ui.add_body_html("<script>{0}</script>".format(ENV.get_template("drag_upload.js").render({
            "container_id": "upload_attachment_card"
        })))

        # endregion

        # todo: nicegui 有提供部分快捷键监听事件，请前往官网查看
        ui.add_body_html("<script>{0}</script>".format(ENV.get_template("find_button_and_click.js").render({
            "button_id": "_arrow_left_btn",  # 临时的
            "pressed_key": "Escape",
            "is_ctrl": False,
        })))

    async def _post_initialize(self):
        await super()._post_initialize()

        # 暂时设定，5 秒周期性自动保存一次（其实也不是太好... 难受，得思考一下有没有什么好办法）
        if not self.is_add_note_page:
            ui.timer(0, lambda: ui.timer(5, self.controller.auto_periodic_save), once=True)

    async def _initialize(self):
        with ui.column().classes("w-full mx-auto px-4 sm:px-6 md:px-8 max-w-7xl py-6"):
            # --- 撤回按钮、小标题
            with ui.row().classes("w-full items-center gap-x-3 mb-6"):
                # [step] ai: ui.icon(name="mdi-arrow-left", size="24px") 可以点击吗？发现 icon 其实是字体，所以改完颜色居然还是默认蓝色
                ui.button(icon="mdi-arrow-left", on_click=self.controller.on_arrow_left_btn_click) \
                    .props("id=c_arrow_left_btn flat round").classes("text-gray-700 hover:bg-gray-100")

                if self.is_add_note_page:
                    ui.label("新增笔记").classes("text-xl font-bold text-gray-900")
                else:
                    with ui.row().classes("items-center gap-x-0"):
                        ui.label("编辑笔记").classes("text-xl font-bold text-gray-900")
                        self.tip_label = ui.label().classes("text-gray-500 text-center text-xs")

            # --- 笔记输入区
            with ui.card().classes("w-full rounded-xl shadow-md border border-gray-200 overflow-hidden"), \
                    ui.column().classes("w-full px-5 py-6"):
                # --- 标题
                self.title = ui.input(placeholder="输入笔记标题...")
                self.title.classes("w-full text-lg font-medium placeholder:text-gray-400").props("dense")

                # --- 标题后的菜单按钮
                with self.title.add_slot("append"):
                    self.build_menu_button()

                # --- 正文
                with ui.splitter(value=100).classes("w-full") as splitter:
                    with splitter.before:
                        self.content = (
                            ui.textarea(placeholder="输入笔记内容...")
                            .classes("w-full mt-4 placeholder:text-gray-400").props("spellcheck=false")  # autogrow
                            .props(f"id=content rows={max(await self.controller.get_note_content_rows(), 14)}")
                            .classes("leading-relaxed")
                            .on_value_change(self.controller.on_content_value_change)
                        )
                    # todo: 是否有办法让 textarea 拉伸时，下面的高度也变化呢？html css js 才可以吧，nicegui 阉割了
                    with splitter.after:
                        with ui.card().classes(
                                "w-full p-3 "
                                "bg-gray-50 border-0 shadow-none rounded-none "
                                "oveflow-y-auto"
                        ):
                            # with ui.scroll_area().classes("flex-grow p-3 bg-gray-50"):
                            #     self.content_preview = ui.markdown().classes("prose prose-sm max-w-none")
                            self.content_preview = ui.markdown().classes("prose prose-sm h-64 ") \
                                .style("user-select: text; cursor: text;")

                # 粘贴上传
                self.content.on("nms_upload_success", self.controller.on_nms_upload_success)

                # 编辑页面 - 初始化 title 和 content（放在前面，迅速初始化，减少延迟）
                if not self.is_add_note_page:
                    await self.controller.init_title_and_content()

                # todo: 右键粘贴到指定光标处
                with self.content, ui.context_menu():
                    async def on_click():
                        self.content.value += pyperclip.paste()

                    ui.menu_item("粘贴", on_click=on_click).tooltip("目前只实现了追加到末尾")

                with ui.column().classes("w-full mt-6 gap-y-4"):
                    # --- 附件标题、上传按钮
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("附件").classes("font-medium text-gray-800")
                        ui.button("查阅附件", on_click=partial(see_attachment, note_id=self.note_id)) \
                            .props("flat icon-right=mdi-chevron-right dense").classes("text-blue-600")

                    # --- 上传附件的长卡片
                    with ui.card().props("id=upload_attachment_card").classes(
                            "w-full rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 "
                            "flex flex-col items-center justify-center px-4 py-4"
                            "transition-colors duration-200 ease-in-out cursor-pointer "
                            "hover:border-gray-400 hover:bg-gray-100 "
                            "nms-drag-area"
                    ) as self.upload_attachment_card:
                        with ui.row().classes("mb-3"):
                            ui.icon(name="mdi-attachment", size="28px").classes("text-gray-500")
                        self.upload_attachment_card_label = ui.label(dynamic_settings.attachment_upload_text.format(0))
                        self.upload_attachment_card_label \
                            .classes("text-gray-500 text-center text-sm max-w-xs nms-drag-area")

                        # 延迟注册拖拽相关事件，主要是修改 card 的 css 样式（不延迟不行，因为 python 层事件比 js 层先注册了）
                        ui.timer(0, self.controller.delay_register_drag_upload_events, once=True)

                        # 拖拽上传
                        self.upload_attachment_card.on("nms_upload_success", self.controller.on_nms_upload_success)

                        # 编辑页面 - 刷新附件数量
                        if not self.is_add_note_page:
                            attachment_count = await self.controller.get_attachment_count(note_id=self.note_id)
                            logger.debug("attachment_count: {}", attachment_count)
                            self.upload_attachment_card_label.text = \
                                dynamic_settings.attachment_upload_text.format(attachment_count)

                    # --- 保存按钮与左侧小文本块
                    with ui.row().classes("w-full items-center justify-end mt-6") as row:
                        self.save_btn = ui.button("保存笔记", on_click=self.controller.save_note) \
                            .props("id=save_btn unelevated") \
                            .classes("px-6 py-2 bg-blue-600 text-white hover:bg-blue-700")  # rounded-2xl

    def show_loading(self, message: str = "处理中..."):
        # todo: show_loading 和 hide_loading 可以使用 contextmanager 管理一下
        self.loading_label.set_text(message)
        self.loading_overlay.style("display: flex;")  # 显示

    def hide_loading(self, ):
        self.loading_overlay.style("display: none;")

    def build_menu_button(self):
        """构建当前页面的菜单按钮"""
        with ui.button(icon="menu").classes("text-[10px] -mr-1 -mb-1") \
                .props("flat dense color=grey"), ui.menu():
            ui.menu_item("语音识别", auto_close=False, on_click=self.controller.toggle_recording) \
                .tooltip("点击开始/停止录音")
            ui.on("nms_speech_recognized", self.controller.on_speech_recognized)

            ui.separator()
            ui.menu_item("ai 生成标题").tooltip("双击触发：根据正文内容，让 ai 生成合适的标题") \
                .on("dblclick", self.controller.ai_generate_title)

            if not self.is_add_note_page:
                ui.separator()
                ui.menu_item("导出为文件", auto_close=False, on_click=self.controller.show_export_dialog)

                # ui.separator()
                # import_file = ui.menu_item("导入文件", auto_close=False)

            # 此处发现，add 和 edit 耦合其实可以接受，但是需要优化一下
            ui.separator()
            with ui.menu_item("前缀插入", auto_close=False), \
                    ui.menu().props('anchor="center right" self="center left"'):
                def create_menu_item(text):
                    async def on_click():
                        if text not in self.title.value:
                            self.title.value = text + self.title.value

                    ui.menu_item(text, auto_close=False, on_click=on_click)

                for value in dynamic_settings.prefix_import_values:
                    create_menu_item(value)

            ui.separator()
            ui.menu_item("笔记归档").tooltip("将已完成的笔记归档起来")


@ui.page("/add_or_edit_note", title="新增或编辑笔记")
async def page_add_or_edit_note(request: Request, temporary_uuid: str, note_id: int = None,
                                source: Literal["home_edit"] | None = None):
    """

    :param request: fastapi Request
    :param note_id: note_id 存在为编辑，不存在为新增
    :param temporary_uuid: 供新增使用，为了定位到上传的附件
    :param source: 从哪进入的（太丑陋了，但是终究是实现了，所以其实始终都是和这样的代码打交道的...）
    """

    # ====== 涉及 header, footer, add_css, add_head_html ====== #

    await HeaderView.create()
    await build_footer()
    await PageAddOrEditNoteView.create(query_params={
        "temporary_uuid": temporary_uuid,
        "note_id": note_id,
        "source": source,
    })
