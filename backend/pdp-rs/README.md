# PyO3 PDP beat (stretch)

The Python `patient360.pdp.evaluate` contract stays the default. FastAPI callers do not import this crate.

The crate exports the same function:

```text
evaluate(subject, resource, context, check) -> Decision
```

with identical reason codes (`relationship_missing_or_expired`, `self_mismatch`,
`notes_not_allowed`, `pixels_not_allowed`, …). `tests/test_pdp_rs.py` compares
this crate to the Python matrix. FastAPI callers stay on Python.

Build the extension with `cargo build --release` in this directory before that test.
