"""rename users creat_at to created_at

Revision ID: 1a97ea980055
Revises: abfc71089501
Create Date: 2026-10-14 11:36:43.356890

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1a97ea980055'
down_revision: str | Sequence[str] | None = 'abfc71089501'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """修正列名拼写：creat_at -> created_at，与 ORM 模型保持一致。"""
    # SQLite 3.25+ 支持 ALTER TABLE ... RENAME COLUMN，且此处为原地重命名，
    # 不会丢失已有数据，无需 batch_alter_table。
    op.alter_column('users', 'creat_at', new_column_name='created_at')


def downgrade() -> None:
    """回滚列名：created_at -> creat_at。"""
    op.alter_column('users', 'created_at', new_column_name='creat_at')
