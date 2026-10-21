"""${message}

Revision ID: ${up_revision}
<%
    # down_revision 为空时输出 "Revises:" 而非 "Revises: "，
    # 避免生成文件出现行尾空格（ruff W291）。
    _revises = down_revision
    if isinstance(_revises, (list, tuple)):
        _revises = ', '.join(str(_r) for _r in _revises)
%>Revises:${(' ' + _revises) if _revises else ''}
Create Date: ${create_date}

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
