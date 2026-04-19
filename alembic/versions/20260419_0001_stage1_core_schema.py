"""stage1 core schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260419_0001"
down_revision = None
branch_labels = None
depends_on = None


canonical_asset_classes = sa.table(
    "canonical_asset_classes",
    sa.column("code", sa.String(length=64)),
    sa.column("label", sa.String(length=128)),
    sa.column("parent_code", sa.String(length=64)),
    sa.column("description", sa.Text()),
)


def _dialect_name() -> str:
    bind = op.get_bind()
    return "" if bind is None else bind.dialect.name


def upgrade() -> None:
    op.create_table(
        "funds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("apra_regulated_flag", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("source_system_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_funds_code", "funds", ["code"], unique=True)

    op.create_table(
        "reporting_periods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("disclosure_due_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("source_cycle", sa.String(length=32), server_default="semi_annual", nullable=False),
    )
    op.create_index("ix_reporting_periods_period_end_date", "reporting_periods", ["period_end_date"], unique=True)
    op.create_index("ix_reporting_periods_label", "reporting_periods", ["label"], unique=True)

    op.create_table(
        "investment_options",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=False),
        sa.Column("source_option_code", sa.String(length=255), nullable=False),
        sa.Column("source_option_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_option_name", sa.String(length=255), nullable=True),
        sa.Column("lineage_key", sa.String(length=128), nullable=True),
        sa.Column("active_from_period", sa.Date(), nullable=True),
        sa.Column("active_to_period", sa.Date(), nullable=True),
        sa.UniqueConstraint("fund_id", "source_option_code", name="uq_investment_options_fund_code"),
    )

    op.create_table(
        "source_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=False),
        sa.Column("investment_option_id", sa.Integer(), sa.ForeignKey("investment_options.id"), nullable=True),
        sa.Column("adapter_key", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("reporting_period_id", sa.Integer(), sa.ForeignKey("reporting_periods.id"), nullable=True),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("mapping_version_id", sa.String(length=64), nullable=True),
        sa.Column("ingest_status", sa.String(length=32), server_default="registered", nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("version_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("supersedes_source_file_id", sa.Integer(), sa.ForeignKey("source_files.id"), nullable=True),
        sa.Column("is_current_version", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersession_reason", sa.Text(), nullable=True),
        sa.Column("terms_snapshot_url", sa.Text(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encoding_replacement_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_source_files_fund_id", "source_files", ["fund_id"])
    op.create_index("ix_source_files_adapter_key", "source_files", ["adapter_key"])
    op.create_index("ix_source_files_checksum", "source_files", ["checksum"])
    op.create_index("ix_source_files_reporting_period_id", "source_files", ["reporting_period_id"])
    op.create_index("ix_source_files_investment_option_id", "source_files", ["investment_option_id"])
    op.create_index(
        "uq_source_files_active_slice",
        "source_files",
        ["fund_id", "investment_option_id", "reporting_period_id", "adapter_key"],
        unique=True,
        sqlite_where=sa.text(
            "is_current_version = 1 AND investment_option_id IS NOT NULL AND reporting_period_id IS NOT NULL"
        ),
        postgresql_where=sa.text(
            "is_current_version = true AND investment_option_id IS NOT NULL AND reporting_period_id IS NOT NULL"
        ),
    )

    op.create_table(
        "canonical_asset_classes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("parent_code", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_canonical_asset_classes_code", "canonical_asset_classes", ["code"], unique=True)
    op.bulk_insert(
        canonical_asset_classes,
        [
            {"code": "listed_equity", "label": "Listed Equity", "parent_code": None, "description": "Public listed equity holdings."},
            {"code": "unlisted_equity", "label": "Unlisted Equity", "parent_code": None, "description": "Private or unlisted equity holdings."},
            {"code": "listed_property", "label": "Listed Property", "parent_code": None, "description": "Listed real estate holdings."},
            {"code": "unlisted_property", "label": "Unlisted Property", "parent_code": None, "description": "Direct or private real estate holdings."},
            {"code": "listed_infrastructure", "label": "Listed Infrastructure", "parent_code": None, "description": "Listed infrastructure holdings."},
            {"code": "unlisted_infrastructure", "label": "Unlisted Infrastructure", "parent_code": None, "description": "Direct or private infrastructure holdings."},
            {"code": "fixed_income", "label": "Fixed Income", "parent_code": None, "description": "Debt and fixed income holdings."},
            {"code": "private_debt", "label": "Private Debt", "parent_code": "fixed_income", "description": "Private debt exposures when explicitly disclosed."},
            {"code": "cash", "label": "Cash", "parent_code": None, "description": "Cash and cash-equivalent holdings."},
            {"code": "derivatives", "label": "Derivatives", "parent_code": None, "description": "Reserved canonical class for future derivative holdings support."},
            {"code": "alternatives", "label": "Alternatives", "parent_code": None, "description": "Residual alternative asset classes."},
            {"code": "multi_asset_other", "label": "Multi-Asset / Other", "parent_code": None, "description": "Residual bucket for ambiguous section totals or uncategorised rows."}
        ],
    )

    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("source_fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=False),
        sa.Column("source_option_id", sa.Integer(), sa.ForeignKey("investment_options.id"), nullable=False),
        sa.Column("reporting_period_id", sa.Integer(), sa.ForeignKey("reporting_periods.id"), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=True),
        sa.Column("value_aud", sa.Numeric(24, 9), nullable=True),
        sa.Column("ownership_pct", sa.Numeric(18, 9), nullable=True),
        sa.Column("units", sa.Numeric(30, 12), nullable=True),
        sa.Column("is_aggregate", sa.Boolean(), nullable=False),
        sa.Column("disclosure_completeness", sa.String(length=32), nullable=False),
        sa.Column("canonical_asset_class_id", sa.Integer(), sa.ForeignKey("canonical_asset_classes.id"), nullable=False),
        sa.Column("source_asset_class_raw", sa.String(length=255), nullable=False),
        sa.Column("source_subclass_raw", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("geo_lat", sa.Numeric(12, 8), nullable=True),
        sa.Column("geo_lng", sa.Numeric(12, 8), nullable=True),
        sa.Column("security_identifier_value", sa.String(length=128), nullable=True),
        sa.Column("security_identifier_type", sa.String(length=32), nullable=True),
        sa.Column("value_band_raw", sa.String(length=128), nullable=True),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("manager_entity_id", sa.Integer(), nullable=True),
        sa.Column("issuer_entity_id", sa.Integer(), nullable=True),
        sa.Column("currency_raw", sa.String(length=32), nullable=True),
        sa.Column("classification_raw", sa.String(length=128), nullable=True),
        sa.Column("location_raw", sa.String(length=255), nullable=True),
        sa.Column("parse_warning_flags", sa.JSON(), nullable=False),
        sa.Column("metadata_attached_from_row_numbers", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source_file_id", "source_row_hash", name="uq_holdings_source_file_row_hash"),
    )
    op.create_index("ix_holdings_source_file_id", "holdings", ["source_file_id"])
    op.create_index("ix_holdings_source_fund_id", "holdings", ["source_fund_id"])
    op.create_index("ix_holdings_source_option_id", "holdings", ["source_option_id"])
    op.create_index("ix_holdings_reporting_period_id", "holdings", ["reporting_period_id"])
    op.create_index("ix_holdings_entity_reporting_period", "holdings", ["entity_id", "reporting_period_id"])
    op.create_index(
        "ix_holdings_source_fund_option_period",
        "holdings",
        ["source_fund_id", "source_option_id", "reporting_period_id"],
    )
    op.create_index("ix_holdings_manager_reporting_period", "holdings", ["manager_entity_id", "reporting_period_id"])
    op.create_index(
        "ix_holdings_asset_class_reporting_period",
        "holdings",
        ["canonical_asset_class_id", "reporting_period_id"],
    )
    op.create_index(
        "ix_holdings_security_identifier",
        "holdings",
        ["security_identifier_type", "security_identifier_value"],
    )
    op.create_index(
        "ix_holdings_reporting_period_disclosure_nonaggregate",
        "holdings",
        ["reporting_period_id", "disclosure_completeness"],
    )

    if _dialect_name() == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            """
            CREATE INDEX ix_holdings_raw_name_trgm
            ON holdings
            USING gin (lower(coalesce(raw_name, '')) gin_trgm_ops)
            """
        )
        op.execute(
            """
            CREATE INDEX ix_holdings_address_trgm
            ON holdings
            USING gin (lower(coalesce(address, '')) gin_trgm_ops)
            """
        )


def downgrade() -> None:
    if _dialect_name() == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_holdings_address_trgm")
        op.execute("DROP INDEX IF EXISTS ix_holdings_raw_name_trgm")
    op.drop_index("ix_holdings_reporting_period_disclosure_nonaggregate", table_name="holdings")
    op.drop_index("ix_holdings_security_identifier", table_name="holdings")
    op.drop_index("ix_holdings_asset_class_reporting_period", table_name="holdings")
    op.drop_index("ix_holdings_manager_reporting_period", table_name="holdings")
    op.drop_index("ix_holdings_source_fund_option_period", table_name="holdings")
    op.drop_index("ix_holdings_entity_reporting_period", table_name="holdings")
    op.drop_index("ix_holdings_reporting_period_id", table_name="holdings")
    op.drop_index("ix_holdings_source_option_id", table_name="holdings")
    op.drop_index("ix_holdings_source_fund_id", table_name="holdings")
    op.drop_index("ix_holdings_source_file_id", table_name="holdings")
    op.drop_table("holdings")
    op.drop_index("ix_canonical_asset_classes_code", table_name="canonical_asset_classes")
    op.drop_table("canonical_asset_classes")
    op.drop_index("uq_source_files_active_slice", table_name="source_files")
    op.drop_index("ix_source_files_investment_option_id", table_name="source_files")
    op.drop_index("ix_source_files_reporting_period_id", table_name="source_files")
    op.drop_index("ix_source_files_checksum", table_name="source_files")
    op.drop_index("ix_source_files_adapter_key", table_name="source_files")
    op.drop_index("ix_source_files_fund_id", table_name="source_files")
    op.drop_table("source_files")
    op.drop_table("investment_options")
    op.drop_index("ix_reporting_periods_label", table_name="reporting_periods")
    op.drop_index("ix_reporting_periods_period_end_date", table_name="reporting_periods")
    op.drop_table("reporting_periods")
    op.drop_index("ix_funds_code", table_name="funds")
    op.drop_table("funds")
