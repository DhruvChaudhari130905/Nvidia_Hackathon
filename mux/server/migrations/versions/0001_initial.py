"""initial: the 12 tables from architecture §5.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blobs",
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("hash"),
    )
    op.create_table(
        "github_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("link_access", sa.Text(), nullable=False),
        sa.Column("link_permission", sa.Text(), nullable=True),
        sa.Column("budget_tokens_cap", sa.BigInteger(), nullable=True),
        sa.Column("budget_runs_cap", sa.Integer(), nullable=True),
        sa.Column("head_checkpoint_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "budgets",
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("tokens_used", sa.BigInteger(), nullable=False),
        sa.Column("runs_used", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("room_id"),
    )
    op.create_table(
        "conflicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "events",
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("room_id", "seq"),
    )
    op.create_table(
        "manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manifests_room_id", "manifests", ["room_id"])
    op.create_table(
        "memberships",
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.Column("domain_role", sa.Text(), nullable=True),
        sa.CheckConstraint("permission in ('owner', 'editor', 'viewer')", name="ck_memberships_permission"),
        sa.CheckConstraint("domain_role in ('pm', 'design', 'eng')", name="ck_memberships_domain_role"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("room_id", "user_id"),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("default_option", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("start_seq", sa.BigInteger(), nullable=False),
        sa.Column("manifest_id", sa.Uuid(), nullable=False),
        sa.Column("sandbox_snapshot_uuid", sa.Text(), nullable=True),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["manifest_id"], ["manifests.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["checkpoints.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checkpoints_room_id", "checkpoints", ["room_id"])
    op.create_table(
        "votes",
        sa.Column("conflict_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("option", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["conflict_id"], ["conflicts.id"]),
        sa.PrimaryKeyConstraint("conflict_id", "user_id"),
    )
    op.create_table(
        "logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pins", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checkpoint_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("kind in ('task', 'day')", name="ck_logs_kind"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_logs_room_id", "logs", ["room_id"])
    op.create_foreign_key("fk_rooms_head_checkpoint_id", "rooms", "checkpoints", ["head_checkpoint_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_rooms_head_checkpoint_id", "rooms", type_="foreignkey")
    op.drop_index("ix_logs_room_id", table_name="logs")
    op.drop_table("logs")
    op.drop_table("votes")
    op.drop_index("ix_checkpoints_room_id", table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_table("questions")
    op.drop_table("memberships")
    op.drop_index("ix_manifests_room_id", table_name="manifests")
    op.drop_table("manifests")
    op.drop_table("events")
    op.drop_table("conflicts")
    op.drop_table("budgets")
    op.drop_table("rooms")
    op.drop_table("github_tokens")
    op.drop_table("blobs")
