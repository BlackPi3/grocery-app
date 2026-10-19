"""Build the public demo's database seed from the made-up receipts.

Each receipt in demo/receipts/ goes through the same upload path a phone
uses (`POST /v1/receipts`, the job, the matcher, identify, the spot checks),
with one difference: the photo reader is replaced by the made-up reading.
So the demo's catalog, questions and insights are what the app really made
of those receipts, not something written by hand. A picture of each receipt
is drawn too, so a guest sees a photo like any other.

    GEMINI_VERTEX_PROJECT=<project> .venv/bin/python scripts/build_demo_seed.py

Writes src/grocery_app/demo_seed.sql (the demo server loads it on every start,
`grocery_app.demo`) and, under data/demo/, the receipt pictures (uploads/)
and product pictures (pictures/) that go to the bucket. Costs a few cents of
model calls; they are recorded in the seed, so the demo shows what it cost.

Every product's picture is settled before the seed is written: the demo
never looks up a seeded product's picture itself (`api.pictures`), since a
picture found there is gone at its next start. When a picture search could
not be made, nothing is written; run again with `--resume` to try those once
more. `--retry-pictures` (with `--resume`) looks again for every product that
has no picture, after the lookup was improved; each search costs some 20 cents.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import create_engine, func, text, update

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from grocery_app import matcher as matching  # noqa: E402
from grocery_app import spend  # noqa: E402
from grocery_app.api.app import (  # noqa: E402
    GEMINI_MODEL,
    create_app,
    identify_decider,
    identify_searcher,
    matcher_decider,
)
from grocery_app.api.images import DiskImageStore, sha256_of  # noqa: E402
from grocery_app.api.matching import line_identifier, line_matcher  # noqa: E402
from grocery_app.api.pictures import (  # noqa: E402
    Pictures,
    default_pictures,
    fill_all_pictures,
    forget_missing_pictures,
)
from grocery_app.api.repository import PostgresRepository  # noqa: E402
from grocery_app.db.migrate import upgrade  # noqa: E402
from grocery_app.db.models import Receipt  # noqa: E402
from grocery_app.db.session import make_session_factory  # noqa: E402
from grocery_app.extract import Extraction  # noqa: E402

RECEIPTS = ROOT / "demo" / "receipts"
SEED = ROOT / "src" / "grocery_app" / "demo_seed.sql"
FONT = "/System/Library/Fonts/Menlo.ttc"


def euro(amount: float, places: int = 2) -> str:
    return f"{amount:.{places}f}".replace(".", ",")


def draw(doc: dict) -> bytes:
    """A till slip with the receipt's text, marked as made up. No date: the
    demo moves its dates to the visit (`demo.move_dates`), a drawn one would
    not move with them."""
    font = ImageFont.truetype(FONT, 22)
    small = ImageFont.truetype(FONT, 18)
    rows = [(doc["store"], font, "center"), (doc["store_location"], small, "center"),
            ("", font, "")]
    for line in doc["lines"]:
        name = line["raw_name"] if line["qty"] == 1 else f"{line['qty']} x {line['raw_name']}"
        amount = line.get("gross", line["net"])
        rows.append((f"{name[:32]:<32}{euro(amount):>8} {line['tax_class']}", font, ""))
        if line.get("sold_by_weight"):
            weighed = f"  {euro(line['weight_kg'], 3)} kg x {euro(line['unit_price'])} EUR/kg"
            rows.append((weighed, small, ""))
        if line.get("discount"):
            rows.append((f"{'  Rabatt':<32}{euro(line['discount']):>8}", font, ""))
    rows += [("-" * 42, font, ""), (f"{'SUMME EUR':<32}{euro(doc['printed_total']):>8}", font, ""),
             ("", font, ""), (f"Uhrzeit {doc['time']}", small, "center"),
             ("MADE-UP DEMO RECEIPT", small, "center")]
    width, height = 620, 40 + 32 * len(rows)
    image = Image.new("RGB", (width, height), "#fbfaf6")
    pen = ImageDraw.Draw(image)
    y = 20
    for words, face, align in rows:
        x = 20 if align != "center" else (width - pen.textlength(words, font=face)) / 2
        pen.text((x, y), words, font=face, fill="#222")
        y += 32
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=88)
    return out.getvalue()


class MadeUpReader:
    """The photo reader's stand-in: answers each drawn slip with its receipt."""

    def __init__(self) -> None:
        self.by_sha: dict[str, dict] = {}

    def __call__(self, path: Path) -> Extraction:
        return Extraction(receipt={**self.by_sha[path.name], "source_image": path.name},
                          meta={"model": "made-up", "prompt_version": "demo", "cost_usd": 0})


def fresh_database(url: str) -> None:
    name = url.rsplit("/", 1)[1]
    admin = create_engine(url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="postgresql+psycopg:///grocery_demo")
    parser.add_argument("--files", default=str(ROOT / "data" / "demo"))
    parser.add_argument("--resume", action="store_true",
                        help="keep the database and skip the receipts already in it")
    parser.add_argument("--retry-pictures", action="store_true",
                        help="look again for every product that has no picture")
    args = parser.parse_args()
    logging.basicConfig(format="%(message)s")
    logging.getLogger("grocery_app.pictures").setLevel(logging.INFO)  # why none was found

    if not args.resume:
        fresh_database(args.url)
    upgrade(args.url)
    factory = make_session_factory(create_engine(args.url))
    spend.install(spend.database_sink(factory))
    files = Path(args.files)
    reader = MadeUpReader()

    matcher = line_matcher(matcher_decider("gemini"), matching.default_shops())
    identify = line_identifier(identify_decider("gemini"), identify_searcher("gemini"))
    app = create_app(PostgresRepository(factory), DiskImageStore(files / "uploads"), reader,
                     matcher, identify)
    client = TestClient(app)
    if args.resume:  # a job a stopped build cut off is finished, not read again
        from grocery_app.api.jobs import resume_unfinished

        for path in sorted(RECEIPTS.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            reader.by_sha[sha256_of(draw(doc))] = doc
        print("finished:", resume_unfinished(factory, DiskImageStore(files / "uploads"), reader,
                                             matcher, identify), flush=True)
    for path in sorted(RECEIPTS.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        photo = draw(doc)
        reader.by_sha[sha256_of(photo)] = doc
        if PostgresRepository(factory).job_for_image(sha256_of(photo)):
            print(f"{path.stem}: already in", flush=True)
            continue
        job = client.post("/v1/receipts", files={"file": (path.stem + ".jpg", photo, "image/jpeg")})
        done = client.get(f"/v1/jobs/{job.json()['job_id']}").json()
        print(f"{path.stem}: {done['status']} {done.get('error') or ''}", flush=True)

    # Said plainly: nobody read these off a photo. And a guest starts with no
    # "new" marks: the made-up receipts are already there, not just arrived.
    with factory() as session:
        session.execute(update(Receipt).values(transcribed_by="made-up", seen_at=func.now()))
        session.commit()

    if args.retry_pictures:
        with factory() as session:
            print("pictures: looking again for", forget_missing_pictures(session), flush=True)
            session.commit()
    service = default_pictures(model=GEMINI_MODEL)
    service = Pictures(find=service.find, download=service.download,
                       store=DiskImageStore(files / "pictures"))
    with spend.tagged("pictures"):
        unknown = fill_all_pictures(factory, service)
    if unknown:
        sys.exit(f"pictures: the lookup could not be made for {', '.join(unknown)}; "
                 "no seed written. Run again with --resume.")

    dump = subprocess.run(["pg_dump", "--inserts", "--no-owner", "--no-privileges",
                           "--no-comments", args.url.replace("+psycopg", "")],
                          check=True, capture_output=True, text=True).stdout
    SEED.write_text(dump, encoding="utf-8")
    print(f"seed: {SEED} ({len(dump) // 1024} KB)")


if __name__ == "__main__":
    main()
