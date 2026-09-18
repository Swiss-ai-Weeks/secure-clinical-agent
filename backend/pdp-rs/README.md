# PyO3 PDP beat (stretch)

The Python `patient360.pdp.evaluate` contract stays the default.

A future Rust crate should export the same function:

```text
evaluate(subject, resource, context, check) -> Decision
```

with identical reason codes (`relationship_missing_or_expired`, `self_mismatch`,
`notes_not_allowed`, `pixels_not_allowed`, …). Do not change the FastAPI
callers until the Rust beat matches `tests/test_pdp_matrix.py`.
