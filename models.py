import re
import pytz
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, func, Integer, String, Text, ForeignKey, BLOB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, async_scoped_session
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr, relationship
from sqlalchemy_utc import UtcDateTime, utcnow
from loguru import logger

# region - template

DATABASE_URL = "sqlite:///./notes.db"
async_engine = create_async_engine("sqlite+aiosqlite:///./notes.db", echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def init_db():
    """初始化数据库：创建所有在 Base.metadata 中定义的表。如果表已存在，则不会重复创建。"""
    logger.info("Initializing database")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow(), onupdate=utcnow(), nullable=False)

    @declared_attr
    def __tablename__(cls) -> str:  # noqa: cls is the class, not an instance
        """将一个类名（或任意字符串）从驼峰命名法转换为蛇形命名法

        r"(?<!^)(?=[A-Z])"是一个零宽断言（zero-width assertion）组合

        """
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()

    def __getattribute__(self, name: str) -> Any:
        attr = super().__getattribute__(name)

        # fixme: 考虑一下，是否应该转为实例方法，即应用层转换，目前有点类似数据库层转换了（虽然数据库未变化）
        # 属性被读取时，进行转换
        if name in ["created_at", "updated_at"] and isinstance(attr, datetime):
            if attr.tzinfo is not None:
                # 转为北京时间
                aware_dt = attr.astimezone(pytz.timezone("Asia/Shanghai"))
                # 移除转为字符串后的 +08:00 这个时区信息 + 将微秒置为0，确保转字符串时无小数点
                naive_dt = aware_dt.replace(tzinfo=None, microsecond=0)
                return naive_dt

        return attr


# endregion

class Note(Base):
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    # [knowledge] backref 可以只在一个表中定义，另一个表会自动创建
    attachments = relationship("Attachment", back_populates="note", cascade="all, delete-orphan")
    """ORM层面的级联删除
    
    cascade="all, delete-orphan"：当Parent对象被删除时，所有关联的Child对象也会被删除
    delete-orphan：当关联关系被移除时（如parent.children = []），被移除的Child对象会被删除
    
    """


class Attachment(Base):
    filename = Column(String(255), comment="原始文件名", nullable=False)
    content = Column(BLOB, comment="文件二进制内容", nullable=False)
    mimetype = Column(String(100), comment="MIME类型（如 application/pdf）", nullable=False)
    size = Column(Integer, comment="文件大小，单位字节", nullable=False)
    note_id = Column(Integer, ForeignKey("note.id"), comment="特别使用，允许为空")
    temporary_uuid = Column(String(64), comment="临时使用的标识，能模拟临时表效果的字段，也允许为空")

    note = relationship("Note", back_populates="attachments")
