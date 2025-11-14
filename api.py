import contextlib
import sqlite3
import asyncio
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import List

from loguru import logger
from fastapi import Request, UploadFile, File, FastAPI
from fastapi.websockets import WebSocket
from fastapi.exceptions import HTTPException
from nicegui import app
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from services import AttachmentService
from schemas import SuccessResponse
from utils import cleanup

# [note] StreamingResponse 是流式返回，FileResponse 直接传入文件路径

# [note] 任何技术的原始层面的锻炼是非常重要的，比如 sql 语句，虽然 orm 节省功夫且可以立刻干活，但是还是要用 sql 语句写项目锻炼的！

# [note] 先使用 orm 再使用 sql 吧，毕竟 orm 熟练，再做出来一个版本后，再考虑换成原生 sql 锻炼一下

# [note] nicegui 根本不需要再定义 api，因为那将导致两次网络请求...

# 创建线程池用于异步执行数据库操作
db_executor = ThreadPoolExecutor(max_workers=5)

@contextlib.asynccontextmanager
async def lifespan(app_: FastAPI):
    # 应用启动时初始化
    logger.debug("startup")
    await cleanup.start()
    yield
    # 应用关闭时清理资源
    logger.debug("shutdown")
    await cleanup.stop()

fastapi_app = FastAPI() # lifespan=lifespan 不生效，理由未知

limiter = Limiter(key_func=get_remote_address)

fastapi_app.state.limiter = limiter

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
    except Exception as e:  # noqa
        # print("Client disconnected")
        # logger.error(e)
        pass


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


@fastapi_app.post("/upload", summary="文件上传", response_model=SuccessResponse)
@limiter.limit("1/second")
async def upload_file(request: Request, note_id: int = None,
                      temporary_uuid: str = None, files: List[UploadFile] = File(...)):
    logger.debug("[upload_file] start")
    # [knowledge] fastapi File 和 UploadFile 注解

    # todo: upload 只是上传，真正的情况应该需要保存笔记时再存储，所以 note_id 不该存在

    logger.debug("temporary_uuid: {}", temporary_uuid)
    logger.debug("note_id: {}", note_id)

    if temporary_uuid is None and note_id is None:
        raise HTTPException(400, "temporary_uuid and note_id is required")

    failed_num = 0
    for file in files:
        content = await file.read()
        async with AttachmentService() as service:
            result = await service.create(
                filename=file.filename,
                content=content,
                mimetype=file.content_type,
                size=file.size,
                note_id=note_id,
                temporary_uuid=temporary_uuid
            )
            if result.is_err():
                failed_num += 1

    return {"message": f"上传文件成功，失败数量 {failed_num} 个"}


@fastapi_app.get("/view_file", summary="查看文件")
async def view_file(request: Request, file_id: int):
    logger.debug("[view_file] start")

    # todo: 添加缓存

    # 正常情况，文件必定存在，不存在的情况暂不考虑
    async with AttachmentService() as service:
        result = await service.get(file_id)
        file = result.unwrap()

    filename = file.filename
    ascii_name = filename.encode("ascii", "ignore").decode("ascii")
    encoded_filename = urllib.parse.quote(filename, encoding="utf-8")

    # Content-Disposition 的 inline 可改为 attachment 实现强制下载
    headers = {
        # 参考：[文件名包含非 ASCII 字符](https://lxblog.com/qianwen/share?shareId=47782eed-a1c4-43d8-8651-b8bf2e3aad05)
        "Content-Disposition": f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_filename}'
    }
    return Response(
        file.content,
        media_type=file.mimetype,
        headers=headers
    )
