import functools
import inspect
import json
import asyncio
import threading
import queue
import atexit
import os
import re
import signal
import subprocess
import time
import traceback
import uuid
from pathlib import Path
from typing import List, Sequence, Callable, Annotated, Dict, AsyncGenerator, TypedDict, Any, Literal, Union, TypeVar, \
    Awaitable, Coroutine
from datetime import datetime, timedelta, timezone
from functools import partial

from pymemcache import Client
from result import Result, Ok, Err
from portpicker import pick_unused_port
from sqlalchemy.ext.asyncio import async_scoped_session, AsyncSession
from fastapi import Depends
from nicegui import background_tasks, ui
from nicegui.events import ValueChangeEventArguments

from models import AsyncSessionLocal, Attachment
from settings import dynamic_settings, ENV
# from services import UserConfigService # 【循环依赖】services 和 utils 可能会出现循环依赖
from mediator import get_user_config_service
from log import logger

from .cleanup import cleanup  # Usage: from utils import cleanup
from .ai import DeepSeekClient, build_ai_chain, audio_to_text_by_qwen3_asr
from .mediator import get_thread_pool_executor
from .timer import print_interval_time, IntervalTimer


class MiscUtils:
    pass


# region - template

A = TypeVar("A")


class Dependencies:
    """dependencies.py - fastapi Depends（目前暂未使用过，待定）"""

    @staticmethod
    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        """依赖项：提供异步数据库会话

        使用方式：
        - 在路由函数中：db: AsyncSession = Depends(get_db)

        """
        db = AsyncSessionLocal()
        try:
            yield db
        finally:
            await db.close()

    DBSession = Annotated[AsyncSession, Depends(get_db)]
    """类型别名（提高可读性）

    示例路由：
    @app.post("/users/", response_model=User)
    async def create_user(user: User, db: DBSession):
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    """


class _MemcachedManager:
    """嵌入式 memcached

    ai 生成，测试发现没问题，就是启动时会有 windows 弹窗，需要考虑用户关闭的情况...

    注意，memcached windows 版本似乎不好找...（推荐里了解一下 memcached 的原理）

    [嵌入式地使用 memcached](https://lxblog.com/qianwen/share?shareId=7d5a9614-2475-4b1c-8cd8-ab492201db6a)

    最佳实践建议：
    - 仅在开发/测试环境使用：生产环境应使用**系统服务**管理 memcached
    - 检查端口是否被占用：避免冲突
    - 日志重定向：可将 stdout/stderr 重定向到文件便于调试
    - 权限问题：确保 ./bin/memcached 有执行权限

    """

    def __init__(self):
        self.memcached_bin = os.path.join(os.getcwd(), "bin", "memcached", "memcached.exe")
        self.memcached_host = "127.0.0.1"
        self.memcached_port = pick_unused_port()
        self.memecached_pid: int | None = None
        self.registerd_stop_memcached = False
        self._client = None

    @property
    def client(self):
        if self._client is None:
            logger.debug("self.memcached_bin: {}", self.memcached_bin)
            logger.debug("self.memcached_port: {}", self.memcached_port)
            self._client = Client((self.memcached_host, self.memcached_port))
        return self._client

    def set(self, key: str, value: str):
        # 待定（client 使用示例而已）
        self.client.set(key, value)

    def get(self, key: str):
        # 待定（client 使用示例而已）
        return self.client.get(key)

    def start_memcached(self):
        if not os.path.exists(self.memcached_bin):
            raise FileNotFoundError(f"memcached binary not found at {self.memcached_bin}")

        # 注册退出清理函数（atexit good, os.kill good）
        if not self.registerd_stop_memcached:
            logger.debug("注册退出清理函数")
            atexit.register(self.stop_memcached)
            self.registerd_stop_memcached = True

        # 启动 memcached 子进程
        proc = subprocess.Popen(
            [self.memcached_bin, "-p", str(self.memcached_port), "-d", "-l", self.memcached_host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.memecached_pid = proc.pid

        logger.debug(f"Started memcached (PID: {proc.pid}) on port {self.memcached_port}")

    def stop_memcached(self):
        if self.memecached_pid:
            try:
                os.kill(self.memecached_pid, signal.SIGTERM)
                logger.debug("Stopped embedded memcached.")
            except ProcessLookupError:
                pass  # Already dead


memcached_manager = _MemcachedManager()


# todo: 改成装饰器 - 修饰 func，在函数入口进行探测，被限制则执行某段代码
# todo: RateLimiter 封装成装饰器需要提升日程
class RateLimiter:
    """速率限制器"""

    def __init__(self, cooldown_seconds: float = 1):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._last_call = datetime.min.replace(tzinfo=timezone.utc)

    def allow(self) -> bool:
        """返回是否允许执行操作"""
        now = datetime.now(timezone.utc)
        # 其实 now - last_call 大于 cooldown 即可（理解成技能冷却结束）
        logger.debug("(now - self._last_call): {} s", (now - self._last_call).total_seconds())
        if self._last_call + self.cooldown <= now:
            self._last_call = now
            return True
        return False

    def time_until_next_allowed(self) -> float:
        """返回还需等待多少秒（用于提示）"""
        now = datetime.now(timezone.utc)
        next_time = self._last_call + self.cooldown
        return max(0.0, (next_time - now).total_seconds())


async def refresh_page():
    """刷新当前页面"""
    await ui.run_javascript("location.reload()")


# endregion


class ConfigInfoTypedDict(TypedDict):
    options: List  # 可选择的范围
    option_name: str  # 数据库字段
    default: Any  # select 的默认值


# [note] 锻炼了封装和抽象能力，将功能抽象出来并封装起来
async def show_config_dialog(config_infos: Dict[str, ConfigInfoTypedDict], persistent: bool = False) -> None:
    """展示配置弹窗

    主要结构是：
                  关闭

        配置名1 | 配置项1
        配置名2 | 配置项2
        配置名3 | 配置项3

                  确认
    点击确认才进行数据更新，点击关闭按钮 dialog 才能关闭，
    每个配置名和数据库的字段对应

    Args:
        config_infos: Map，元素是 <配置名, 配置项>（List[Tuple] 其实也可以，而且似乎更好理解，且有序）
        persistent: dialog 是否是 persistent（即点旁边关不掉，但是有 bug，select 组件选择时可能会被关掉...）

    """
    if persistent:
        # dialog.props("persistent") 提示 Coroutine '__call__' is not awaited？？？
        dialog = ui.dialog().props("persistent")
    else:
        dialog = ui.dialog()

    # todo: 参考一下渲染模式的样式，那个看起来更舒服呀！
    with dialog, ui.card():
        # [step] ai answer: 右上角关闭按钮（用绝对定位）
        # [question] 绝对布局到底咋布局的？
        # [do] 当前 dialog 的布局我看起来还可以接受
        with ui.row().classes("w-full flex justify-end items-center pr-5"):
            close = ui.icon("close").classes("cursor-pointer text-blue text-lg rounded-lg hover:bg-gray-200 ")
            # close.classes("absolute top-2 right-2")
            close.on("click", dialog.close)
            # close = ui.button(icon="close", on_click=dialog.close)
            # close.props("flat ").classes("absolute top-2 right-2")

        with ui.grid(columns=3).classes("items-center"):
            # 存储所有 select 的值的映射
            select_values: Dict = {}
            for name, info in config_infos.items():
                ui.label(name).classes("text-center col-span-1")
                select_values[info["option_name"]] = info["default"]

                async def on_change(option_name: str, e: ValueChangeEventArguments):
                    # 更新 select_values 值，便于确认按钮时统一处理
                    select_values[option_name] = e.value

                # Shadows name 'select' from outer scope，但是其实只要没有用 nonlocal 等关键字，就不用担心！
                select = ui.select(info["options"], value=info["default"],
                                   on_change=partial(on_change, info["option_name"]))
                select.classes("col-span-2").props('input-style="text-align: center;"')

            async def on_confirm_click():
                modified = False
                for _, info in config_infos.items():
                    option_name = info["option_name"]
                    async with get_user_config_service()() as service:
                        select_value = select_values[option_name]
                        value = await service.get_value(option_name)
                        if select_value == value:
                            continue
                        modified = True
                        logger.debug("[on_confirm_click] option_name: {}, value: {}", option_name, select_value)
                        await service.set_value(option_name, select_value)
                if modified:
                    await refresh_page()
                dialog.close()

            ui.space().classes("col-span-2")
            ui.button("确定", on_click=on_confirm_click).classes("col-span-1").props("flat")

    dialog.open()


class FileUtils:
    pass


@functools.lru_cache()
def run_script(script_path: str, loader: str = "./") -> Dict | None:
    """动态读取并执行外部 Python 脚本，并根据其 __all__ 列表返回受限的命名空间。如果没有定义 __all__，则返回完整命名空间。

    :param script_path: 外部脚本的文件路径
    :param loader: 加载器（参考 jinja2，未来扩展为一个类）
    :return: 包含脚本执行后所有全局变量的字典，执行失败返回 None
    """
    start = time.perf_counter()
    # [note] 尽早出错（不得不说，JAVA 确实适合企业级项目）
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"脚本文件 '{script_path}' 不存在")
    if not path.is_file():
        raise FileNotFoundError(f"脚本文件 '{script_path}' 不是一个文件")
    try:
        namespace = {}
        with open(script_path, "r", encoding="utf-8") as f:
            exec(f.read(), namespace)
        if "__all__" in namespace:
            all_names = namespace["__all__"]
            if not isinstance(all_names, (list, tuple)):
                raise ValueError("__all__ 必须是 list 或 tuple")
            filtered_ns = {}
            for name in all_names:
                if name not in namespace:
                    raise AttributeError(f"__all__ 中包含未定义的名称: {name}")
                filtered_ns[name] = namespace[name]
            return filtered_ns
        return namespace
    except Exception as e:
        logger.error(f"{type(e).__name__} - {e}\n{traceback.format_exc()}============")
        return None
    finally:
        logger.debug(f"time interval: {(time.perf_counter() - start) * 1000:.4f} ms")


def is_valid_filename(filename: str) -> Result[bool, str]:
    # todo: run_script 应该也可以类似 lua 塞入 env，除此以外，建议这种脚本代码应该只能在前端回调中执行...
    #       总之，要思考这种情况的使用场景，但是不得不说，它有助于开发... pyinstaller 打包太麻烦...
    #       纯玩具，需要思考进一步的可行性...
    try:
        namespace = run_script("./scripts/is_valid_filename.py")
        result = namespace["is_valid_filename"](filename)
        return Ok(result)
    except Exception as e:
        logger.error("{} - {}\n{}============", type(e).__name__, e, traceback.format_exc())
        return Err(str(e))


def register_find_button_and_click(pressed_key: str, button_id: str, is_ctrl: bool = False):
    """注册 js 事件，找到某个按钮，然后点击"""
    context = {
        "button_id": button_id,
        "pressed_key": pressed_key,
        "is_ctrl": is_ctrl,
    }
    ui.add_head_html("<script>{0}</script>".format(ENV.get_template("find_button_and_click.js").render(context)))


def extract_urls(text):
    # 匹配以 http:// 或 https:// 开头的 URL
    # todo: 直接找正则表达式工具，必定有的，正则表达式推荐不要自己写！一定不要！
    url_pattern = r'https?://[^\s<>"{}|\\^`[\]]+'
    urls = re.findall(url_pattern, text)
    return urls


# region - template

class AsyncRunner:
    """复用后台线程 + 消息队列（生产级）

    启动一个长期运行的后台线程，维护一个事件循环，并通过队列提交任务，实现通过同步方式调用异步函数并等待其结果

    Details:
        1. 注册任务队列、结果队列、后台守护线程
        2. 守护线程尝试从任务队列获取任务，没有获取到则阻塞（线程 wait），任务来了就唤醒。
           唤醒后在守护线程的事件循环中执行异步任务，拿到结果后 put 到结果队列中
        3. 主线程调用 run 函数，它会往任务队列中 put 任务，然后进入 wait 状态等待后台线程唤醒它

    可能存在的问题：
        后台线程执行耗时任务或者过多任务时，主线程岂不是会卡住（但是说实在的，应该不算问题吧，
        cpu 不是本来就在一直执行，只要不是太耗时，那和主线程执行代码又有什么大的区别呢？）

    """

    def __init__(self):
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._status = "init"

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            coro = self.task_queue.get()
            if coro is None:
                break
            try:
                # logger.debug("[AsyncRunner:_run_loop] 运行协程并获取结果")
                result = loop.run_until_complete(coro)
                self.result_queue.put(("ok", result))
            except Exception as e:
                self.result_queue.put(("error", e))

    def register_timed_task(self, coro):
        """注册定时任务让守护线程执行"""
        # [2025-11-23]
        # 该函数是新增的，想复用守护线程。该守护线程最初的主要作用是与主线程交互，主线程将异步任务传递过来，等待守护线程执行完并返回结果。
        # 现在我想附加注册周期执行的定时器，暂时的实现设想：
        # 调用 self.run 传递一个类型下面这样的协程任务，
        """
        async def task():
            # asyncio.sleep 睡眠
            # 执行定时任务
            # 执行完毕后，向 self.task_queue 中再 put 一个自己
        """
        # 关于上面这个周期执行定时器，我的 cleanup 可以和当前类融合，
        # 最好能实现一个新的事件循环，让这个守护线程忙起来！

    def run(self, coro: Coroutine):
        """在已有事件循环中让异步任务在同步函数中执行并阻塞拿到结果

        :param coro: 不是 async 修饰的那个函数，而是那个函数（）的执行结果，即 Coroutine/Awaitable | Awaitable 也可以是 asyncio.create_task 返回值
        :return: coro 执行完的返回值
        """
        # 目前只考虑 coro 执行的返回值一个只有一个的清空，如果是多个，不知道拿到的是不是元组
        start_time = time.time()
        # logger.debug("[AsyncRunner:run] ■ 提交异步任务并同步等待结果")
        self.task_queue.put(coro)
        status, value = self.result_queue.get()
        # 人机交互研究中常用的经验法则 - 人类感知延迟阈值：延迟 < 10 ms，用户感受是即时响应，非常流畅
        interval = (time.time() - start_time) * 1000
        logger.debug(f"⏱️ 异步任务执行总耗时：{interval:.3f}ms（{coro.__name__}）")
        if interval > 10:
            logger.warning("[AsyncRunner:run] ⚠️ 异步任务执行总耗时超过 10 ms，发生延迟")
        if status == "error":
            raise value
        return value


@functools.lru_cache()
def get_async_runner() -> AsyncRunner:
    return AsyncRunner()


async def asyncify(sync_func: Callable[[], A], *args) -> A:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(get_thread_pool_executor(), sync_func, *args)  # noqa
    return result


sync_to_async = asyncify


def extract_bracketed_content(text: str, multiline: bool = False) -> List[str]:
    """
    提取文本中所有被 【】 包裹的内容

    Args:
        text: 输入字符串
        multiline: 是否允许匹配跨行内容

    Returns:
        所有匹配到的内容列表（不含括号）
    """
    flags = re.DOTALL if multiline else 0
    return re.findall(r"【(.*?)】", text, flags)


# endregion

# todo: utils.py 需要拆分了

def go_main():
    ui.navigate.to("/")


def go_add_note():
    ui.navigate.to(f"/add_or_edit_note?temporary_uuid={uuid.uuid4()}")


def go_edit_note(note_id: int, source: str = None):
    url = f"/add_or_edit_note?note_id={note_id}&temporary_uuid={uuid.uuid4()}"
    if source:
        url += f"&source={source}"
    ui.navigate.to(url)


def go_get_note(note_id: int, notify_from: Literal["add_note"] | None = None):
    url = f"/get_note?note_id={note_id}"
    if notify_from:
        url = url + "&notify_from=" + notify_from
    ui.navigate.to(url)
