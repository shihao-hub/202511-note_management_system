#### 原生 sqlite 使用

```python
import sqlite3
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import Request, UploadFile, File, FastAPI
from loguru import logger

fastapi_app = FastAPI()

# 创建线程池用于异步执行数据库操作
db_executor = ThreadPoolExecutor(max_workers=5)


@fastapi_app.post("/add_note", summary="测试·添加笔记")
async def add_note(request: Request):
    logger.debug("[add_note] start")
    logger.debug("request type: {}", type(request))

    def add_note_to_db():
        # todo: 执行出错会发生什么？将异常抛给上层？一直没处理就一直往上抛？
        lastrowid = None
        with sqlite3.connect("native_notes.db") as conn:
            conn.execute("""
                         CREATE TABLE IF NOT EXISTS notes
                         (
                             id         INTEGER PRIMARY KEY AUTOINCREMENT,
                             title      TEXT NOT NULL,
                             content    TEXT NOT NULL,
                             created_at REAL NOT NULL,
                             updated_at REAL NOT NULL
                         )
                         """)
            cursor = conn.cursor()
            timestamp = time.time()
            cursor.execute("INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                           (f"测试标题-{timestamp}", f"测试内容-{timestamp}", timestamp, timestamp))
            lastrowid = cursor.lastrowid
        return lastrowid

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(db_executor, add_note_to_db)  # noqa: Parameter 'args' unfilled, ...

    return {"id": res}
```

#### fastapi 与 websocket

```python
from fastapi.websockets import WebSocket
from nicegui import app


# 测试发现，这个注册一次之后，第二次再注册，会被忽略（即只保留第一次注册的情况，包括那个函数的闭包上值）
# 我很好奇这些背后的事情，page 刷新后，card 依旧存在？它为什么还存在？是一直都存在还是因为被闭包了才存在的？这是否存在内存泄露问题？
# 说起内存泄漏，前后端分离 + 无状态 http 可以让前后端几乎无依赖，但是 nicegui 似乎可能发生前端让后端内存泄露的情况？
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 此处的函数本来是定义在 page 里面的，所以有 card。现在暂且保留此函数
    await websocket.accept()
    await websocket.send_text("Connected to NiceGUI WebSocket!")
    try:
        while True:
            # 接收来自前端的消息
            data = await websocket.receive_text()
            # print(f"Received from client: {data}")

            # 我都想笑了...虽然这个注册存在问题，但是第一次注册的时候，后端确实可以访问到 card 并修改其内容
            # frontend(js) ->(websocket) backend(python) ->(memory) card ->(websocket) frontend(browser)
            # logger.debug("ws card: {}", id(card))
            # card.classes("bg-blue-500")

            # 响应消息
            await websocket.send_text(f"Server received: {data}")

            # [note] 此处显然实现一个分发器就行了（websocket 是双向的，前端如何接收消息的暂不管）：
            #        假设前端发来的消息格式为 事件名和事件相关数据，那么后端此处实现一个分发器即可？其实也就类似 http 请求分发？

    except Exception as e:  # noqa
        # print("Client disconnected")
        # logger.error(e)
        pass
```

#### 挂在的 fastapi_app 无法设置 lifespan

```python
import contextlib

from fastapi import FastAPI
from loguru import logger

from utils import cleanup


@contextlib.asynccontextmanager
async def lifespan(app_: FastAPI):
    # 应用启动时初始化
    logger.debug("startup")
    await cleanup.start()
    yield
    # 应用关闭时清理资源
    logger.debug("shutdown")
    await cleanup.stop()


fastapi_app = FastAPI()  # lifespan=lifespan 不生效，理由未知
```

#### ai 生成的新建笔记 card

```python
from nicegui import ui


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
```

#### 防抖

```python
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
```

#### tinydb

```python
async def tinydb_test():
    from tinydb import TinyDB, Query

    @alru_cache()
    async def get_db(filepath: str = "memo.json") -> TinyDB:
        return await asyncify(lambda: TinyDB(filepath))

    # todo: 需要思考一下这个的可靠性，如多线程会发生什么，而且我这边丢着不放居然出现了 json 文件格式出错的问题，很诡异（id=150后，错位了）
    #       json 文件最大多少容量就应该升级了？
    db = await get_db()

    # [Welcome to TinyDB!](https://tinydb.readthedocs.io/en/latest/)
    # [github.com/msiemens/tinydb](https://github.com/msiemens/tinydb)
    # https://github1s.com/msiemens/tinydb/blob/master/docs/extensions.rst#L22
    # https://zread.ai/msiemens/tinydb

    async def test_a():
        await asyncify(lambda: db.insert({"status": "ok2"}))
        result = await asyncify(lambda: db.all())
        print(result)

    await test_a()
```

#### pytz 简单使用

```python
def old_version():
    import pytz
    # 转为北京时间
    aware_dt = utc_dt.astimezone(pytz.timezone("Asia/Shanghai"))
    # 移除转为字符串后的 +08:00 这个时区信息 + 将微秒置为0，确保转字符串时无小数点
    naive_dt = aware_dt.replace(tzinfo=None, microsecond=0)
    return naive_dt
```

#### pyinstaller

```python
# pyinstaller（注意 sqlalchemy 搭配 alembic 的主动迁移命令，导致打包后出错，需要考虑如何解决，虽然复制一个无数据 db 即可解决）
try:
    import addict
    import aiocache
    import aiosqlite
    import alembic
    import async_lru
    import fastapi_limiter
    import jinja2
    import loguru
    import lupa
    import nicegui
    import numpy
    import openai
    import pandas
    import portpicker
    import pydantic_settings
    import pyecharts
    import pyperclip
    import result
    import slowapi
    import sqlalchemy
    import sqlalchemy_utc
    import tinydb
    import unqlite

    import gradio_client  # 实践发现，这个库 pyintaller 打包不进来，不知道是 nicegui-pack 的原因还是什么原因
    import matplotlib  # 实践发现，`No module named 'matplotlib.backends.backend_svg'`，添加下列代码后导入成功
    import matplotlib.backends
    import matplotlib.backends.backend_svg
except ImportError as exception:
    logger.error(exception)
    raise exception
```

#### splash ai 生成（不够可用）

```python
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageTk
import tkinter as tk


class SplashScreen:
    def __init__(self, image_path: str, duration: int = 3):
        """
        初始化 Splash 屏幕
        
        Args:
            image_path: splash 图片路径
            duration: 显示持续时间（秒）
        """
        self.image_path = image_path
        self.duration = duration
        self.root = None

    def show(self):
        """显示 splash 屏幕"""
        if not os.path.exists(self.image_path):
            print(f"Splash 图片不存在: {self.image_path}")
            return

        self._show_splash()

    def _show_splash(self):
        """内部方法：实际显示 splash 窗口"""
        try:
            self.root = tk.Tk()
            self.root.title("启动中...")

            # 移除窗口边框
            self.root.overrideredirect(True)

            # 设置窗口居中
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()

            # 加载图片
            try:
                image = Image.open(self.image_path)
                photo = ImageTk.PhotoImage(image)

                # 获取图片尺寸
                img_width = image.width
                img_height = image.height

                # 计算居中位置
                x = (screen_width - img_width) // 2
                y = (screen_height - img_height) // 2

                # 设置窗口位置和大小
                self.root.geometry(f"{img_width}x{img_height}+{x}+{y}")

                # 显示图片
                label = tk.Label(self.root, image=photo)
                label.image = photo  # 保持引用防止垃圾回收
                label.pack()

            except Exception as e:
                print(f"加载 splash 图片失败: {e}")
                # 如果图片加载失败，显示简单的文本
                self.root.geometry("300x150")
                label = tk.Label(self.root, text="笔记管理系统\n启动中...", font=("Arial", 16))
                label.pack(expand=True)

            # 刷新窗口
            self.root.update()

            # 显示指定时间
            time.sleep(self.duration)

            # 关闭窗口
            self.root.destroy()

        except Exception as e:
            print(f"Splash 窗口创建失败: {e}")
            if self.root:
                try:
                    self.root.destroy()
                except:
                    pass


def show_splash(image_path: str = None, duration: int = 3):
    """
    便捷函数：显示 splash 屏幕
    
    Args:
        image_path: splash 图片路径，默认使用项目根目录下的 icon.png
        duration: 显示持续时间（秒）
    """
    if image_path is None:
        # 获取项目根目录
        current_dir = Path(__file__).parent.parent
        image_path = str(current_dir / "icon.png")

    splash = SplashScreen(image_path, duration)
    splash.show()
    return splash


if __name__ == "__main__":
    # # 测试代码
    # splash = show_splash(duration=2)
    # print("Splash 测试完成")
    # 显示 splash 屏幕
    splash = None
    try:
        from splash import show_splash

        splash = show_splash(duration=2)
    except ImportError as e:
        print("无法导入 splash 模块，跳过启动画面: {}", e)
    except Exception as e:
        print("显示启动画面失败: {}", e)

    if splash:
        splash.wait()  # ？

```

#### PySide/PyQt 自定义右键菜单和 closeEvent

```python
# 禁用默认上下文菜单
# self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
# self.view.customContextMenuRequested.connect(self.show_custom_menu)

def show_custom_menu(self, pos):
    """设置自定义右键菜单（仍在开发阶段）"""
    menu = QMenu(self)

    # 添加自定义菜单项
    action1 = menu.addAction("Custom Action 1")
    action2 = menu.addAction("Custom Action 2")
    action3 = menu.addAction("Open in New Tab")

    # 可选：添加分隔线
    menu.addSeparator()

    # 添加原生功能（比如保存页面）
    save_action = menu.addAction("Save Page")
    # save_action.triggered.connect(self.save_page)

    # 显示菜单
    menu.exec_(self.view.mapToGlobal(pos))

# def closeEvent(self, event):
#     # 窗口关闭时优雅终止后端（需要考虑一下，因为会导致关闭有延迟）
#     terminate_process_gracefully(self.backend_process, timeout=5)
#     event.accept()


# QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar) # 禁用原生菜单条样式

```

#### dependency-groups/dev

```toml
[dependency-groups]
dev = [
    "cachetools>=6.2.2",
    "duckdb>=1.4.1",
    "gradio-client>=2.0.1",
    "kafka-python>=2.2.16",
    "opencv-python>=4.11.0.86",
    "pymemcache>=4.0.0",
    "ring>=0.10.1",
    "tinydb>=4.8.2",
    "unqlite>=0.9.9",
```

#### pydantic-settings + lupa

```python
# region - template

# [note] [pydantic-settings 如何使用](https://lxblog.com/qianwen/share?shareId=ec78187b-f927-4c5e-9296-7cae4b461a6d)

class LuaConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: Type[BaseSettings], lua_file: Path, lua_file_encoding: str = "utf-8"):
        super().__init__(settings_cls)
        self.settings_cls = settings_cls
        self.lua_file = lua_file
        self.lua_file_encoding = lua_file_encoding

    def get_field_value(self, field: FieldInfo, field_name: str) -> Tuple[Any, str, bool]:
        config_dict = self._load_lua_config()
        if field_name in config_dict:
            return config_dict[field_name], field_name, True
        return None, field_name, False

    def _lua_table_to_python(self, lua, obj: Any) -> Union[Dict, List, Any]:
        """

        递归将 Lupa 的 LuaTable 转换为 Python 的 dict 或 list。
        - 如果 Lua 表是连续整数索引（1-based），视为 list。
        - 否则视为 dict。

        当前函数主要逻辑由 ai 生成

        """

        # 判断是否是 Lua 表：检查是否有 .items() 方法（这是 LuaTable 的特征）
        if hasattr(obj, 'items') and hasattr(obj, 'keys') and not isinstance(obj, (dict, list)):
            # 检查是否为数组式表（1,2,3,... 连续整数键）
            length = len(obj)
            if length > 0:
                # 尝试判断是否为纯数组：所有键为 1..length 的整数
                is_array = all(
                    isinstance(k, int) and 1 <= k <= length
                    for k in obj.keys()
                )
                if is_array:
                    return [self._lua_table_to_python(lua, obj[i]) for i in range(1, length + 1)]
            return {k: self._lua_table_to_python(lua, v) for k, v in obj.items()}

        # 其他类型（number, string, bool, None）直接返回
        return obj

    def _load_lua_config(self) -> Dict:
        lua = LuaRuntime()
        with open(self.lua_file, "r", encoding=self.lua_file_encoding) as f:
            lua_code = f.read()
        lua.execute(lua_code)
        config_table = lua.globals()["config"]
        return self._lua_table_to_python(lua, config_table)

    def __call__(self) -> Dict[str, Any]:
        return self._load_lua_config()


class DynamicSettings(BaseSettings):
    """动态配置即不需要修改代码的配置

    Details:
        1. settings_customise_sources 用于从 json 文件导入配置
        2. model_config 是 Pydantic v2 引入的新语法，用来替代 v1 中的 class Config:。
           - env_file: 指定 .env 文件路径
           - env_prefix: 环境变量前缀
           - case_sensitive: 是否区分大小写
           - extra: 如何处理未定义的字段
        3. 当前类定义的类属性会被自动填充到实例中
        4. 类字段如果未设置默认值，也无法从文件中导入，那么当前类初始化时，会直接报错
    """

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：初始化参数 > 环境变量 > .env > JSON/LUA 文件 > 默认值（相关配置文件）
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            LuaConfigSettingsSource(settings_cls, lua_file=Path("settings.lua"), lua_file_encoding="utf-8"),
            # JsonConfigSettingsSource(settings_cls, json_file=Path("settings.json"), json_file_encoding="utf-8"),
            file_secret_settings,
        )

    @field_validator("export_dir", mode="before")
    @classmethod
    def validate_export_dir(cls, value: str):
        log_enabled = False

        value = value.strip()

        # 1. 禁止显式包含 . 或 .. 作为路径组件（简单防御）
        parts = Path(value).parts
        if log_enabled:
            logger.debug("parts: {}", parts)
        if any(part in (".", "..") for part in parts):
            raise ValueError("路径中不能包含 '.' 或 '..'")

        # 2. 转为绝对路径并解析
        cwd = Path.cwd().resolve()
        resolved = (cwd / value).resolve()
        if log_enabled:
            logger.debug("resolved: {}", resolved)

        # 3. 确保最终路径在 cwd 内部（沙箱检查）
        try:
            resolved.relative_to(cwd)
        except ValueError as e:
            raise ValueError(f"路径必须位于当前工作目录下: {cwd}") from e

        return resolved

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    save_note_cooldown: int
    attachment_upload_text: str  # [note] python 可以这样使用 format："{0}".format(0)
    intruction_content: str
    title: str
    host: str
    version: str
    export_dir: Path
    prefix_import_values: List[str]





@functools.lru_cache()
def get_dynamic_settings():
    """惰性加载（真的有用吗）

    但是这将导致无法保证启动阶段就检查到报错，不太好吧？
    比如 save_note_cooldown 不设置默认值，然后相关配置文件也没有这个字段...

    """
    return DynamicSettings()  # noqa: Parameter 'save_note_cooldown' unfilled


dynamic_settings = get_dynamic_settings()  # 要不直接命名成 settings 吧，from settings import settings ...

# endregion
```