# Organizer historical data foundation

`treasury_4tier_dataset.csv` is the authoritative historical source. The reader
never writes it, resamples it, allocates its hourly flows to fabricated events,
converts rates to integer basis points, or changes timezone semantics.

## Read and validate

From the repository root, with backend dependencies installed:

```powershell
$env:PYTHONPATH = 'backend;.'
python -m app.data.organizer
```

On Linux/macOS use `PYTHONPATH=backend:. python -m app.data.organizer`.
This local diagnostic command prints metadata and validation counts, not the
full dataset. It adds no public API or database writes.

The default `ORGANIZER_DATASET_PATH=treasury_4tier_dataset.csv` resolves from the
repository root regardless of the caller's working directory. Override the
setting with an absolute source location or repository-relative path. A missing
source raises `FileNotFoundError`; it never falls back to synthetic data.
Container users must supply the source file through their deployment's data
mount/configuration; this milestone does not change Docker orchestration.

```python
from app.data.organizer import OrganizerDatasetSource

dataset = OrganizerDatasetSource().load()
first = dataset.observation_at(0)
observed_history = dataset.history_through(23)  # inclusive, first 24 observations
identity = dataset.metadata.dataset_id
```

There is no replay implementation yet. Future historical replay must pass only
an observed chronological prefix to forecasting. Dataset access by itself does
not enforce a forecasting information boundary.

## Schema, precision, and immutability

`HourlyObservation` contains exactly the 16 source columns. Numbers are parsed
from source strings directly into finite `Decimal` values, with no quantization.
Binary floats are rejected. Rates/yields may be signed finite values; observed
minimum/maximum values are not hard-coded as admissible bounds. Deposits,
withdrawals, volatility, and overdraft penalty must be nonnegative; prices and
duration must be positive; haircut percentages must be within 0–100.

Timestamps retain the source's timezone-unspecified `YYYY-MM-DD HH:MM:SS`
semantics. No UTC/IST conversion occurs. Flags accept source `True`/`False`.
The loader checks a complete 8,760-row hourly sequence, unique increasing
timestamps, and repo flags at 17:00/08:00. Counts of flags and reconciliation
outcomes are calculated, never used as fixed loader acceptance assumptions.
Tests can configure shorter expected row counts for isolated invalid fixtures.

The dataset, observations, metadata, and validation summaries are frozen;
observations are held in a tuple. Input files are read once as bytes. That exact
snapshot is both hashed and parsed, preventing provenance from referring to a
different read of a changing file. Loaded snapshots remain independent of later
external file changes. Negative/out-of-range observation indices are rejected.
The source CSV is tracked without Git line-ending conversion (`-text` in
`.gitattributes`) so its content identity remains stable across Windows/Linux
checkouts. That rule does not rewrite the source file.

## Provenance and diagnostics

Metadata records dataset name, `ORGANIZER_CSV` source type, configured path,
SHA-256, content-addressed dataset ID, row count, first/last timestamps, native
3,600-second interval, `UNSPECIFIED` timezone, and validation status. Metadata has
no wall-clock creation timestamp, so repeated loads are reproducible. Persist
this content identity with future historical runs; no provenance table is added
before the persistence milestone.

`derived_net_flow_usd` is deposits minus withdrawals. `net_flow_residual_usd` is
the supplied `net_flow_usd` minus that derived value. Each observation reports
`EXACT_MATCH`, `ONE_CENT_DIFFERENCE`, or `OTHER_DIFFERENCE`. Source net flow is
always retained. Even larger residuals are diagnostics rather than silent
corrections or guessed replacement values.

Successful validation with any nonzero residual is
`VALIDATED_WITH_DIAGNOSTICS`; otherwise it is `VALIDATED`. Invalid structure,
numeric fields, timestamps, or repo schedule raise `DatasetValidationError` with
immutable issues containing code, CSV line, field, and message. No partial
validated dataset is returned after an error.

## Current source identity

- SHA-256: `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`
- 8,760 hourly observations, 16 columns, from 2026-01-01 00:00:00 through
  2026-12-31 23:00:00; source timezone unspecified.
- Measured reconciliation: 6,642 exact matches, 2,118 one-cent differences,
  zero other differences, +$0.10 total residual.

These are measured properties of this file, not hard-coded loader allowances.
There is no trading, portfolio execution, engine integration, or synthetic-data
substitution in this milestone.

## Graphify coverage

The code graph represents the source loader, observation validators, metadata,
diagnostics, and tests. Curated source relationships identify the actual CSV and
its SHA-256 provenance. The historical replay consumer is explicitly marked
planned, not implemented. Graphify's code extractor does not discover the CSV
file relationship automatically; retain these evidence-based relationships when
refreshing the graph. Its optional PDF and SQL parsers are unavailable in the
current Graphify runtime; their extraction warnings do not affect CSV validation.
