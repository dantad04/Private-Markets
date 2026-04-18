from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


CANONICAL_ASSET_CLASS_SEED = [
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
    {"code": "multi_asset_other", "label": "Multi-Asset / Other", "parent_code": None, "description": "Residual bucket for ambiguous section totals or uncategorised rows."},
]


class Base(DeclarativeBase):
    pass


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    apra_regulated_flag: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    source_system_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    source_files: Mapped[list["SourceFile"]] = relationship(back_populates="fund")
    investment_options: Mapped[list["InvestmentOption"]] = relationship(back_populates="fund")


class ReportingPeriod(Base):
    __tablename__ = "reporting_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_end_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    disclosure_due_date: Mapped[date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(32), unique=True)
    source_cycle: Mapped[str] = mapped_column(String(32), default="semi_annual", server_default="semi_annual")


class InvestmentOption(Base):
    __tablename__ = "investment_options"
    __table_args__ = (
        UniqueConstraint("fund_id", "source_option_code", name="uq_investment_options_fund_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    source_option_code: Mapped[str] = mapped_column(String(255))
    source_option_name: Mapped[str] = mapped_column(String(255))
    canonical_option_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lineage_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active_from_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    active_to_period: Mapped[date | None] = mapped_column(Date, nullable=True)

    fund: Mapped[Fund] = relationship(back_populates="investment_options")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    investment_option_id: Mapped[int | None] = mapped_column(ForeignKey("investment_options.id"), nullable=True, index=True)
    adapter_key: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    reporting_period_id: Mapped[int | None] = mapped_column(ForeignKey("reporting_periods.id"), nullable=True, index=True)
    schema_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingest_status: Mapped[str] = mapped_column(String(32), default="registered", server_default="registered")
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    supersedes_source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_files.id"), nullable=True)
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersession_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoding_replacement_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    fund: Mapped[Fund] = relationship(back_populates="source_files")


class CanonicalAssetClass(Base):
    __tablename__ = "canonical_asset_classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    parent_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("source_file_id", "source_row_hash", name="uq_holdings_source_file_row_hash"),
        Index("ix_holdings_entity_reporting_period", "entity_id", "reporting_period_id"),
        Index("ix_holdings_source_fund_option_period", "source_fund_id", "source_option_id", "reporting_period_id"),
        Index("ix_holdings_manager_reporting_period", "manager_entity_id", "reporting_period_id"),
        Index("ix_holdings_asset_class_reporting_period", "canonical_asset_class_id", "reporting_period_id"),
        Index("ix_holdings_security_identifier", "security_identifier_type", "security_identifier_value"),
        Index(
            "ix_holdings_reporting_period_disclosure_nonaggregate",
            "reporting_period_id",
            "disclosure_completeness",
            sqlite_where=text("is_aggregate = 0"),
            postgresql_where=text("is_aggregate = false"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), index=True)
    source_fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    source_option_id: Mapped[int] = mapped_column(ForeignKey("investment_options.id"), index=True)
    reporting_period_id: Mapped[int] = mapped_column(ForeignKey("reporting_periods.id"), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_aud: Mapped[Decimal | None] = mapped_column(Numeric(24, 9), nullable=True)
    ownership_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)
    units: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    is_aggregate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    disclosure_completeness: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_asset_class_id: Mapped[int] = mapped_column(ForeignKey("canonical_asset_classes.id"), index=True)
    source_asset_class_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    source_subclass_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo_lat: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    geo_lng: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    security_identifier_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    security_identifier_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value_band_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    manager_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issuer_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parse_warning_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_attached_from_row_numbers: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

