"""SQLAlchemy 2.0 models. The Alembic migration under migrations/ is the DDL;
`tests/test_db.py` checks the two never drift apart."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Money is exact in the store (cents are cents); the repository hands it to
# the normalizer as float, the way the files do.
Money = Numeric(10, 2)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: ARRAY(String)}


class Receipt(Base):
    """One paper receipt: the header of a truth file. No product ids here, ever."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_image: Mapped[str] = mapped_column(String, unique=True)
    transcribed_by: Mapped[str] = mapped_column(String)  # hand | llm-verified | llm
    store: Mapped[str | None] = mapped_column(String)
    store_location: Mapped[str | None] = mapped_column(String)
    date: Mapped[date | None] = mapped_column(Date)
    time: Mapped[str | None] = mapped_column(String(8))  # as printed, "11:49"
    currency: Mapped[str | None] = mapped_column(String(3))
    printed_total: Mapped[Decimal | None] = mapped_column(Money)
    printed_savings: Mapped[Decimal | None] = mapped_column(Money)
    tax_buckets: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    lines: Mapped[list[ReceiptLine]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan",
        order_by="ReceiptLine.position")


class ReceiptLine(Base):
    """One printed line, exactly as the truth schema holds it."""

    __tablename__ = "receipt_lines"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)  # 0-based, as line_resolutions counts
    type: Mapped[str] = mapped_column(String)  # product | deposit | deposit_return
    raw_name: Mapped[str] = mapped_column(String)
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_gross: Mapped[Decimal | None] = mapped_column(Money)
    gross: Mapped[Decimal | None] = mapped_column(Money)
    discount: Mapped[Decimal | None] = mapped_column(Money)
    net: Mapped[Decimal] = mapped_column(Money)
    tax_class: Mapped[str | None] = mapped_column(String(4))  # as printed: A, 1, 2, ...
    sold_by_weight: Mapped[bool | None] = mapped_column(Boolean)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    unit_price_basis: Mapped[str | None] = mapped_column(String)  # kg, piece, ...

    receipt: Mapped[Receipt] = relationship(back_populates="lines")


class Product(Base):
    """What a product is. `id` is the public `p-0001`; it never changes."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    brand: Mapped[str | None] = mapped_column(String)
    product_line: Mapped[str | None] = mapped_column(String)
    variant: Mapped[str | None] = mapped_column(String)
    size: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    category: Mapped[str | None] = mapped_column(String)
    is_organic: Mapped[bool | None] = mapped_column(Boolean)
    is_own_brand: Mapped[bool | None] = mapped_column(Boolean)
    eans: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    open_questions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list,
                                                      server_default="{}")
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Filled by `grocery-app enrich` from Open Food Facts; `extra` is an older
    # free-form note on a few products, kept whole rather than dropped.
    nutrition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enrichment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Resolution(Base):
    """What receipt text means at one store: a product, a family, or nothing.

    Exactly one of these holds per row: `product_id` set (exact),
    `product_ids` non-empty (a family the till cannot tell apart), or both
    empty with `line_type` != product (a deposit line, known not to be a product).
    """

    __tablename__ = "resolutions"
    __table_args__ = (UniqueConstraint("store", "raw_name", "line_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str] = mapped_column(String)
    raw_name: Mapped[str] = mapped_column(String)
    line_type: Mapped[str] = mapped_column(String)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    product_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list,
                                                   server_default="{}")
    status: Mapped[str | None] = mapped_column(String)  # e.g. ambiguous_on_receipt
    confirmed_by: Mapped[str | None] = mapped_column(String)
    confirmed_at: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String)


class StoreListing(Base):
    """What one store sells a product as, with the shelf prices seen there."""

    __tablename__ = "store_listings"
    __table_args__ = (UniqueConstraint("store", "article_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str] = mapped_column(String)
    article_number: Mapped[str] = mapped_column(String)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    url: Mapped[str | None] = mapped_column(String)
    prices: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list,
                                                         server_default="[]")


class LineResolution(Base):
    """The shopper's own answer for one line the receipt could not pin down."""

    __tablename__ = "line_resolutions"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    raw_name: Mapped[str] = mapped_column(String)  # guards against a re-transcribed line
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    confirmed_by: Mapped[str | None] = mapped_column(String)
    confirmed_at: Mapped[date | None] = mapped_column(Date)
    basis: Mapped[str | None] = mapped_column(String)  # memory, photo, ...
