import functools
from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, JsonConfigSettingsSource, SettingsConfigDict


PAGE_SIZE = 6


# [note] [pydantic-settings 如何使用](https://lxblog.com/qianwen/share?shareId=ec78187b-f927-4c5e-9296-7cae4b461a6d)

# region - template

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
        # 优先级：初始化参数 > 环境变量 > .env > JSON 文件 > 默认值（相关配置文件）
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls, json_file=Path("settings.json"), json_file_encoding="utf-8"),
            file_secret_settings,
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    save_note_cooldown: int
    attachment_upload_text: str # [note] python 可以这样使用 format："{0}".format(0)
    intruction_content: str


@functools.lru_cache()
def get_dynamic_settings():
    """惰性加载

    但是这将导致无法保证启动阶段就检查到报错，不太好吧？
    比如 save_note_cooldown 不设置默认值，然后相关配置文件也没有这个字段...

    """
    return DynamicSettings() # noqa: Parameter 'save_note_cooldown' unfilled


dynamic_settings = get_dynamic_settings()

# endregion