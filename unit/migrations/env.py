from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# region - template

from models import Base
target_metadata = Base.metadata
render_as_batch = config.get_main_option("sqlalchemy.url").startswith("sqlite")
"""
alembic revision --autogenerate -m "general" # "init"
alembic upgrade head # head 也可以是 revision id，参考 git
"""
# 1. --autogenerate 自动生成，需要自行调整，第一次生成后，数据库会自动创建 alembic_version 表，但是并不会填充内容
# 2. upgrade head 生效后，alembic_version 表会填充版本号
# 3. alembic 命令会根据当前数据库表结构和当前 models.py 对比，生成相应的语句
# 4. sqlite 似乎会记录执行过那些 DDL 语句，这将使得 alembic 也能知道
# 5. alembic 是通过分析你项目中的 迁移脚本文件来确定哪个是 head 的（根据 revision 和 down_revision 构建一个有向图），这将导致 versions 文件不能随便删，需要有联动地删
# 6. alembic 通过 alembic_version 表（如果存在）和 versions .py 文件构建有向图，找到已迁移和未迁移的文件
# 7. 不要删除任何已发布的迁移文件，永远不要
# 8.

# endregion

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            render_as_batch=render_as_batch
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
