import contextlib
import re
import enum
import urllib.parse
from datetime import datetime
from typing import Any, TypedDict, Literal, List, Dict

from alembic import command
from alembic.config import Config
from contextvars import ContextVar
from sqlalchemy import Column, DateTime, func, Integer, String, Text, ForeignKey, BLOB, Enum, JSON, UniqueConstraint
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, async_scoped_session, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr, relationship
from sqlalchemy_utc import UtcDateTime, utcnow

from log import logger


# region - template

def _get_async_database_url(sync_url: str) -> str:
    """将同步数据库 URL 转换为异步版本"""
    if not sync_url:
        raise ValueError("Database URL is empty or not configured in alembic.ini")

    # urllib.parse 解析 sqlite:/// 可能存在问题
    # parsed = urllib.parse.urlparse(sync_url)

    # SQLite 特殊处理（直接字符串替换，简单场景可用）
    if sync_url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + sync_url[len("sqlite://"):]

    # 可扩展：PostgreSQL / MySQL 等
    # 默认：假设已经是异步 URL 或无需转换
    return sync_url


alembic_cfg = Config("alembic.ini")
sync_database_url = alembic_cfg.get_main_option("sqlalchemy.url")
async_database_url = _get_async_database_url(sync_database_url)
async_engine = create_async_engine(
    async_database_url,
    echo=False,  # 生产设为 False
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,  # 避免提交后对象失效
    autoflush=False,  # 手动控制 flush
)


async def init_db():
    """初始化数据库

    Usage:
        1. 在 @app.on_startup 中使用
        2. 主要用于做一些初始化操作，如：默认数据等

    """
    logger.info("🗃️ Initializing database")


async def auto_upgrade_db():
    """自动迁移数据库

    Usage:
        1. 开发阶段会使用 reload 不建议自动执行这段命令
        2. 在 @app.on_startup 中使用

    """
    logger.info("🚀 执行 alembic 数据库迁移命令")
    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(e)
        raise e


_current_session: ContextVar[AsyncSession | None] = ContextVar("_current_session", default=None)


@contextlib.asynccontextmanager
async def db_session():
    """

    Usage:
        async def get_note(note_id: int) -> Optional[Note]:
            session = get_db_session()
            return await session.get(Note, note_id)

        async with db_session():
            note = await get_note(1)

    """
    session = AsyncSessionLocal()
    token = _current_session.set(session)
    try:
        yield session
        await session.commit()
    except Exception as e:
        logger.error(e)
        await session.rollback()
        raise
    finally:
        await session.close()
        _current_session.reset(token)  # 清理上下文，防止内存泄漏


def get_db_session() -> AsyncSession:
    """协程安全的 session 上下文，在任意地方安全获取当前 session

    Details:
        1. ContextVar（_current_session） 是协程隔离的，多个协程之间无法共享同一个 ContextVar 的值
        2. 当前函数会自动从 _current_session 获取 session，不存在则出错，因为未提前执行 db_session 初始化 _current_session

    """
    session = _current_session.get()
    if session is None:
        raise RuntimeError(
            "No active database session. "
            "Wrap your code with `async with db_session():`"
        )
    return session


class Base(DeclarativeBase):
    """全局基类

    Details:
        1. 时间类字段使用 UtcDateTime 类，通过 orm 创建数据时，自动填充 UTC 类型的数据到数据库中
        2. 自动根据类名生成表名（参考）
        3. 时间属性从数据库读取并实例化时，转为本地时间（不带时区和微秒数）的 datetime 的实例

    """
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
                utc_dt = attr
                # 转换为本地时间（naive，不带时区 + 微秒置为 0）
                local_dt = utc_dt.astimezone().replace(tzinfo=None, microsecond=0)
                return local_dt
        return attr

    @staticmethod
    def utc_to_local(utc_dt: datetime, result_no_tzinfo: bool = True, result_no_microsecond: bool = True):
        """将 utc 时间转当地时间"""
        replace = {}
        if result_no_tzinfo:
            replace["tzinfo"] = None
        if result_no_microsecond:
            replace["microsecond"] = 0
        return utc_dt.astimezone().replace(**replace)


# endregion

# -------------------------------------------------------------------------------------------------------------------- #

# todo: 转 enum.Enum 与数据库字段搭配映射，让 ide 提供智能提示功能
class NoteTypeMaskedEnum:
    DEFAULT = "default"  # 为了避免混淆，强烈建议显式使用字符串值，不要使用 enum.auto()（默认为 1）
    HYPERLINK = "hyperlink"
    BOOKMARK = "bookmark"
    TODO = "todo"
    ARCHIVE = "archive"

    # ARCHIVE = "archive"
    # SHORT_NOTE = "short_note"  # 短笔记，可以通过动态判断内容（比如保存的时候），也可以通过归档的方法分类

    @classmethod
    def to_dict(cls) -> Dict[str, str]:
        return {
            cls.DEFAULT: "普通笔记",
            cls.HYPERLINK: "链接笔记",
            cls.BOOKMARK: "书签笔记",
            cls.TODO: "待办笔记",
            cls.ARCHIVE: "归档笔记",
            # cls.SHORT_NOTE: "短笔记",
        }


class TagSourceEnum(enum.Enum):
    USER = "user"
    AUTO = "auto"


class NoteDetailRenderTypeEnum(enum.Enum):
    """
    note_detail_render_type = Column(Enum(NoteDetailRenderType), default=NoteDetailRenderType.LABEL)  # 笔记详情的渲染类型
    但是我选择使用 JSON 字段替代
    """
    LABEL = "label"
    MARKDOWN = "markdown"

    @classmethod
    def values(cls) -> List[str]:
        return list(map(lambda x: x.value, cls.__members__.values()))


class UserProfileTypedDict(TypedDict):
    """
    profile: Mapped[UserProfile] = Column(JSON, default=dict)
    但是这个类型注解导致我使用 profile 只能传入字面量，无法传入动态值，因为会被 ide 警告
    """
    note_detail_render_type: str  # NoteDetailRenderTypeEnum
    note_detail_autogrow: bool
    page_size: int  # 3 的倍数
    home_select_option: str  # NoteTypeMaskedEnum
    search_content: str
    note_content_rows: int
    tag_select: str
    current_page: int


# -------------------------------------------------------------------------------------------------------------------- #

class Note(Base):
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    # todo: 这个导致每次过滤都需要添加这个字段，很麻烦吧？没有别的办法吗？我觉得不应该！
    #       所以 stmt 必须调用某个函数再去执行？或者封装一下 self.db.execute？
    note_type = Column(Text, server_default=NoteTypeMaskedEnum.DEFAULT)
    # todo: https://www.qianwen.com/share?shareId=4195847b-bf2a-4ab8-88b5-1295b36762fa
    #       default 和 server_default 字段用起来很奇怪，
    #       目前的看法是，建表时无所谓，新增字段时，没有 server_default 旧数据肯定都是 NULL 了
    visit = Column(Integer, comment="访问次数", server_default="0")

    # [knowledge] backref 可以只在一个表中定义，另一个表会自动创建
    attachments = relationship("Attachment", back_populates="note", cascade="all, delete-orphan", lazy="select")
    """ORM层面的级联删除

    cascade="all, delete-orphan"：当Parent对象被删除时，所有关联的Child对象也会被删除
    delete-orphan：当关联关系被移除时（如parent.children = []），被移除的Child对象会被删除

    """

    tags = relationship("Tag", back_populates="note", cascade="all, delete-orphan")

    # todo: 新增 metadata 字段，json 格式，用于存储一些自定义的额外信息！


class Tag(Base):
    name = Column(String(200), comment="标签名", unique=True, nullable=False)
    # 如何和 enum 绑定在一起啊？
    source = Column(String(200), comment="标签来源", server_default=TagSourceEnum.AUTO.value)
    # SQLite + Alembic 的组合在 batch 模式下不允许匿名约束，必须显式命名，理由未知（可能是新增列）
    # 说实在的，不如用原生 sql 进行版本管理... 否则要么是踩坑、要么是阅读文档、要么是阅读源代码...
    note_id = Column(Integer, ForeignKey("note.id", name="fk_tag_note_id"), comment="特别使用，允许为空")
    note = relationship("Note", back_populates="tags", lazy="select")

    __table_args__ = (
        UniqueConstraint("name", name="name_tags_name"),  # 标签名唯一约束，否则 migrate 检测不到
    )


class Attachment(Base):
    """

    [2025-11-23]
        给除 content 表外的数据都加上索引，期望可能弥补一下。
        因为理解错了 sqlite 的对手是文件系统这句话！
        大于 100KB 的文件依旧不能存在 sqlite 数据库中！

    """
    filename = Column(String(255), comment="原始文件名", nullable=False, index=True)
    content = Column(BLOB, comment="文件二进制内容", nullable=False)
    mimetype = Column(String(100), comment="MIME类型（如 application/pdf）", nullable=False, index=True)
    size = Column(Integer, comment="文件大小，单位字节", nullable=False, index=True)
    temporary_uuid = Column(String(64), comment="临时使用的标识，能模拟临时表效果的字段，也允许为空", index=True)
    note_id = Column(Integer, ForeignKey("note.id"), comment="特别使用，允许为空", index=True)  # [2025-11-23] 外键加索引
    note = relationship("Note", back_populates="attachments")


# todo: 分表，将大文件单独存储在另一张表中，然后给 id 建立索引（勉强算分表吧！）
#       真正的分表：1. 按某字段值的范围切分，如：User0 User1 User2 等，每张表 1000 万条数据 2. 对字段值做 hash 再取模来决定落在哪张表中


class UserConfig(Base):
    @staticmethod
    def default_user_profile() -> UserProfileTypedDict:
        """除了新建表时使用，后续新增内容时，为了保证兼容性，也会使用该函数"""
        # [2025-11-20] 注意，json 有如下类型 string number object array boolean null，其中：
        #              string   - ui.select/ui.input（枚举用 ui.select）
        #              number   - ui.number/ui.input/ui.select（枚举用 ui.select，浮点数用 ui.input）
        #              object   - ?（嵌套 dialog 也可以，但是尽量避免吧）
        #              array    - ui.select
        #              boolean  - ui.switch
        #              null     - ?（null 肯定不会单独出现，ui.select(["(null)"] 勉强可以表达，但是不建议！）
        #
        return {
            "note_detail_render_type": NoteDetailRenderTypeEnum.LABEL.value,  # ui.select
            "note_detail_autogrow": False,  # ui.switch
            "page_size": 6,  # ui.number
            "home_select_option": NoteTypeMaskedEnum.DEFAULT,  # ui.select
            "search_content": "",  # ui.input
            "note_content_rows": 10,
            "tag_select": "(null)",
            "current_page": 1
        }

    # [2025-11-24] 人傻了，直接建一张表，key value type 三个字段不就行了？根据 type 处理序列化和反序列化就可以了...
    #              也就是说，无嵌套结构 json 没必要，有嵌套结构不涉及深度嵌套搜索，似乎也没有必要...
    # todo: 能否搞个 :memory: 访问？
    # todo: 仔细考虑一下 user_config.profile 该如何是好，如果将所有 select 相关类似选项都视为 profile，然后通过刷新页面的方式，可以很轻松实现很多功能！
    profile = Column(JSON, comment="动态字段，缓解关系型数据库的弊端", default=lambda: UserConfig.default_user_profile())
