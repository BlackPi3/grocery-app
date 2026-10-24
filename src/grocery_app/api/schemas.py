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

from datetime import datetime
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
# And to 7 on 2026-10-05: `not_counted` marks a line the shopper left out of
# their numbers with one tap.
# And to 8 on 2026-10-09: `product_line` and `variant` became one list,
# `details` (migration 0011): two fixed slots the reader guessed between.
PURCHASES_CONTRACT_VERSION = 8
#
# Insights bumped to 3 on 2026-09-29: lines known not to be groceries (café,
# flowers, cards) left every insight, so `coverage.spend` means grocery spend,
# and `coverage.not_grocery` says what was left out.
#
# Insights bumped to 4 on 2026-10-01: price changes and the basket compare
# like with like (loose with loose, packs with packs), so an entry carries
# `sold_as` and the basket names product and form.
#
# Insights bumped to 5 on 2026-10-05: lines the shopper marked `not_counted`
# leave spend, cadence, the basket and the budget-brand share (they still
# count as prices), and `coverage.not_counted` says what was left out.
# Insights bumped to 9 on 2026-10-14: `discounts` says what printed discounts
# saved, per month and per shop.
# Insights bumped to 10 on 2026-10-14: `regulars`, the products bought on 3
# days or more, for Home's rotating tile.
# Insights bumped to 11 on 2026-10-15: each month's `why`, why it is off its
# usual (parts of the shop, trips, prices), for the month page.
INSIGHTS_CONTRACT_VERSION = 11


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
    details: list[str] | None = Field(
        default=None, description="Everything the pack says besides name, brand, category "
                                  "and size (a range, a strength, a flavour), any number")
    # The vocabulary key (`reibekaese`), and the three labels it stands for
    # (`["Molkereiprodukte & Eier", "Käse", "Reibekäse"]`), coarsest first.
    category: str | None = None
    category_path: list[str] | None = None
    is_budget_brand: bool | None = None
    is_organic: bool | None = None
    not_counted: bool | None = Field(
        default=None,
        description="Present and true when the shopper left this line out of their numbers "
                    "(bought for someone else, a mistake): it stays on the receipt and in "
                    "price comparisons, and leaves spend, habits and the basket")


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
    regulars: list[dict[str, Any]]
    price_changes: list[dict[str, Any]]
    price_moves: list[dict[str, Any]]
    basket_index: dict[str, Any]
    budget_brand: dict[str, Any]
    cross_store: dict[str, Any]
    discounts: dict[str, Any]
    months: list[dict[str, Any]]


class FirstGuess(BaseModel):
    """What the photo reading guessed a line is, before anything placed it."""

    model_config = ConfigDict(extra="forbid")

    name: str | None
    category: str | None
    category_path: list[str] | None


class ReceiptLineView(Purchase):
    """A normalized line, with the position the correction routes address it by.

    `position` is not part of the purchases contract — it is how a client
    names one line of one receipt, and `normalize_receipt` emits exactly one
    record per printed line, in order, so the index is the position.

    `first_guess` is not part of it either, on purpose: it is the reading's
    guess, shown while a line is not placed, and the history never counts it.
    Only receipts read since prompt v3 have one.
    """

    position: int
    first_guess: FirstGuess | None = None


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
    """The shopper's answer for one line, in exactly one of four ways, or
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
    none_of_these: Literal[True] | None = Field(
        default=None,
        description="No on every card: the line stays not placed and is not asked again; on a "
                    "line the app placed, its product is counted as a mistake and forgotten")
    confirmed_by: str | None = Field(default=None,
                                     description="Who answered; defaults to 'shopper'")
    basis: str | None = Field(default=None, description="How they knew: memory, photo, ...")


class Picture(BaseModel):
    """A photo of the pack, where the app found it (`grocery_app.pictures`)."""

    url: str = Field(description="The app's own copy, under /pictures (no token needed)")
    from_: str = Field(alias="from",
                       description="The shop, `Open Food Facts`, or the site a web "
                                   "search found it on")
    page: str | None = Field(description="The page it is on, to look closer")


class QuestionCandidate(BaseModel):
    """One product a question offers. `number` is what an answer quotes back."""

    number: int
    name: str
    brand: str | None
    pack_size: str | None
    product_id: str | None = Field(description="Set when the catalog already holds it")
    article: str | None = Field(description="The shop's article number, when a shop lists it")
    url: str | None
    price: float | None = Field(
        default=None, description="Its shelf price nearest to what was paid, when one is known")
    picture: Picture | None = Field(default=None, description="A photo of the pack, if found")


class QuestionCard(BaseModel):
    """One yes/no card: a candidate by its number, or what a web search said."""

    model_config = ConfigDict(extra="forbid")

    candidate: int | None = None
    choice: str | None = None


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
    cards: list[QuestionCard] = Field(
        default_factory=list,
        description="What to ask with, one yes/no card at a time, first card first: the "
                    "price paid picks the order (`api.cards`)")


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
    details: list[str]
    sold_as: SoldAs | None = Field(
        description="Loose or a pack of what size: all the app claims is put to the shopper, "
                    "or 'right' could only judge half of it (Parham, 2026-10-08)")
    category_path: list[str] | None
    decided_by: str | None = Field(
        description="Which part of the app said it: `matcher`, `identify`, `produce` (the "
                    "produce vocabulary) or `price` (a price narrowing a family)")
    picture: Picture | None = Field(
        default=None, description="A photo of the pack, once the server has found one; "
                                  "none for a product known only as a kind of thing")


class SharedRequest(BaseModel):
    """Share an upload with the developer, or take it back."""

    model_config = ConfigDict(extra="forbid")

    shared: bool


class LeftOutLine(BaseModel):
    """A product line the shopper left out of their numbers."""

    name: str = Field(description="The product's name, else the printed name")
    net_paid: float | None


class ReceiptSummary(BaseModel):
    """One receipt in the list, and how far its product lines are placed."""

    receipt_id: int
    date: str | None
    store: str | None
    source_image: str
    printed_total: float | None
    product_lines: int
    said_by_you: int
    said_by_app: int
    unplaced: int = Field(description="Product lines nothing placed, not counting those the "
                                      "shopper left out")
    not_counted: int = Field(description="Product lines the shopper left out of their numbers")
    spend: float = Field(0.0, description="What the shopper's numbers count of it: the product "
                                          "lines they count, as paid (Home's month adds these)")
    left_out: list[LeftOutLine] = Field(default_factory=list,
                                        description="The product lines they left out, named")
    deposits: float = Field(0.0, description="Deposits paid less returned; not spend")
    lines_total: float | None = Field(None, description="Every line as read, added up: "
                                                        "unlike `printed_total`, something "
                                                        "was misread")
    shared: bool = Field(False, description="Its upload is shared with the developer "
                                            "(`PUT /v1/receipts/{receipt_id}/shared`)")
    photo: bool = Field(default=False,
                        description="The photo or PDF it was read from can be fetched "
                                    "(`GET /v1/receipts/{receipt_id}/photo`)")
    seen_at: str | None = Field(
        default=None,
        description="When its owner first opened it (`PUT /v1/receipts/{receipt_id}/seen`); "
                    "null while it is new to them")


class ProductPurchase(BaseModel):
    """One receipt line placed as the product: where to open it, and what it cost."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: int
    position: int = Field(description="The line on that receipt, as `GET /v1/receipts/{id}` "
                                      "numbers it")
    date: str | None
    store: str | None
    raw_name: str = Field(description="What the paper printed")
    qty: float
    net_paid: float
    unit_price: UnitPrice | None = None
    shelf_unit_price: UnitPrice | None = Field(
        None, description="The shelf price per unit before printed discounts, as every "
                          "price insight reads it (`insights.shelf_unit_price`)")
    sold_as: SoldAs | None = None
    said_by: Literal["you", "app"] | None
    not_counted: bool = False


class ProductPurchases(BaseModel):
    """Every purchase of one product, oldest first: what an insight about it
    was computed from, line by line (the drill-down, 2026-10-12)."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    product: str | None
    brand: str | None
    category_path: list[str] | None
    purchases: list[ProductPurchase]


class ProductMatch(BaseModel):
    """A catalog product a search found."""

    product_id: str
    name: str | None
    brand: str | None
    details: list[str]
    category_path: list[str] | None


class ChecksMeta(BaseModel):
    open: int
    right: int = Field(description="Answered with the product the app said")
    corrected: int = Field(description="Answered with another product")
    error_rate: float | None = Field(
        description="corrected / (right + corrected): the app's mistake rate on lines it was "
                    "sure of, on real shopping; null before any check is answered")
    held_back: int = Field(0, description="Checks not shown yet: their product's picture is "
                                          "still being looked up (`api.pictures`)")


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


class LineCountedRequest(BaseModel):
    """One tap on a line: leave it out of my numbers (`false`), or count it again."""

    model_config = ConfigDict(extra="forbid")

    counted: bool


class Seen(BaseModel):
    """A receipt opened: when it was first."""

    receipt_id: int
    seen_at: str


class ReceiptPatch(BaseModel):
    """The header fact a shopper can correct. Nothing else is writable."""

    model_config = ConfigDict(extra="forbid")

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
    receipt_id: int | None = Field(
        description="The receipt, as soon as the photo is read: lines are still being "
                    "placed until the job is done")
    model: str | None
    prompt_version: str | None
    cost_usd: float | None
    error: str | None
    already_added: bool = Field(
        description="The photo was of a receipt already in the history: `receipt_id` is "
                    "that receipt, and nothing new was stored")
    turned_away: Literal["restaurant_or_cafe", "other_business", "not_a_receipt"] | None = Field(
        description="The photo was not of a shop receipt, and nothing was stored: where the "
                    "reader says it is from")
    shared: bool = Field(False, description="The sender shared it with the developer "
                                            "(`PUT /v1/jobs/{job_id}/shared`)")
    created_at: str | None
    started_at: str | None
    finished_at: str | None


class Me(BaseModel):
    """Who a password belongs to."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["owner", "user"]
    name: str | None = Field(description="A user's name; none for the owner")
    demo: bool = Field(False, description="The public demo: made-up receipts, wiped on "
                                          "every restart (`grocery_app.demo`)")
    contact: str | None = Field(None, description="In the demo, the developer's address, "
                                "to ask for an account; none elsewhere")


class UserSummary(BaseModel):
    """Someone who uses the app besides the owner."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    email: str | None = Field(None, description="The Google address they sign in with; "
                                                "none when they have a password only")
    receipts: int
    last_sign_in: datetime | None = Field(None, description="Their latest Google sign-in")
    last_upload: datetime | None = Field(None, description="When they last sent a photo, "
                                                           "read or not")
    month_cost_usd: float = Field(0.0, description="What their uploads' model calls cost "
                                                   "this month (UTC), at list price")


class NewUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    email: str | None = Field(None, max_length=254,
                              description="Their Google address, to sign in with Google. "
                                          "A first Google sign-in makes its user itself.")


class UserPatch(BaseModel):
    """Give a user a Google address, change it, or take it away (null)."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(max_length=254)


class NewUser(BaseModel):
    """A user just made. `password` is shown this once and kept nowhere."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    email: str | None = None
    password: str


class AuthConfig(BaseModel):
    """How one may sign in here; open, so the page can ask before it has a password."""

    model_config = ConfigDict(extra="forbid")

    google_client_id: str | None = Field(
        description="The Google OAuth client id the page's Google button uses; none when "
                    "Google sign-in is off (not configured, or the demo)")


class GoogleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=1, max_length=8192,
                            description="The ID token Google Identity Services handed the page")


class SignedIn(BaseModel):
    """A sign-in: `token` goes in `Authorization: Bearer`, like a password.
    Shown this once; only its hash is kept."""

    model_config = ConfigDict(extra="forbid")

    token: str
    role: Literal["owner", "user"]
    name: str | None = Field(description="A user's name; none for the owner")
    expires_at: datetime


class MonthCost(BaseModel):
    """What the model calls cost in one month, by what they were for."""

    model_config = ConfigDict(extra="forbid")

    month: str = Field(description="YYYY-MM, when the money was spent (UTC)")
    total_usd: float
    reading_usd: float = Field(description="Reading receipt photos")
    finding_usd: float = Field(description="Finding what receipt lines are: matching and "
                                           "identifying, searches included")
    pictures_usd: float = Field(description="Finding product photos")
    other_usd: float = Field(description="Any other call, e.g. one made answering a question")
    searches: int = Field(description="Web searches the model ran; the first "
                                      "`free_searches_per_month` are free")
    receipts: int = Field(description="Receipts processed this month")
    per_receipt_usd: float | None = Field(
        description="Average reading + finding cost of this month's receipts whose finding "
                    "was recorded; null when there is none")
    billed_usd: float = Field(
        description="`total_usd` less the month's free searches: what Google bills")
    billed_per_receipt_usd: float | None = Field(
        description="`per_receipt_usd` less each receipt's share of the free searches")


class ReceiptCost(BaseModel):
    """What processing one receipt cost."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: int
    month: str
    reading_usd: float
    finding_usd: float
    searches: int
    total_usd: float
    finding_recorded: bool = Field(
        description="False for a receipt processed before finding was recorded: its "
                    "`finding_usd` is unknown, not zero")


class CostsDocument(BaseModel):
    """What the app's model calls cost, at list price, in dollars. The server
    and the database are billed by Google separately and are not in here."""

    model_config = ConfigDict(extra="forbid")

    months: list[MonthCost] = Field(description="Newest first")
    receipts: list[ReceiptCost]
    free_searches_per_month: int
    finding_recorded_from: str


class OfferRecord(BaseModel):
    """One shop offer as read from the offers source (`offers.read_offer`)."""

    model_config = ConfigDict(extra="forbid")

    source: str
    id: str
    chain: str
    brand: str | None
    product: str | None
    description: str | None
    category: str | None
    price: float
    price_before: float | None
    pack: dict[str, Any] | None = Field(description="amount of unit, count packs")
    per_unit: dict[str, Any] | None
    valid_from: str
    valid_to: str
    loyalty_card: bool


class OfferSaving(BaseModel):
    model_config = ConfigDict(extra="forbid")

    per_unit: float = Field(description="Euros less per unit than usually paid")
    share: float = Field(description="That as a share of the usual price, 0 to 1")


class OfferMatch(BaseModel):
    """An offer for one of the asker's regular groceries (`offer_match.match`)."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    product: str
    brand: str | None
    label: str = Field(description='"your product" or "like yours"')
    offer: OfferRecord
    usual_per_unit: UnitPrice | None = Field(
        description="What the asker usually paid per the offer's unit; none to compare")
    saving: OfferSaving | None


class OffersDocument(BaseModel):
    """The asker's offers for the coming week, their own products first."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    offers: list[OfferMatch]


class ListUsual(BaseModel):
    """The product a person usually takes of a kind: a hint, not the line."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    product: str | None
    brand: str | None


class ListLine(BaseModel):
    """One kind on the shopping list (`shopping_list.kind`). An added kind
    bought on too few days to judge has no chance or run-out."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="The category key, `eier`")
    name: str
    usual: ListUsual | None
    products: int = Field(description="How many products of this kind were bought")
    days_bought: int
    last_bought: str | None
    chance: float | None = Field(description="Of a buy in the coming week, 0 to 1")
    days_per_buy: float | None = Field(description="How long one usual buy lasts")
    runs_out: str | None
    days_left: int | None
    when: Literal["now", "this_week", "later"]
    added: bool = Field(description="On the list because the person added it")


class ListSnoozed(BaseModel):
    """A kind the person removed for now: off the list until `until`."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    until: str = Field(description="The first day it is back")
    times: int = Field(description="Removals since it was last bought")


class ShoppingListDocument(BaseModel):
    """The asker's shopping list today, with their edits (`shopping_list.with_edits`)."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    lines: list[ListLine] = Field(description="What they added first, then the most urgent")
    snoozed: list[ListSnoozed]


class ListEditRequest(BaseModel):
    """One tap on the list: put a kind on it (`true`), or take it off for now."""

    model_config = ConfigDict(extra="forbid")

    on_list: bool


class OffersRhythm(BaseModel):
    """When one chain's offers are first seen (`offers.rhythm`)."""

    model_config = ConfigDict(extra="forbid")

    chain: str
    offers: int = Field(description="Offers first seen before their first day")
    usual_day: str = Field(description="The weekday most of them were first seen, Mon to Sun")
    days_ahead: int = Field(description="How many days before they start, on that weekday")
    by_day: dict[str, int] = Field(description="Offers first seen on each weekday")


class SurenessCounts(BaseModel):
    """Product lines by how sure the app is of them (`grocery_app.sureness`).
    A line the shopper left out of their numbers is not counted."""

    model_config = ConfigDict(extra="forbid")

    lines: int = Field(description="Product lines counted: answered plus the four levels")
    answered: int = Field(description="A person said what the line is, or that it was "
                                      "none of what the app offered")
    sure: int = Field(description="Level 1: the app placed it on one product, from its "
                                  "memory of the printed name or the produce vocabulary")
    unclear_print: int = Field(description="Level 2: the printed name stands for several "
                                           "products; the price paid picked one")
    category_only: int = Field(description="Level 3: the printed name stands for several "
                                           "products of one category; none picked")
    needs_answer: int = Field(description="Level 4: nothing placed it; only a person can say")
    print_says_nothing: int = Field(description="Of level 4: a name the till prints for "
                                                "anything (the receipt's fault)")
    category_guessed: int = Field(description="Of level 4: the photo reading guessed a "
                                              "category, which the history does not use")


class MonthSureness(SurenessCounts):
    month: str | None = Field(description="The shopping month, YYYY-MM; null for a receipt "
                                          "with no date")


class CheckOutcomes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    right: int
    corrected: int
    yes_rate: float | None = Field(description="right / (right + corrected); null before any "
                                               "spot check is answered")


class SurenessDocument(SurenessCounts):
    """How sure the app is of every product line, over everyone's receipts,
    and what the spot checks on its own lines say."""

    checks: CheckOutcomes
    months: list[MonthSureness] = Field(description="Newest first")


class JobsDocument(BaseModel):
    """The photos still being read or placed, and the ones that failed in the
    last hour: the same list on every device."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[JobDocument]


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
