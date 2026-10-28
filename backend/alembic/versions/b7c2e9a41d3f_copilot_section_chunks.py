"""copilot: section-aware chunk metadata and a separate passage vector table

Revision ID: b7c2e9a41d3f
Revises: e1d14600b48e
Create Date: 2026-10-28 16:00:00.000000

Document chunk vectors move out of embedding_records into document_chunk_embeddings. The old rows
(entity_type 'document_chunk') are derived data that nothing reads any more, so they are deleted;
POST /api/v1/ai/reindex rebuilds passage vectors in the new table. No ANN index is created on the new
table: pgvector applies WHERE filters after an approximate index scan, which can silently return fewer
than k rows, and a corpus of a few hundred chunks is cheap to scan exactly.
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy.vector  # noqa: F401
import sqlalchemy as sa

revision: str = 'b7c2e9a41d3f'
down_revision: Union[str, None] = 'e1d14600b48e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('document_number', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('document_type', sa.String(length=64), nullable=True))
    op.add_column('document_chunks', sa.Column('section_number', sa.String(length=32), nullable=True))
    op.add_column('document_chunks', sa.Column('section_heading', sa.String(length=255), nullable=True))
    op.add_column('document_chunks', sa.Column('section_path', sa.Text(), nullable=True))
    op.add_column('document_chunks', sa.Column('window', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('chat_messages', sa.Column('answer_mode', sa.String(length=16), nullable=True))
    op.add_column('chat_messages', sa.Column('abstention_reason', sa.Text(), nullable=True))
    op.create_table(
        'document_chunk_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('chunk_id', sa.UUID(), nullable=False),
        sa.Column('model_name', sa.String(length=120), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chunk_id', 'model_name', name='uq_chunk_embedding_model'),
    )
    op.create_index(op.f('ix_document_chunk_embeddings_chunk_id'), 'document_chunk_embeddings', ['chunk_id'], unique=False)
    op.execute("DELETE FROM embedding_records WHERE entity_type = 'document_chunk'")


def downgrade() -> None:
    # The deleted embedding_records rows are not restored; re-index after downgrading.
    op.drop_index(op.f('ix_document_chunk_embeddings_chunk_id'), table_name='document_chunk_embeddings')
    op.drop_table('document_chunk_embeddings')
    op.drop_column('chat_messages', 'abstention_reason')
    op.drop_column('chat_messages', 'answer_mode')
    op.drop_column('document_chunks', 'window')
    op.drop_column('document_chunks', 'section_path')
    op.drop_column('document_chunks', 'section_heading')
    op.drop_column('document_chunks', 'section_number')
    op.drop_column('documents', 'document_type')
    op.drop_column('documents', 'document_number')
