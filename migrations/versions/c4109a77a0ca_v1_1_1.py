"""v1.1.1

Revision ID: c4109a77a0ca
Revises: 
Create Date: 2025-11-16 13:03:15.301542

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlalchemy_utc
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision: str = 'c4109a77a0ca'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def table_exists(table_name, schema=None):
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names(schema=schema)
    return table_name in tables

def upgrade() -> None:
    """Upgrade schema."""
    # v1.1.1 及其之前，未使用 alembic 进行 sql 管理，而是使用 create_all()...
    # 现在需要进行特殊兼容，对于已存在的数据库文件，我需要判断表是否存在，再进行迁移操作
    if not table_exists('note'):
        op.create_table('note',
                        sa.Column('title', sa.String(length=200), nullable=False),
                        sa.Column('content', sa.Text(), nullable=False),
                        sa.Column('id', sa.Integer(), nullable=False),
                        sa.Column('created_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
                        sa.Column('updated_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
                        sa.PrimaryKeyConstraint('id')
                        )
        op.create_index(op.f('ix_note_id'), 'note', ['id'], unique=False)

    if not table_exists('attachment'):
        op.create_table('attachment',
                        sa.Column('filename', sa.String(length=255), nullable=False, comment='原始文件名'),
                        sa.Column('content', sa.BLOB(), nullable=False, comment='文件二进制内容'),
                        sa.Column('mimetype', sa.String(length=100), nullable=False,
                                  comment='MIME类型（如 application/pdf）'),
                        sa.Column('size', sa.Integer(), nullable=False, comment='文件大小，单位字节'),
                        sa.Column('note_id', sa.Integer(), nullable=True, comment='特别使用，允许为空'),
                        sa.Column('temporary_uuid', sa.String(length=64), nullable=True,
                                  comment='临时使用的标识，能模拟临时表效果的字段，也允许为空'),
                        sa.Column('id', sa.Integer(), nullable=False),
                        sa.Column('created_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
                        sa.Column('updated_at', sqlalchemy_utc.sqltypes.UtcDateTime(timezone=True), nullable=False),
                        sa.ForeignKeyConstraint(['note_id'], ['note.id'], ),
                        sa.PrimaryKeyConstraint('id')
                        )
        op.create_index(op.f('ix_attachment_id'), 'attachment', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # v1.1.1 及其之前，未使用 alembic 进行 sql 管理，而是使用 create_all()...
    pass
