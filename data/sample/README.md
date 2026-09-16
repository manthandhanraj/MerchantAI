# Sample data

Two merchants x three days, hand-written in Stage 1 for one purpose: to prove
the schema in [`docs/DATA_SCHEMA.md`](../../docs/DATA_SCHEMA.md) is valid and
loadable. `tests/test_data_schema.py` validates these files on every run.

This is **not** the demo dataset. Stage 2 generates the full synthetic dataset
into `data/raw/`. Do not build features against these files.

The sample satisfies every documented invariant, including inventory
continuity (`closing stock = previous closing - units sold`), so it doubles as
a worked example of what Stage 2's generator must produce.
