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
    Float,
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


class User(Base):
    """Someone other than the owner who uses the app with their own receipts.

    The owner is the account behind the server's own password
    (`GROCERY_TOKEN`): no row, and everything with no user is theirs. A user
    has a password of their own, kept here only as its sha256, and sees only
    their own receipts. The catalog and the memory are shared, and a user's
    answers teach them with less weight than the owner's (`memory.learn`):
    Parham, 2026-10-11, "her answers should be accepted with a grain of salt".
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    # The Google account they sign in with, lowercased; none for a password
    # only. Invite-only (2026-10-12): an address nobody added gets no account.
    email: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class SignIn(Base):
    """One Google sign-in: the token the page keeps and sends as its password.

    Only the token's sha256 is kept, as with passwords. It ends at
    `expires_at`, when its user is removed (the row goes with them), and when
    the address it was made for is no longer theirs: a user's `email`
    changed, or the owner's `GROCERY_OWNER_EMAIL`. `user_id` empty: the owner.
    """

    __tablename__ = "sign_ins"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Receipt(Base):
    """One paper receipt: the header of a truth file. No product ids here, ever."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Whose receipt: a user's, or the owner's when empty (everything from before
    # accounts, and whatever the command line imports).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_image: Mapped[str] = mapped_column(String, unique=True)
    # Set when the photo arrived over HTTP; null for the files transcribed on
    # the laptop. Not unique: a second photo of one paper has other bytes, and
    # is caught by what it prints (`api.jobs.same_paper`), not by its hash.
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    # When its owner first opened it on the page; empty while it is new to
    # them (the "new" mark, 2026-10-13). Set by `PUT /v1/receipts/{id}/seen`.
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How often the server read this receipt's waiting lines again, and when
    # last (`api.matching.reread_waiting`).
    reread_tries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reread_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # Everything the pack says besides name, brand, category and size: a range
    # (`system`), a strength, a flavour. Any number, in the product's words.
    details: Mapped[list[str]] = mapped_column(ARRAY(String), default=list,
                                               server_default="{}")
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
    # A photo of the pack for spot checks (`grocery_app.pictures`), found by
    # the server, not part of what the product is: not exported.
    picture: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    picture_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The word the shops' offers are searched by (`offer_match.flyer_words`), kept
    # so it is asked once; not part of what the product is: not exported.
    offer_word: Mapped[str | None] = mapped_column(String)
    offer_word_by: Mapped[str | None] = mapped_column(String)  # the prompt's version
    # Where it is kept until opened (fridge, freezer, cupboard) and how many
    # days it keeps from the day bought (`grocery_app.storage`). A model's
    # answer, asked again if lost: not exported with the catalog.
    storage: Mapped[str | None] = mapped_column(String)
    keeps_days: Mapped[int | None] = mapped_column(Integer)
    storage_by: Mapped[str | None] = mapped_column(String)  # the prompt's version


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
    # None is an answer too: "none of these", the line stays not placed and
    # is not asked about again (Parham, 2026-10-12: a No on every card).
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    # The product a No on a spot check said the line was not.
    rejected: Mapped[str | None] = mapped_column(String)
    confirmed_by: Mapped[str | None] = mapped_column(String)
    confirmed_at: Mapped[date | None] = mapped_column(Date)
    basis: Mapped[str | None] = mapped_column(String)  # memory, photo, ...
    # What the shopper wrote, as written, when the answer was a description:
    # the product holds the app's reading of it, and a bad reading can be
    # traced back to the words (Parham, 2026-10-01).
    shopper_words: Mapped[str | None] = mapped_column(String)
    # The memory's row for this printed name as it was before this answer
    # taught it, so taking the answer back undoes that too: `{"held": null}`
    # when there was none. None for answers from before 2026-10-10.
    memory_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # A user's answer that contradicts what the owner told the memory: the
    # owner's product, kept so the owner can look. The answer holds for the
    # user's own line; the memory keeps the owner's (2026-10-11).
    disagrees_with: Mapped[str | None] = mapped_column(String)


class UncountedLine(Base):
    """A line the shopper left out of their numbers, with one tap: a wine
    bought for a friend, a mistake. No reason is asked (Parham, 2026-10-05).
    It stays on the receipt and in the prices; `raw_name` binds the mark to
    the line's text, as a line answer is bound."""

    __tablename__ = "uncounted_lines"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    raw_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class LineGuess(Base):
    """What the photo reading guessed a line is, before anything placed it.

    Shown while the lines are still being placed, and after that for a line
    nothing placed. Never read by the normalizer: a guess is not a product,
    and the history and the insights rest only on what was placed. Kept out
    of `receipt_lines` because those columns hold what the paper prints.
    """

    __tablename__ = "line_guesses"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)  # a categories.CATEGORIES key
    reading: Mapped[str | None] = mapped_column(String)  # model and prompt version


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
    shopper_product_id: Mapped[str | None] = mapped_column(String)  # None: "not that"
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now())


class Question(Base):
    """A line the matcher could not settle, waiting for the shopper.

    `proposal` is what the matcher saw and said (`matcher.propose`): the
    candidates to offer, its own pick and why. Kept whole, so asking costs no
    second model call and a later matcher can be compared with this one.
    `answered_at` is set when the shopper answers the line.
    """

    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    raw_name: Mapped[str] = mapped_column(String)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the shopper last skipped it: not an answer, the card goes last.
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Check(Base):
    """A spot check: a line the app placed on its own, put to the shopper.

    The app's mistakes that it does not know about are found only by asking
    about lines it thinks it got right. A couple per receipt (Parham,
    2026-09-30: two) are chosen at random from the lines the app placed
    itself, and `app_product_id` keeps what it said at the time. The answer
    is the shopper's ordinary line answer (`line_resolutions`), so the
    outcome is read from there, never stored twice: the same product is
    `right`, another one is `corrected` (and a `corrections` row).
    """

    __tablename__ = "checks"
    __table_args__ = (UniqueConstraint("receipt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    raw_name: Mapped[str] = mapped_column(String)
    app_product_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    # When the shopper last skipped it: not an answer, the card goes last.
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # Who sent the photo; the owner when empty. Its receipt is theirs.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    # The photo was of a receipt already in the history: `receipt_id` is that
    # receipt, and nothing new was stored (Parham, 2026-10-09).
    already_added: Mapped[bool] = mapped_column(Boolean, default=False,
                                                server_default="false")
    # The photo was not of a shop receipt: where the reader says it is from
    # (`extract.RECEIPT_FROM`, never "shop"), and nothing was stored.
    turned_away: Mapped[str | None] = mapped_column(String)
    # When the upload was handed to the developer to look at (`/v1/inbox`):
    # another person's upload, a PDF, a failure (2026-10-11).
    dev_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the sender shared it with the developer, to make the app better
    # (2026-10-15): another person's upload reaches the developer only then.
    # The owner's own uploads need no sharing. Empty again when taken back.
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    receipt: Mapped[Receipt | None] = relationship()


class ModelCall(Base):
    """One paid model call, and what it cost (`grocery_app.spend`).

    Written for every Gemini call, whatever made it, so what processing a
    receipt costs can be read back: its reading, and finding what its lines
    are, which should cost less as the catalog grows (Parham, 2026-10-11).
    `cost_usd` is the list price; the free monthly searches are not taken off.
    """

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                         index=True)
    purpose: Mapped[str] = mapped_column(String)  # spend.PURPOSES
    # The upload it served; none for a picture lookup or a command-line run.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    model: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)  # thinking included
    searches: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Cost)


class Offer(Base):
    """A shop's offer, as the offers source showed it near a postcode
    (`grocery_app.offers`). Public: the same for everyone, so it says nothing
    about who searched. Kept after it ends, to learn each chain's rhythm."""

    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("source", "source_id", "postcode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String)  # offers.SOURCE
    source_id: Mapped[str] = mapped_column(String)
    postcode: Mapped[str] = mapped_column(String(5), index=True)
    chain: Mapped[str] = mapped_column(String)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date, index=True)
    record: Mapped[dict[str, Any]] = mapped_column(JSONB)  # offers.read_offer
    # The search words that found it near this postcode: which products'
    # offers it may be (`offer_match`).
    words: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}")
    # The first look that found it: before `valid_from`, it says how far
    # ahead the chain publishes (`offers.rhythm`).
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OfferSearch(Base):
    """When a search word was last looked up near a postcode, so the server
    asks again only once a day (`api.offers`). Neither says who asked."""

    __tablename__ = "offer_searches"
    __table_args__ = (UniqueConstraint("postcode", "word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    postcode: Mapped[str] = mapped_column(String(5))
    word: Mapped[str] = mapped_column(String)
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer, default=0)


class OfferVerdict(Base):
    """What the judge said one offer is for one product (`offer_match.judge`):
    `same_product`, `same_kind` or `no`. About a product and a public offer,
    never a person: two people with the same regular share one verdict."""

    __tablename__ = "offer_verdicts"
    __table_args__ = (UniqueConstraint("product_id", "source", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    verdict: Mapped[str] = mapped_column(String)  # offer_match.VERDICTS
    judged_by: Mapped[str] = mapped_column(String)  # model and prompt version
    judged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())


class ListWord(Base):
    """The word a shopping list calls a flyer word's kind (`Romatomaten`:
    `Tomaten`), given once by a model (`offer_match.list_words`). Keyed by
    the flyer word as `products.offer_word` holds it; the same for everyone."""

    __tablename__ = "list_words"

    word: Mapped[str] = mapped_column(String, primary_key=True)
    list_word: Mapped[str] = mapped_column(String)
    given_by: Mapped[str] = mapped_column(String)  # the prompt's version
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                               server_default=func.now())


class ListEdit(Base):
    """One change a person made to their shopping list: a kind added or
    removed for now, a line crossed off, words typed or deleted
    (`shopping_list.with_edits`). Kept as it happened, never updated: the
    list is worked out from these and the receipts. Goes with their account."""

    __tablename__ = "list_edits"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Whose list: a user's, or the owner's when empty.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String)  # an item key, `eier`, or typed words
    edit: Mapped[str] = mapped_column(String)  # shopping_list.EDITS
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CountedKind(Base):
    """A kind close to groceries a person counts as well (`categories.CLOSE_KINDS`):
    one row per kind switched on, none when only groceries count. Goes with
    their account."""

    __tablename__ = "counted_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Whose choice: a user's, or the owner's when empty.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String)


class ShopPlace(Base):
    """Where a shop on people's receipts is, and when the supermarkets around
    it were last looked up (`grocery_app.nearby`). Keyed by the printed
    address (`nearby.place_key`), never by who shops there; forgotten once
    nobody's receipts name it any more."""

    __tablename__ = "shop_places"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    street: Mapped[str | None] = mapped_column(String)
    postcode: Mapped[str] = mapped_column(String(5))
    # None when the map knows no such place (asked again after a while).
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    located_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stores_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stores: Mapped[list[NearbyStore]] = relationship(
        back_populates="place", cascade="all, delete-orphan", passive_deletes=True)


class NearbyStore(Base):
    """A supermarket within `nearby.RADIUS_M` of a shop place, as the map
    lists it: public, the same for everyone."""

    __tablename__ = "nearby_stores"
    __table_args__ = (UniqueConstraint("place_id", "osm_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("shop_places.id", ondelete="CASCADE"),
                                          index=True)
    osm_id: Mapped[str] = mapped_column(String)  # `node/123`
    chain: Mapped[str | None] = mapped_column(String)  # the map's brand
    name: Mapped[str] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[int] = mapped_column(Integer)
    place: Mapped[ShopPlace] = relationship(back_populates="stores")
