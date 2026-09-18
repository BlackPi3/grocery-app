"""The HTTP layer over the pipeline's contracts.

`purchases.json` is the contract; this package serves it. Nothing here
computes anything the CLI cannot: routes call the same functions
(`build_insights`, ...) and read the same documents. The storage behind the
routes is hidden behind `Repository` so it can move from JSON files to a
database without the routes or their clients noticing.

See docs/designs/backend-api.md for the phases and the endpoint contract.
"""
