import os
import traceback
import urllib.parse
import webbrowser
import tempfile
from typing import List

from loguru import logger
from fastapi import Request, UploadFile, File, FastAPI
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from nicegui import app

from services import AttachmentService
from schemas import SuccessResponse
from utils import audio_to_text_by_qwen3_asr

# [note] StreamingResponse 是流式返回，FileResponse 直接传入文件路径
# [note] 任何技术的原始层面的锻炼是非常重要的，比如 sql 语句，虽然 orm 节省功夫且可以立刻干活，但是还是要用 sql 语句写项目锻炼的！
# [note] 先使用 orm 再使用 sql 吧，毕竟 orm 熟练，再做出来一个版本后，再考虑换成原生 sql 锻炼一下
# [note] nicegui 根本不需要再定义 api，因为那将导致两次网络请求...

fastapi_app = FastAPI()

# 简单的限流器，最低只能设置 1 秒 1 次（我想要的是这个效果，因为某个时间段限制次数依旧可以做到一瞬间一堆次数）
limiter = Limiter(key_func=get_remote_address)


@app.get("/open-external-link")
def open_external_link(url: str):
    webbrowser.open(url)
    return {"status": "ok"}


@fastapi_app.post("/upload", summary="文件上传", response_model=SuccessResponse)
@limiter.limit("1/second")
async def upload_file(request: Request, temporary_uuid: str, files: List[UploadFile] = File(...)):
    logger.debug("[upload_file] start")
    logger.debug("temporary_uuid: {}", temporary_uuid)

    # [knowledge] fastapi File 和 UploadFile 注解

    failed_num = 0
    for file in files:
        content = await file.read()
        async with AttachmentService() as service:
            result = await service.create(
                filename=file.filename,
                content=content,
                mimetype=file.content_type,
                size=file.size,
                note_id=None,
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
        if result.is_err():
            raise HTTPException(status_code=400, detail=f"file {file_id} not found")
        file = result.unwrap()

    filename = file.filename
    ascii_name = filename.encode("ascii", "ignore").decode("ascii")
    encoded_filename = urllib.parse.quote(filename, encoding="utf-8")

    # [note] [文件名包含非 ASCII 字符](https://lxblog.com/qianwen/share?shareId=47782eed-a1c4-43d8-8651-b8bf2e3aad05)
    # Content-Disposition 的 inline 可改为 attachment 实现强制下载
    headers = {
        "Content-Disposition": f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_filename}'
    }
    return Response(
        file.content,
        media_type=file.mimetype,
        headers=headers
    )


@fastapi_app.post("/speech_recognition", summary="语音识别，文件上传", response_model=SuccessResponse)
async def speech_recognition(request: Request, file: UploadFile = File(...)):
    try:
        # [2025-11-20] 完成，但未测试，待定。

        # 根据上传文件名推断后缀，默认 .wav，便于 H5 使用 webm/ogg 等容器
        ext = os.path.splitext(file.filename)[1] or ".wav"

        # NamedTemporaryFile：创建一个有名字的临时文件，可以通过 .name 获取路径 | 默认在关闭时自动删除（可通过 delete=False 禁用）
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
            f.write(await file.read())
            f.seek(0)
            f.flush()  # 确保写入磁盘（如果需要外部程序读取）

        # with 外自动关闭临时文件（因为会提示），但不删除，拿到语音调用结果后再删除
        text = await audio_to_text_by_qwen3_asr(f.name)
        logger.debug("删除临时文件：{}", f.name)
        os.remove(f.name)

        # 如何不说话，会返回：text == "响应结构不完整"，需要考虑处理

        return {"data": text}
    except Exception as e:
        # todo: 此处的日志需要详细打印出来，建议 logger.error 必须打印调用栈！（还需要兼容异步栈）
        #       js 层的日志 native 后上哪找？触发事件传导到后端？
        logger.error("{}({})\n{}============", e, type(e), traceback.format_exc())
        raise HTTPException(status_code=400, detail="语音识别失败")
