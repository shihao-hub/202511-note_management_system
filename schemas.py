from functools import partial

from typing import Any, Optional, Generic, TypeVar
from datetime import datetime, timezone

from pydantic import BaseModel, Field

# todo: 较为熟练地使用 pydantic

# region - template
T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """成功响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="响应消息")
    data: T | None = Field(None, description="响应数据")
    timestamp: datetime = Field(default_factory=partial(datetime.now, tz=timezone.utc), description="时间戳")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorDetail(BaseModel):
    """错误详情模型"""
    field: str | None = Field(None, description="错误字段")
    detail: str = Field(..., description="错误详情")
    type: str | None = Field(None, description="错误类型")
    value: Any | None = Field(None, description="错误值")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    error: ErrorDetail | None = Field(None, description="错误详情")
    timestamp: datetime = Field(default_factory=partial(datetime.now, tz=timezone.utc), description="时间戳")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
# endregion
