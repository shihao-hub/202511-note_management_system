"""v1.1.2

Revision ID: 096e13d313fd
Revises: c4109a77a0ca
Create Date: 2025-11-16 13:19:48.550600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utc

# revision identifiers, used by Alembic.
revision: str = '096e13d313fd'
down_revision: Union[str, Sequence[str], None] = 'c4109a77a0ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 新增 UserConfig 表
    op.create_table('user_config',
    sa.Column('profile', sa.JSON(), nullable=True, comment='动态字段，缓解关系型数据库的弊端'),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_config_id'), 'user_config', ['id'], unique=False)

    # 新增 Note note_type 字段
    op.add_column('note', sa.Column('note_type', sa.Text(), server_default='default', nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # v1.1.1 -> v1.1.2 没有降级操作，因为 v1.1.1 之前没有使用 alembic 进行 sql 版本管理
    pass
