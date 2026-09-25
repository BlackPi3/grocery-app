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
PURCHASES_CONTRACT_VERSION = 4
INSIGHTS_CONTRACT_VERSION = 2


class UnitPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float
    per: str = Field(description="The basis: 'kg', 'l', 'piece', ...")


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
    candidate_ids: list[str]
    qty: float
    gross: float | None
    discount: float
    net_paid: float
    tax_class: str | None = Field(description="As printed on the receipt, never interpreted")
    tax_rate: float | None
    unit_price: UnitPrice | None = None

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
    """"None of these, it's …": a product nobody lists, in the shopper's words."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="What it was, e.g. 'Kashk'")
    brand: str | None = Field(default=None, description="The brand, when the shopper knows it")


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


class QuestionsMeta(BaseModel):
    open: int
    matcher_answers: int = Field(description="Names the memory holds on the matcher's word")
    overruled: int = Field(description="Machine answers the shopper corrected (`corrections`)")


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
