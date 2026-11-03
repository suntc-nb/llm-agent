"""add cascade delete to chat_messages fk

Revision ID: 423d9f1d6dfd
Revises: dfb7606ad607
Create Date: 2026-10-30 11:17:50.586792

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '423d9f1d6dfd'
down_revision: str | Sequence[str] | None = 'dfb7606ad607'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = 'fk_chat_messages_session_id'


def upgrade() -> None:
    """为 chat_messages.session_id 外键加上 ON DELETE CASCADE。

    删除会话时由数据库自动清理其消息，避免外键约束失败。
    SQLite 不支持 ALTER TABLE 修改外键，batch 模式会重建表并保留数据。
    """
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_='foreignkey')
        batch_op.create_foreign_key(
            _FK_NAME,
            'chat_sessions',
            ['session_id'],
            ['session_id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    """移除 ON DELETE CASCADE，恢复为默认的 NO ACTION。"""
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_='foreignkey')
        batch_op.create_foreign_key(
            _FK_NAME,
            'chat_sessions',
            ['session_id'],
            ['session_id'],
        )
