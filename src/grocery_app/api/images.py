"""Where an uploaded photo's bytes live.

`ImageStore` is the seam, the same idea as `Repository`: the routes talk to
the protocol, and storage is a class behind it. Today the only implementation
is a folder on disk; deployed, it becomes object storage (R2 or S3), and that
is a new class rather than a change to any route.

Photos are content-addressed — the file is named by the sha256 of its bytes.
That is what makes "have I already paid to read this photo?" a lookup instead
of a comparison, and it sidesteps the fact that every phone upload is called
`image.jpg`. The bytes are stored exactly as uploaded, never the downscaled
copy `extract.prepare_image` makes, so a better prompt can be run later
against the original.
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image, UnidentifiedImageError

DEFAULT_ROOT = "data/uploads"
ENV_VAR = "GROCERY_IMAGES"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def looks_like_an_image(data: bytes) -> bool:
    """Can the extractor actually open this?

    Checked at upload rather than in the job, so a phone that sends something
    unreadable hears about it in the response instead of in a failed job ten
    seconds later. `verify()` reads the header only; it does not decode.
    """
    try:
        Image.open(io.BytesIO(data)).verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    return True


@runtime_checkable
class ImageStore(Protocol):
    def put(self, sha256: str, data: bytes) -> None:
        """Store the bytes under their hash. Storing the same bytes twice is a no-op."""
        ...

    def path(self, sha256: str) -> Path:
        """A local path the extractor can open."""
        ...

    def size(self, sha256: str) -> int | None:
        """Bytes held under this hash, or None if nothing is."""
        ...


class DiskImageStore:
    """A folder of photos named by hash, with no file extension.

    No extension because the name is an identity, not a description, and the
    extractor sniffs the format from the bytes anyway. The job row keeps the
    name the phone used, for humans reading the table.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, sha256: str) -> Path:
        return self.root / sha256

    def put(self, sha256: str, data: bytes) -> None:
        destination = self.path(sha256)
        if destination.exists():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename: a crash mid-write must not leave
        # a truncated file sitting under a hash that promises whole bytes.
        temporary = destination.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(destination)

    def size(self, sha256: str) -> int | None:
        destination = self.path(sha256)
        return destination.stat().st_size if destination.exists() else None


def default_image_store() -> DiskImageStore:
    return DiskImageStore(os.environ.get(ENV_VAR, DEFAULT_ROOT))
