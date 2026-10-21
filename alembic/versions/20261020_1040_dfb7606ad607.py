"""add chat messages table and foreign keys

Revision ID: dfb7606ad607
Revises: e1684463b6a2
Create Date: 2026-10-20 10:40:11.754550

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dfb7606ad607'
down_revision: str | Sequence[str] | None = 'e1684463b6a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['session_id'],
            ['chat_sessions.session_id'],
            name='fk_chat_messages_session_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_chat_messages_message_id'), 'chat_messages', ['message_id'], unique=True
    )
    op.create_index(
        op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False
    )

    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，batch 模式会自动重建表
    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_chat_sessions_user_id', 'users', ['user_id'], ['user_id'])

    # 修正历史漂移：user_name 在模型中声明为 unique，但首个迁移只建了普通索引
    op.drop_index(op.f('ix_users_user_name'), table_name='users')
    op.create_index(op.f('ix_users_user_name'), 'users', ['user_name'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_user_name'), table_name='users')
    op.create_index(op.f('ix_users_user_name'), 'users', ['user_name'], unique=False)

    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_chat_sessions_user_id', type_='foreignkey')

    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_message_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
