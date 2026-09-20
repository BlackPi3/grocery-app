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

PURCHASES_CONTRACT_VERSION = 2
INSIGHTS_CONTRACT_VERSION = 1


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
    resolution: Literal["exact", "user", "price", "family", "none"]
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
    category: str | None = None
    is_own_brand: bool | None = None
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

    contract_version: Literal[2]
    meta: PurchasesMeta
    purchases: list[Purchase]


class InsightsDocument(BaseModel):
    """`insights.json`, typed at the top level only (see module docstring)."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1]
    as_of: str
    coverage: dict[str, Any]
    repurchase: list[dict[str, Any]]
    price_changes: list[dict[str, Any]]
    basket_index: dict[str, Any]
    own_brand: dict[str, Any]
    cross_store: dict[str, Any]


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
