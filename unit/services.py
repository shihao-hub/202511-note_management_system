import asyncio
from collections import namedtuple
from typing import Any, Sequence, TypeVar, Type, Dict, TypedDict, Annotated, List

from loguru import logger
from result import Ok, Err, Result
from sqlalchemy import select, update, insert, or_, desc, and_, func, exists, delete
from sqlalchemy.orm import Bundle
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from models import (
    AsyncSessionLocal, NoteTypeMaskedEnum, TagSourceEnum,
    Note, Attachment, UserConfig, Tag
)
from utils import print_interval_time

# [note] 项目较小时，services.py 多半是累赘，基础的 CRUD 本就不需要抽成单独的函数，当然如果多次使用，自然也是 ok 的
#        其实即使项目小，这样一个简单的拆分操作，也是很有益处的，建议还是优先考虑拆到 services.py 中吧


# region - template

# [note] Service 是我写的模板函数，但是 result 库是 ai 找到的，差不多是模仿 Rust 实现的第三方库，太秒了，太强了
#        但是我 rust 只理解皮毛，Err 里面是 Exception 类型还是就单纯的字符串呀？（我目前感觉是字符串，也可以是异常）

M = TypeVar("M", bound=DeclarativeMeta)  # 定义一个类型变量，约束为 SQLAlchemy 模型类（即 DeclarativeMeta 的子类）


class Service[M]:
    model: Type[M]  # # 子类必须设置为具体的模型类，如 User

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

    async def create(self, **kwargs) -> Result[M, str]:
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

    async def get(self, ident: int) -> Result[M, str]:
        """R - 根据主键获取一条记录"""
        try:
            instance = await self.db.get(self.model, ident)
            if instance is None:
                logger.error(f"{self.model.__name__} {ident} doesn't exist")
                return Err(f"{self.model.__name__} {ident} doesn't exist")
            return Ok(instance)
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def update(self, ident: int, **kwargs) -> Result[M, str]:
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

    def parse_to_order_by_field(self, order_by: str):
        """解析得到排序字段"""
        is_desc = False
        # 默认是正序（小到大），前缀 "-" 待办倒序（大到小）
        if order_by.startswith("-"):
            order_by = order_by[1:]
            is_desc = True
        if not hasattr(self.model, order_by):
            raise AttributeError(f"{order_by}({self.model.__name__}) doesn't exist")
        order_by_field = getattr(self.model, order_by)
        if is_desc:
            order_by_field = desc(order_by_field)
        # logger.debug("order_by: {}, order_by_field: {}", order_by, order_by_field)
        return order_by_field

    async def list_all(self, order_by: str = "id", extra_stmt=None, **kwargs) -> Result[Sequence[M], str]:
        """列出所有记录（无排序、无过滤、无任何特殊情况）"""
        # todo: 参考 django 的 name__contains 去扩展 kwargs
        try:
            order_by_field = self.parse_to_order_by_field(order_by)
            stmt = select(self.model).order_by(order_by_field)
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
    # todo: 亟待优化，但是有个好处，数据都是从这里流出去的，好定位！
    model = Note

    def __init__(self) -> None:
        super().__init__()

    async def build_filter_statement(self,
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

        # [note] 对于 `Dict | None` 这种类型的变量，判断应该用 not XXX 而不是 is None
        logger.debug("search_filter: {}", search_filter)
        search_filter = search_filter or {}
        search_content = search_filter.get("search_content", None)
        has_attachment = search_filter.get("has_attachment", None)
        tag_select = search_filter.get("tag_select", "(null)")
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

        # 自定义格式 - 标题标签筛选
        if tag_select != "(null)":
            stmt = stmt.filter(Note.title.contains(f"【{tag_select}】"))

        order_by_field = self.parse_to_order_by_field(order_by)

        stmt = stmt.order_by(order_by_field)

        if page is None:
            return stmt

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        """结合 offset 实现分页

        # 跳过前 20 条，取 10 条（第 3 页，每页 10 条）
        users = session.query(User).offset(20).limit(10).all()

        """

        return stmt

    async def execute(self, stmt, note_type: str | None = None):
        # fixme: 这个方法不对，因为总是需要考虑调用点是否正确！
        try:
            # 我担心 stmt 无法 .where
            if note_type is None:
                note_type = NoteTypeMaskedEnum.DEFAULT
            new_stmt = stmt.where(Note.note_type == note_type)
            # logger.debug("new_stmt: {}", new_stmt)
            result = await self.db.execute(new_stmt)
        except Exception as e:
            logger.error(e)
            result = await self.db.execute(stmt)
        return result

    NotePreview = namedtuple("NotePreview", ["id", "title", "content"])

    async def get_no_content_notes(self, note_type: str | None = None) -> List[NotePreview]:
        stmt = select(Note.id, Note.title, Note.content)
        if note_type:
            stmt = stmt.where(Note.note_type == note_type)
        result = await self.db.execute(stmt)
        rows = result.mappings().all()
        note_previews = [self.__class__.NotePreview(**row) for row in rows]
        return note_previews

    async def incr_visit(self, node_id: int) -> int:
        """增加访问次数"""
        # 数据库层面计算：visit = visit + 1
        # 增加访问次数我不想 updated_at 修改，故更新时再改回去
        stmt = (
            update(Note)
            .where(Note.id == node_id)
            .values(visit=Note.visit + 1, updated_at=Note.updated_at)
            .returning(Note.visit)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one()

    async def get_visit(self, node_id: int) -> int:
        stmt = select(Note.visit).where(Note.id == node_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_notes(
            self,
            *,
            page: Annotated[int | None, "页号，None 代表不分页"] = 1,
            search_filter: Dict | None = None,
            no_content: bool = False,
            to_paginate: bool = True
    ) -> Sequence[Note]:
        """在有过滤和分页的情况下获取 Note List"""
        # todo: 该方法亟待优化（很尴尬，虽然 web 和业务强相关，但是只要是代码，又怎么不需要理解和阅读，又怎么不是业务强相关呢）
        logger.debug("[get_notes] start")
        if not to_paginate:
            page = None
        stmt = await self.build_filter_statement(page=page, search_filter=search_filter)
        note_type = None if not search_filter else search_filter.get("note_type", None)
        result = await self.execute(stmt, note_type=note_type)
        return result.scalars().all()

    async def get_titles(self) -> List[str]:
        try:
            result = await self.db.execute(select(Note.title))
            return result.scalars().all()  # noqa: Note.title 限定，返回值就是 List[str]
        except Exception as e:
            logger.error(e)
            raise e

    async def get_note_with_attachments(self, ident: int, selectinload_enable: bool = True) -> Result[Note, str]:
        """获得有附件的 Note"""
        logger.debug("[get_note_with_attachments] start")
        try:
            stmt = select(Note).where(Note.id == ident)
            if selectinload_enable:
                stmt = stmt.options(selectinload(Note.attachments))
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
        logger.debug("[count_note] start")
        try:
            stmt = await self.build_filter_statement(page=None,
                                                     search_filter=search_filter,
                                                     select_field=func.count(Note.id))
            note_type = None if not search_filter else search_filter.get("note_type", None)
            result = await self.execute(stmt, note_type=note_type)
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
            return Ok(result.rowcount)  # noqa
        except Exception as e:
            logger.error(e)
            return Err(str(e))

    async def count_attachment(self, note_id: int) -> Result[int, str]:
        try:
            # id 是主键列，通常作为计数的列。因为主键不允许为 NULL，所以 COUNT(User.id) 等同于 COUNT(*)。
            # [note][2025-11-23] 给 note_id 添加索引后，速度直线上升。数据库某表存储二进制数据影响巨大！被 "sqlite 对标文件系统" 这句话坑了。
            #                    参考资料推荐：
            #                    1. https://www.qianwen.com/share?shareId=6188c8db-6343-43e9-85a9-d075463a9d78
            #                    2. https://www.qianwen.com/share?shareId=01fe2004-b2d6-40a4-8185-64ba9ad9e85b
            #                    3. https://www.qianwen.com/share?shareId=bb0123ff-a83a-4e24-a61a-085950be4936
            #                    4. https://www.qianwen.com/share?shareId=87df7634-0982-493c-99d6-ede0f52f802d
            #                    5. https://www.qianwen.com/share?shareId=efcdfecd-ba4f-4854-8bef-fb4e74babc2d
            #                    但是说实在的，还是不是太理解 sqlite 的对标文件系统，如果单纯配置文件，json 足以。
            #                    实际上 sqlite 还是应该视为小型嵌入式数据库吧？
            #                    再次 emo，人力是有限的，搞研究才是正道，搞业务对我而言，有点死路一条的感觉...
            stmt = select(func.count(Attachment.id)).filter(Attachment.note_id == note_id)
            result = await self.db.execute(stmt)
            count = result.scalar()  # 使用 .scalar() 获取单个计数值
            # logger.debug("[count_attachment] count: {}", count) # [2025-11-19] 循环过多，删除
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

    shared_cache = dict()  # service 委托层的好处，减少了数据库访问的次数（写入没有处理，似乎也没什么处理的必要）

    # todo: 内存缓存可参考的三方库：https://lxblog.com/qianwen/share?shareId=02502627-7e8f-4724-a995-206c43310eaa
    # todo: 嵌入式 memcached

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

    async def _handle_get_value(self, key: str, returned_value: Any):
        """处理 get_value 的返回值，让对应 key 的 value 在对应的 Enum 中"""

    async def get_value(self, key: str) -> Any | None:
        """唯一 read 入口函数"""
        if key not in UserConfigService.shared_cache:
            config = await self._get_user_config()
            value = config.profile.get(key)
            logger.debug("[get_value] config.profile[{}]: {}", key, value)
            UserConfigService.shared_cache[key] = value
        return UserConfigService.shared_cache[key]

    def _clear_cache(self, key: str):
        """使用 python 类属性 dict 实现一个简单的缓存（主要不要用 self 调用，要用 cls，否则会实例化）"""
        if UserConfigService.shared_cache.get(key) is not None:
            logger.debug("[_clear_cache] del self.shared_cache[{}]", key)
            del UserConfigService.shared_cache[key]

    async def set_value(self, key: str, value):
        """唯一 update 入口函数"""
        if await self.get_value(key) == value:
            logger.debug("[set_value] key={}, the value hasn't changed.)", key)
            return
        self._clear_cache(key)
        config = await self._get_user_config()
        config.profile[key] = value
        logger.debug("[set_value] config.profile[{}]: {}", key, value)
        # 显式标记 profile 字段已修改
        flag_modified(config, "profile")
        # SQLAlchemy 检测到变更，自动替换为 UPDATE 语句
        await self.db.commit()

    async def get_page_size(self):
        page_size = await self.get_value("page_size")
        if page_size is None:
            raise Exception(f"UserConfigService.init_user_config() failed, page_size is None")
        return page_size


class TagService(Service[Tag]):
    model = Tag

    async def get_tags(self, order_by: str = "id") -> List[str]:
        try:
            stmt = select(Tag.name)
            if order_by:
                stmt = stmt.order_by(self.parse_to_order_by_field(order_by))
            result = await self.db.execute(stmt)
            tags = result.scalars().all()
            return tags  # noqa: select 限定了字段，返回值就是 List[str]
        except Exception as e:
            logger.error(e)
            raise e

    async def delete_all(self):
        stmt = delete(Tag)
        result = await self.db.execute(stmt)
        deleted_count = result.rowcount  # noqa: Unresolved attribute reference 'rowcount' for class 'Result'
        logger.debug("Deleted {} rows.", deleted_count)
        await self.db.commit()

    async def create_tag_if_not_exists(self, name: str) -> bool:
        try:
            tag = Tag(name=name)
            self.db.add(tag)
            await self.db.commit()
            return True
        except IntegrityError:
            # 此时说明 name 已存在，回滚
            await self.db.rollback()
            return False
        except Exception as e:
            logger.debug("type: {}", type(e))
            logger.error(e)
            raise e
