import os
import sys
import functools
from pathlib import Path
from typing import Type, Any, Tuple, Dict, List, Union

from lupa.lua51 import LuaRuntime, lua_type
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, JsonConfigSettingsSource, SettingsConfigDict
from pydantic import field_validator
from pydantic.fields import FieldInfo
from jinja2 import Environment, FileSystemLoader
from loguru import logger

# todo: 不要从 settings.py 读，从数据库读，或者说再新增一张表，用来管理配置文件（od python）
# PAGE_SIZE = 6

# 设置 jinja2 模板目录
ENV = Environment(loader=FileSystemLoader("./templates"))
VUE_COMPATIBLE_ENV = Environment(
    loader=FileSystemLoader("templates"),
    variable_start_string="[[",
    variable_end_string="]]"
)

# 判断是否被 pyinstaller 打包
IS_PACKED = "PACKED" in os.environ or getattr(sys, "frozen", False)


# region - template

# [note] [pydantic-settings 如何使用](https://lxblog.com/qianwen/share?shareId=ec78187b-f927-4c5e-9296-7cae4b461a6d)

class LuaConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: Type[BaseSettings], lua_file: Path, lua_file_encoding: str = "utf-8"):
        super().__init__(settings_cls)
        self.settings_cls = settings_cls
        self.lua_file = lua_file
        self.lua_file_encoding = lua_file_encoding

    def get_field_value(self, field: FieldInfo, field_name: str) -> Tuple[Any, str, bool]:
        config_dict = self._load_lua_config()
        if field_name in config_dict:
            return config_dict[field_name], field_name, True
        return None, field_name, False

    def _lua_table_to_python(self, lua, obj: Any) -> Union[Dict, List, Any]:
        """

        递归将 Lupa 的 LuaTable 转换为 Python 的 dict 或 list。
        - 如果 Lua 表是连续整数索引（1-based），视为 list。
        - 否则视为 dict。

        当前函数主要逻辑由 ai 生成

        """

        # 判断是否是 Lua 表：检查是否有 .items() 方法（这是 LuaTable 的特征）
        if hasattr(obj, 'items') and hasattr(obj, 'keys') and not isinstance(obj, (dict, list)):
            # 检查是否为数组式表（1,2,3,... 连续整数键）
            length = len(obj)
            if length > 0:
                # 尝试判断是否为纯数组：所有键为 1..length 的整数
                is_array = all(
                    isinstance(k, int) and 1 <= k <= length
                    for k in obj.keys()
                )
                if is_array:
                    return [self._lua_table_to_python(lua, obj[i]) for i in range(1, length + 1)]
            return {k: self._lua_table_to_python(lua, v) for k, v in obj.items()}

        # 其他类型（number, string, bool, None）直接返回
        return obj

    def _load_lua_config(self) -> Dict:
        lua = LuaRuntime()
        with open(self.lua_file, "r", encoding=self.lua_file_encoding) as f:
            lua_code = f.read()
        lua.execute(lua_code)
        config_table = lua.globals()["config"]
        return self._lua_table_to_python(lua, config_table)

    def __call__(self) -> Dict[str, Any]:
        return self._load_lua_config()


class DynamicSettings(BaseSettings):
    """动态配置即不需要修改代码的配置

    Details:
        1. settings_customise_sources 用于从 json 文件导入配置
        2. model_config 是 Pydantic v2 引入的新语法，用来替代 v1 中的 class Config:。
           - env_file: 指定 .env 文件路径
           - env_prefix: 环境变量前缀
           - case_sensitive: 是否区分大小写
           - extra: 如何处理未定义的字段
        3. 当前类定义的类属性会被自动填充到实例中
        4. 类字段如果未设置默认值，也无法从文件中导入，那么当前类初始化时，会直接报错
    """

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：初始化参数 > 环境变量 > .env > JSON/LUA 文件 > 默认值（相关配置文件）
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            LuaConfigSettingsSource(settings_cls, lua_file=Path("settings.lua"), lua_file_encoding="utf-8"),
            # JsonConfigSettingsSource(settings_cls, json_file=Path("settings.json"), json_file_encoding="utf-8"),
            file_secret_settings,
        )

    @field_validator("export_dir", mode="before")
    @classmethod
    def validate_export_dir(cls, value: str):
        log_enabled = False

        value = value.strip()

        # 1. 禁止显式包含 . 或 .. 作为路径组件（简单防御）
        parts = Path(value).parts
        if log_enabled:
            logger.debug("parts: {}", parts)
        if any(part in (".", "..") for part in parts):
            raise ValueError("路径中不能包含 '.' 或 '..'")

        # 2. 转为绝对路径并解析
        cwd = Path.cwd().resolve()
        resolved = (cwd / value).resolve()
        if log_enabled:
            logger.debug("resolved: {}", resolved)

        # 3. 确保最终路径在 cwd 内部（沙箱检查）
        try:
            resolved.relative_to(cwd)
        except ValueError as e:
            raise ValueError(f"路径必须位于当前工作目录下: {cwd}") from e

        return resolved

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    save_note_cooldown: int
    attachment_upload_text: str  # [note] python 可以这样使用 format："{0}".format(0)
    intruction_content: str
    title: str
    host: str
    version: str
    export_dir: Path
    prefix_import_values: List[str]


@functools.lru_cache()
def get_dynamic_settings():
    """惰性加载（真的有用吗）

    但是这将导致无法保证启动阶段就检查到报错，不太好吧？
    比如 save_note_cooldown 不设置默认值，然后相关配置文件也没有这个字段...

    """
    return DynamicSettings()  # noqa: Parameter 'save_note_cooldown' unfilled


dynamic_settings = get_dynamic_settings()  # 要不直接命名成 settings 吧，from settings import settings ...

# endregion
