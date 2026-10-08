"""candidates.visibility: новые умолчания приватности (E36-4, ADR-027).

Анкеты, у которых хранится нетронутый старый набор умолчаний, переводятся на новый: компании и
опыт видны, ФИО скрыто, ФСП и регион видны. Анкеты, где кандидат что-то менял, не трогаем.

Revision ID: b1_15
Revises: b2_12
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "b1_15"
down_revision = "b2_12"
branch_labels = None
depends_on = None

OLD_DEFAULT = {
    "companies": False,
    "education": False,
    "repos": False,
    "teams": True,
    "public_profile": False,
}
NEW_KEYS = {"full_name": False, "companies": True, "fsp": True, "region": True}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("select user_id, visibility from candidates")).fetchall()
    for user_id, vis in rows:
        if isinstance(vis, str):
            vis = json.loads(vis)
        if vis == OLD_DEFAULT:
            bind.execute(
                sa.text("update candidates set visibility = cast(:v as json) where user_id = :u"),
                {"v": json.dumps({**vis, **NEW_KEYS}), "u": user_id},
            )


def downgrade() -> None:
    """Данные не откатываем: лишние ключи видимости безвредны."""
