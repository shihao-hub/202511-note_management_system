import contextlib
import functools
from typing import List, Any, Coroutine, Sequence, Tuple, Union, TypeVar, Type, Dict, TypedDict

from sqlalchemy import select, update, delete, insert, Row, RowMapping, or_, desc, and_, func, exists
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import DeclarativeMeta
from loguru import logger
from result import Ok, Err, Result

from models import AsyncSessionLocal, Note, Attachment, UserConfig

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

class SearchFilterTypedDict(TypedDict):
    search_content: str | None
    has_attachment: bool | None
    order_by: str | None


class NoteService(Service[Note]):
    model = Note

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    async def build_filter_statement(cls,
                                     page: int | None = 1,
                                     search_filter: Dict | None = None,
                                     select_field=Note):
        """构建过滤语句（临时不完美方案，饭要一口一口吃）

        一步一步来，先实践，写小函数，需求复杂后完善，再考虑抽成类（所以啊，编程就是要多练习...）

        Args:
            page: 页号，page 为 None，代表不进行分页
            search_filter: 自定义过滤 Dict（易变）
            select_field: select(...) 中传递的参数，暂不够明确

        """
        async with UserConfigService() as user_config_service:
            page_size = await user_config_service.get_page_size()

        logger.debug("search_filter: {}", search_filter)
        search_filter = search_filter or {}
        search_content = search_filter.get("search_content", None)
        has_attachment = search_filter.get("has_attachment", None)
        note_type = search_filter.get("note_type", None)
        order_by = search_filter.get("order_by", "-updated_at")  # 默认按 updated_at 倒叙排列

        stmt = select(select_field)

        # 自定义格式 - 搜索标题和正文
        if search_content is not None:
            # search_content 为 "" 时，contains 可以忽略，即全部匹配
            stmt = stmt.filter(or_(Note.title.contains(search_content), Note.content.contains(search_content)))

        # 自定义格式 - 有附件（无附件暂时就不处理了，True/False/None 三进制）
        if has_attachment is True:  # noqa
            stmt = stmt.where(exists().where(Attachment.note_id == Note.id))
        elif has_attachment is False:  # noqa
            stmt = stmt.where(~exists().where(Attachment.note_id == Note.id))

        if note_type is not None:
            stmt = stmt.where(Note.note_type == note_type)

        # region - order-by
        is_desc = False
        if order_by.startswith("-"):
            order_by = order_by[1:]
            is_desc = True
        order_by_field = getattr(cls.model, order_by, None)
        if order_by_field is None:
            raise AttributeError(f"{order_by}({cls.model.__name__}) doesn't exist")
        if is_desc:
            order_by_field = desc(order_by_field)
        # endregion
        logger.debug("order_by: {}, order_by_field: {}", order_by, order_by_field)

        stmt = stmt.order_by(order_by_field)

        if page is None:
            return stmt

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        """结合 offset 实现分页

        # 跳过前 20 条，取 10 条（第 3 页，每页 10 条）
        users = session.query(User).offset(20).limit(10).all()

        """

        return stmt

    async def get_notes(self, page: int = 1, search_filter: Dict | None = None) -> Sequence[Note]:
        """在有过滤和分页的情况下获取 Note List"""
        stmt = await self.build_filter_statement(page=page, search_filter=search_filter)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_note_with_attachments(self, ident: int) -> Result[Note, str]:
        """获得有附件的 Note"""
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

    async def count_note(self, search_filter: Dict | None = None) -> Result[int, str]:
        """在有过滤的情况下，统计 Note 数量"""
        try:
            stmt = await self.build_filter_statement(page=None,
                                                     search_filter=search_filter,
                                                     select_field=func.count(Note.id))
            result = await self.db.execute(stmt)
            count = result.scalar()
            if not isinstance(count, int):
                raise TypeError(f"{count} is not int")
            logger.debug("count_note: {}, search_filter: {}", count, search_filter)
            return Ok(count)
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


class UserConfigService(Service[UserConfig]):
    model = UserConfig

    async def init_user_config(self):
        # 由于没有登录系统，所以用户配置表最多只有一条数据，软件启动阶段就将其创建出来
        result = await self.db.execute(select(UserConfig))
        user_config = result.scalars().first()
        logger.debug("[init_user_config] user_config: {}", user_config)
        # 配置不存在则创建，配置存在则考虑更新
        if user_config is None:
            await self.db.execute(insert(UserConfig))
            await self.db.commit()
        else:
            # 与默认值比对，如果数据库中该键值对不存在，则添加
            default = UserConfig.default_user_profile()
            modified = False
            for name, value in default.items():
                if user_config.profile.get(name) is None:
                    user_config.profile[name] = value
                    logger.debug("init user_config.profile[{}]: {}", name, value)
                    modified = True
            if modified:
                flag_modified(user_config, "profile")
                await self.db.commit()

    async def _get_user_config(self):
        result = await self.db.execute(select(UserConfig))
        config = result.scalars().first()
        if config is None:
            exc = Exception(f"UserConfigService.init_user_config() failed")
            logger.error(exc)
            raise exc
        return config

    async def get_value(self, key: str) -> Any | None:
        config = await self._get_user_config()
        res = config.profile.get(key)
        logger.debug("[get_value] config.profile[{}]: {}", key, res)
        return res

    async def set_value(self, key: str, value):
        config = await self._get_user_config()
        config.profile[key] = value
        logger.debug("[set_value] config.profile[{}]: {}", key, value)
        # 显式标记 profile 字段已修改
        flag_modified(config, "profile")
        # SQLAlchemy 检测到变更，自动替换为 UPDATE 语句
        await self.db.commit()

    # @functools.lru_cache() # 调用 get_page_size.cache_clear() 方法，会清空该函数的所有缓存条目
    async def get_page_size(self):
        config = await self._get_user_config()
        page_size = config.profile.get("page_size")
        if page_size is None:
            raise Exception(f"UserConfigService.init_user_config() failed, page_size is None")
        return page_size
