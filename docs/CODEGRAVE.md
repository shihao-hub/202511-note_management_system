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