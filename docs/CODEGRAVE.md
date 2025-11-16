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