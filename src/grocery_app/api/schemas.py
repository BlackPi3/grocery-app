"""Typed views of the pipeline's documents.

These models say what `purchases.json` (contract 2) and `insights.json`
(contract 1) contain, in a form the API can validate and document. They are
deliberately strict on the purchase record (`extra="forbid"`): a field the
normalizer adds without updating this file fails the pipeline test, which is
the point of having a contract.

The insights document is typed at the top level only. Its sections are still
moving (every insight carries its own coverage shape), and pinning them here
would make each change a two-file change for no reader's benefit yet. Type
them when the iOS client needs to bind to them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bumped to 3 and 2 on 2026-09-22, when `is_own_brand` became `is_budget_brand`
# and the insight section `own_brand` became `budget_brand`. Renaming a field is
# a shape change, and the shape is what the version is for.
#
# Purchases bumped again to 4 on 2026-09-23: `category` stopped being free text
# and became a key from the closed vocabulary, and `category_path` arrived
# beside it with the three labels a reader sees. Same field name, different
# language in it, which is exactly the change a consumer must be told about.
#
# Purchases bumped to 5 on 2026-09-30: `said_by` says who said what each line
# is, `you` or `app`, so a reader can tell a confirmed answer from a guess.
# And to 6 on 2026-10-01: `sold_as` says how the line was sold, loose or a
# pack of some size; the product stays one thing.
PURCHASES_CONTRACT_VERSION = 6
#
# Insights bumped to 3 on 2026-09-29: lines known not to be groceries (café,
# flowers, cards) left every insight, so `coverage.spend` means grocery spend,
# and `coverage.not_grocery` says what was left out.
#
# Insights bumped to 4 on 2026-10-01: price changes and the basket compare
# like with like (loose with loose, packs with packs), so an entry carries
# `sold_as` and the basket names product and form.
INSIGHTS_CONTRACT_VERSION = 4


class UnitPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float
    per: str = Field(description="The basis: 'kg', 'l', 'piece', ...")


class PackSize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int | None
    value: float | None
    unit: str | None


class SoldAs(BaseModel):
    """How a line was sold: loose (weighed at the till), or a pack of `size`."""

    model_config = ConfigDict(extra="forbid")

    form: Literal["loose", "pack"]
    size: PackSize | None


class Purchase(BaseModel):
    """One receipt line after normalization. Mirrors `normalizer.normalize_line`."""

    model_config = ConfigDict(extra="forbid")

    date: str | None
    store: str | None
    source_image: str | None
    type: Literal["product", "deposit", "deposit_return"]
    raw_name: str
    product_id: str | None
    resolved: bool
    resolution: Literal["exact", "user", "price", "family", "produce", "none"]
    said_by: Literal["you", "app"] | None = Field(
        description="Who said what this line is: the shopper (`you`) or a guess the shopper "
                    "can overrule (`app`); null when nothing places it")
    candidate_ids: list[str]
    qty: float
    gross: float | None
    discount: float
    net_paid: float
    tax_class: str | None = Field(description="As printed on the receipt, never interpreted")
    tax_rate: float | None
    unit_price: UnitPrice | None = None
    sold_as: SoldAs | None = None

    # Present only when the line resolved to a product or a family of products.
    product: str | None = None
    brand: str | None = None
    product_line: str | None = None
    variant: str | None = None
    # The vocabulary key (`reibekaese`), and the three labels it stands for
    # (`["Molkereiprodukte & Eier", "Käse", "Reibekäse"]`), coarsest first.
    category: str | None = None
    category_path: list[str] | None = None
    is_budget_brand: bool | None = None
    is_organic: bool | None = None


class PurchasesMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipts: int
    date_range: list[str]
    product_lines: int
    total_net_paid: float
    unresolved_items: list[str]
    ambiguous_items: list[str]


class PurchasesDocument(BaseModel):
    """`purchases.json`: the central contract of the project."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[PURCHASES_CONTRACT_VERSION]
    meta: PurchasesMeta
    purchases: list[Purchase]


class InsightsDocument(BaseModel):
    """`insights.json`, typed at the top level only (see module docstring)."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[INSIGHTS_CONTRACT_VERSION]
    as_of: str
    coverage: dict[str, Any]
    repurchase: list[dict[str, Any]]
    price_changes: list[dict[str, Any]]
    basket_index: dict[str, Any]
    budget_brand: dict[str, Any]
    cross_store: dict[str, Any]


class ReceiptLineView(Purchase):
    """A normalized line, with the position the correction routes address it by.

    `position` is not part of the purchases contract — it is how a client
    names one line of one receipt, and `normalize_receipt` emits exactly one
    record per printed line, in order, so the index is the position.
    """

    position: int


class ReceiptDocument(BaseModel):
    """One receipt: what the paper says, and what the normalizer makes of it."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: int
    receipt: dict[str, Any] = Field(
        description="The receipt in the truth schema, exactly as a truth file holds it")
    lines: list[ReceiptLineView]


class NewProductAnswer(BaseModel):
    """"None of these, it's …": what the line was, described in the shopper's words.

    Any language, as loose as they like: kind, brand, what it is for. The
    server reads it into its own format (`matching.described_product`) and
    keeps the words beside the answer; the shopper never writes our format,
    which may change (Parham, 2026-10-01).
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        min_length=1, description="What it was, in your own words, e.g. "
                                  "'salted pickled cucumbers, the Pamir ones'")


class LineResolutionRequest(BaseModel):
    """The shopper's answer for one line, in exactly one of three ways, or
    `product_id: null` to withdraw it."""

    model_config = ConfigDict(extra="forbid")

    product_id: str | None = Field(
        default=None,
        description="A product id from the catalog, or null to withdraw the answer")
    candidate: int | None = Field(
        default=None, ge=1,
        description="The number of a candidate in this line's question (GET /v1/questions); "
                    "a shop listing the catalog lacks becomes a product")
    new_product: NewProductAnswer | None = Field(
        default=None, description="None of the candidates: a new product in the shopper's words")
    confirmed_by: str | None = Field(default=None,
                                     description="Who answered; defaults to 'shopper'")
    basis: str | None = Field(default=None, description="How they knew: memory, photo, ...")


class QuestionCandidate(BaseModel):
    """One product a question offers. `number` is what an answer quotes back."""

    number: int
    name: str
    brand: str | None
    pack_size: str | None
    product_id: str | None = Field(description="Set when the catalog already holds it")
    article: str | None = Field(description="The shop's article number, when a shop lists it")
    url: str | None


class Question(BaseModel):
    """A line nothing could place, waiting for the shopper."""

    receipt_id: int
    position: int
    store: str | None
    date: str | None
    raw_name: str
    paid: float | None = Field(description="Shelf price paid, before discount (per kg if weighed)")
    per_line: bool = Field(description="The till prints this name for anything, so the answer "
                                       "is about this line only and is never remembered")
    candidates: list[QuestionCandidate] = Field(
        description="What the matcher found; empty when it was not run or found nothing")
    model_pick: int | None = Field(description="The candidate the model would pick, if any")
    reason: str | None = Field(description="The model's reason, in one sentence")
    unclear: str | None = Field(
        default=None, description="Why identify could not tell what the line is, when it "
                                  "was run: the part of the printed name it cannot read")
    choices: list[str] = Field(
        default_factory=list, description="What a web search for the whole line narrowed it "
                                          "down to, when identify could not tell; best first")


class SpotCheck(BaseModel):
    """A line the app placed on its own, put to the shopper at random."""

    receipt_id: int
    position: int
    store: str | None
    date: str | None
    raw_name: str
    paid: float | None = Field(description="Shelf price paid, before discount (per kg if weighed)")
    app_product_id: str = Field(description="What the app said the line is")
    app_product: str | None = Field(description="That product's name")
    brand: str | None
    category_path: list[str] | None
    decided_by: str | None = Field(
        description="Which part of the app said it: `matcher`, `identify`, `produce` (the "
                    "produce vocabulary) or `price` (a price narrowing a family)")


class ReceiptSummary(BaseModel):
    """One receipt in the list, and how far its product lines are placed."""

    receipt_id: int
    date: str | None
    store: str | None
    source_image: str
    printed_total: float | None
    is_duplicate: bool
    product_lines: int
    said_by_you: int
    said_by_app: int
    unplaced: int


class ProductMatch(BaseModel):
    """A catalog product a search found."""

    product_id: str
    name: str | None
    brand: str | None
    variant: str | None
    category_path: list[str] | None


class ChecksMeta(BaseModel):
    open: int
    right: int = Field(description="Answered with the product the app said")
    corrected: int = Field(description="Answered with another product")
    error_rate: float | None = Field(
        description="corrected / (right + corrected): the app's mistake rate on lines it was "
                    "sure of, on real shopping; null before any check is answered")


class ChecksDocument(BaseModel):
    """Open spot checks, oldest receipt first, and what the answered ones say."""

    meta: ChecksMeta
    checks: list[SpotCheck]


class QuestionsMeta(BaseModel):
    open: int
    matcher_answers: int = Field(description="Names the memory holds on the matcher's word")
    identify_answers: int = Field(description="Names the memory holds on identify's word")
    overruled: int = Field(description="Machine answers the shopper corrected (`corrections`)")
    held_back: int = Field(0, description="Questions not shown because no web search narrowed "
                                          "them down (`searched=true` only)")


class QuestionsDocument(BaseModel):
    """Every open question, oldest receipt first, and how the machine is doing."""

    meta: QuestionsMeta
    questions: list[Question]


class ReceiptPatch(BaseModel):
    """The two header facts a shopper can correct. Nothing else is writable."""

    model_config = ConfigDict(extra="forbid")

    is_duplicate: bool | None = Field(
        default=None,
        description="The same paper photographed twice; a duplicate leaves the history")
    store: str | None = Field(
        default=None, description="The store, for a photo whose header was cropped off")


class JobDocument(BaseModel):
    """One extraction job, as the phone polls it.

    `cost_usd` is in dollars because the provider bills in dollars; the euro
    amounts elsewhere come off a receipt and are a different thing.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    image_sha256: str
    original_filename: str | None
    receipt_id: int | None = Field(description="The receipt, once the job is done")
    model: str | None
    prompt_version: str | None
    cost_usd: float | None
    error: str | None
    created_at: str | None
    started_at: str | None
    finished_at: str | None


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    purchases_contract_version: int
    insights_contract_version: int
    receipts: int = Field(description="Receipts behind the served history")
    uploads: bool = Field(
        default=False,
        description="Whether this server can accept a photo at POST /v1/receipts")
    writes: bool = Field(
        default=False,
        description="Whether this server can record corrections (needs a database)")
