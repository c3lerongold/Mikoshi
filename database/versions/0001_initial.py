"""Initial Mikoshi schema.

Revision ID: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("users", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("email", sa.String(320), unique=True, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("personas", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("language", sa.String(12), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    # The remaining tables are maintained by SQLAlchemy metadata in backend/app/models.py.

def downgrade() -> None:
    op.drop_table("personas")
    op.drop_table("users")
