"""The runtime store: PostgreSQL tables behind the same contracts as the files.

Files under data/ stay the developer interface (the CLI, eval and tests read
them); these tables hold the same data for the server. Two rules carry over
from docs/data-layout.md and are enforced by the schema, not by convention:

- truth stays uninterpreted: `receipt_lines.tax_class` is what the paper
  printed, and there is no rate column;
- a receipt never holds a product id: resolution is a join through
  `resolutions` and `line_resolutions`, done at read time by the normalizer.

See docs/designs/backend-api.md, phase 1.
"""
