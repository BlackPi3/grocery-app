"""SQLAlchemy 2.0 models. The Alembic migration under migrations/ is the DDL;
`tests/test_db.py` checks the two never drift apart."""

from __future__ import annotations

import uuid
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
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Money is exact in the store (cents are cents); the repository hands it to
# the normalizer as float, the way the files do.
Money = Numeric(10, 2)
# What a model call cost. Not Money: that is euros off a receipt, this is
# dollars off an invoice, and a single extraction costs fractions of a cent.
Cost = Numeric(10, 5)

# A job moves queued -> running -> done | failed, and never backwards except
# when a failed one is deliberately retried.
JOB_STATUSES = ("queued", "running", "done", "failed")


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: ARRAY(String)}


class Receipt(Base):
    """One paper receipt: the header of a truth file. No product ids here, ever."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_image: Mapped[str] = mapped_column(String, unique=True)
    # Set when the photo arrived over HTTP; null for the files transcribed on
    # the laptop. Not unique: two photos of one paper are a duplicate receipt
    # (`is_duplicate`), which is a judgement, not a constraint.
    image_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
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


class Correction(Base):
    """A machine's answer for a line that the shopper overruled.

    Kept so the rate of wrong automatic answers is always known
    (`catalog-growth.md`, decision 5): the matcher's mistakes and the produce
    vocabulary's are counted, not silently replaced. Written by the route that
    takes a shopper's answer, never edited after.
    """

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer)
    store: Mapped[str | None] = mapped_column(String)
    raw_name: Mapped[str] = mapped_column(String)
    machine_how: Mapped[str] = mapped_column(String)  # the line's `resolution` before
    machine_product_id: Mapped[str] = mapped_column(String)
    shopper_product_id: Mapped[str] = mapped_column(String)
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now())


class Job(Base):
    """One extraction: a photo that arrived over HTTP and what became of it.

    The phone holds `id` and polls it; everything else here is the record the
    queue cannot keep. A queue forgets an item once a worker takes it, so the
    row is written and committed *before* any work is scheduled, and it is the
    only place a job's existence, cost and failure are written down.

    The money fields are the `.meta.json` sidecar `grocery-app extract` writes
    beside a receipt, moved into a table: the same facts, the same names.

    `image_sha256` is indexed, not unique. It answers "have I already paid to
    read this photo?" before a model is called. A unique constraint would say
    something stronger and wrong, because re-extracting one photo under a new
    `prompt_version` is a thing this project does on purpose.
    """

    __tablename__ = "jobs"

    # A uuid, not a counter: this is the one id a client holds and quotes back,
    # and a guessable sequence over someone's receipts is not worth the bytes
    # it saves.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String, default="queued")  # JOB_STATUSES
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str | None] = mapped_column(String)
    # Kept if the receipt is deleted: what was spent was still spent.
    receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL"))

    model: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    request_id: Mapped[str | None] = mapped_column(String)  # to ask the provider about a call
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # tokens, as the API reports
    cost_usd: Mapped[Decimal | None] = mapped_column(Cost)
    error: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    receipt: Mapped[Receipt | None] = relationship()
