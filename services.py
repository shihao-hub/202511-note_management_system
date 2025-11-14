import contextlib
from typing import List, Any, Coroutine, Sequence, Tuple, Union, TypeVar, Type

from addict import Dict as Addict
from sqlalchemy import select, update, delete, insert, Row, RowMapping, or_, desc, and_, func
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import DeclarativeMeta
from loguru import logger
from result import Ok, Err, Result

from settings import PAGE_SIZE
from models import AsyncSessionLocal, Note, Attachment

# [note] 项目较小时，services.py 多半是累赘，基础的 CRUD 本就不需要抽成单独的函数，当然如果多次使用，自然也是 ok 的
#        其实即使项目小，这样一个简单的拆分操作，也是很有益处的，建议还是优先考虑拆到 services.py 中吧


# region - template

# [note] Service 是我写的模板函数，但是 result 库是 ai 找到的，差不多是模仿 Rust 实现的第三方库，太秒了，太强了
#        但是我 rust 只理解皮毛，Err 里面是 Exception 类型还是就单纯的字符串呀？（我目前感觉是字符串，也可以是异常）

T = TypeVar("T", bound=DeclarativeMeta)  # 定义一个类型变量，约束为 SQLAlchemy 模型类（即 DeclarativeMeta 的子类）


class Service[T]:
    model: Type[T]  # # 子类必须设置为具体的模型类，如 User

    def __init__(self):
        self.db: AsyncSession | None = None

    async def __aenter__(self) -> "Service":
        self.db = AsyncSessionLocal()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            # 如果有异常，会自动回滚（SQLAlchemy 会处理）
            await self.db.close()
        # 返回 False 表示不抑制异常
        return False

    async def create(self, **kwargs) -> Result[T, str]:
        """C - 创建一个新记录"""
        try:
            instance = self.model(**kwargs)
            self.db.add(instance)
            await self.db.commit()
            await self.db.refresh(instance)  # 刷新对象，获取数据库返回的值
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def get(self, ident: int) -> Result[T, str]:
        """R - 根据主键获取一条记录"""
        try:
            instance = await self.db.get(self.model, ident)
            if instance is None:
                logger.debug(f"{self.model.__name__} {ident} doesn't exist")
                return Err(f"{self.model.__name__} {ident} doesn't exist")
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def update(self, ident: int, **kwargs) -> Result[T, str]:
        """U - 根据主键更新记录"""
        try:
            instance = await self.db.get(self.model, ident)
            if not instance:
                return Err(f"{self.model.__name__} {ident} doesn't exist")
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            await self.db.commit()
            await self.db.refresh(instance)
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def delete(self, ident: int) -> Result[bool, str]:
        """D - 根据主键删除记录"""
        try:
            instance = await self.db.get(self.model, ident)
            if not instance:
                return Err(f"{self.model.__name__} {ident} doesn't exist")
            await self.db.delete(instance)
            await self.db.commit()
            return Ok(True)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def list_all(self, order_by: str = "id", **kwargs) -> Result[Sequence[T], str]:
        """列出所有记录（无排序、无过滤）"""
        # todo: 参考 django 的 name__contains 去扩展 kwargs
        try:
            stmt = select(self.model)
            # region - 形如 -id 代表倒序排序
            is_desc = False
            if order_by.startswith("-"):
                is_desc = True
                order_by = order_by[1:]
            if not hasattr(self.model, order_by):
                raise AttributeError(f"{order_by}({self.model.__name__}) doesn't exist")
            order_by_field = getattr(self.model, order_by)
            logger.debug("order_by: {}, order_by_field: {}", order_by, order_by_field)
            if is_desc:
                stmt = stmt.order_by(desc(order_by_field))
            else:
                stmt = stmt.order_by(order_by_field)
            # endregion
            result = await self.db.execute(stmt)
            return Ok(result.scalars().all())
        except Exception as e:
            logger.error(e)
            return Err(str(e))


# endregion

class NoteService(Service[Note]):
    model = Note

    def __init__(self) -> None:
        super().__init__()

    async def get_notes(self, page: int = 1, search_filter: Union[Addict, None] = None) -> Sequence[Note]:
        # todo: 实现一个过滤类，用于搜索功能，主要搜索 title 和 content？

        if search_filter is None:
            result = await self.db.execute(select(Note)
                                           .offset((page - 1) * PAGE_SIZE)
                                           .limit(PAGE_SIZE)
                                           .order_by(Note.id))
        else:
            # search 为 "" 时，contains 可以忽略，即全部匹配
            search = search_filter.search_content
            stmt = (select(Note)
                    .filter(or_(Note.title.contains(search), Note.content.contains(search)))
                    .offset((page - 1) * PAGE_SIZE)
                    .limit(PAGE_SIZE)
                    .order_by(Note.id))
            """结合 offset 实现分页
            
            # 跳过前 20 条，取 10 条（第 3 页，每页 10 条）
            users = session.query(User).offset(20).limit(10).all()
            
            """
            result = await self.db.execute(stmt)

        return result.scalars().all()

    async def get_note_with_attachments(self, ident: int) -> Result[Note, str]:
        try:
            stmt = select(Note).where(Note.id == ident).options(selectinload(Note.attachments))
            result = await self.db.execute(stmt)
            instance = result.scalar_one_or_none()
            if instance is None:
                return Err(f"{self.model.__name__} {ident} doesn't exist")
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def count_note(self, search_filter: Union[Addict, None] = None) -> Result[int, str]:
        try:
            if search_filter is None:
                result = await self.db.execute(select(func.count(Note.id)))
            else:
                search = search_filter.search_content
                stmt = select(func.count(Note.id)).filter(
                    or_(Note.title.contains(search), Note.content.contains(search)))
                result = await self.db.execute(stmt)
            return Ok(result.scalar())
        except Exception as e:
            logger.error(e)
            return Err(str(e))


class AttachmentService(Service[Attachment]):
    model = Attachment

    async def get_by_filename(self, ident: int, filename: str) -> Result[Attachment, str]:
        try:
            result = await self.db.execute(select(Attachment).filter(and_(
                Attachment.id == ident,
                Attachment.filename == filename
            )))
            instance = result.scalar_one_or_none()
            if instance is None:
                raise Exception(f"Attachment {ident}-{filename} doesn't exist")
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def update_by_temporary_uuid(self, _uuid: str, **kwargs) -> Result[int, str]:
        """通过 temporary_uuid 查询并批量更新"""
        try:
            logger.debug("[update_by_temporary_uuid] temporary_uuid: {}", _uuid)
            stmt = update(Attachment).where(Attachment.temporary_uuid == _uuid).values(**kwargs)
            result = await self.db.execute(stmt)
            await self.db.commit()
            logger.debug("result: {}", result)
            return Ok(0)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def count_attachment(self, note_id: int) -> Result[int, str]:
        try:
            # id 是主键列，通常作为计数的列。因为主键不允许为 NULL，所以 COUNT(User.id) 等同于 COUNT(*)。
            stmt = select(func.count(Attachment.id)).filter(Attachment.note_id == note_id)
            result = await self.db.execute(stmt)
            count = result.scalar()  # 使用 .scalar() 获取单个计数值
            logger.debug("[count_attachment] count: {}", count)
            return Ok(count)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def count_attachment_by_temporary_uuid(self, temporary_uuid: str) -> Result[int, str]:
        try:
            stmt = select(func.count(Attachment.id)).filter(Attachment.temporary_uuid == temporary_uuid)
            result = await self.db.execute(stmt)
            count = result.scalar()
            logger.debug("[count_attachment_by_temporary_uuid] count: {}", count)
            return Ok(count)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def get_attachments_by_note_id(self, note_id: int) -> Result[Sequence[Attachment], str]:
        try:
            stmt = select(Attachment).filter(Attachment.note_id == note_id)
            result = await self.db.execute(stmt)
            attachments = result.scalars().all()
            logger.debug("[get_attachments_by_note_id] attachments: {}", attachments)
            return Ok(attachments)
        except Exception as e:
            logger.error(e)
            return Err(str(e))
