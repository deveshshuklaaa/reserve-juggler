"""Bounded organizer CSV imports, immutable storage and persisted replay sources."""
import csv
import hashlib
import io
import re
from pathlib import Path

from sqlalchemy import select

from app.data.organizer import (
    DatasetMetadata, DatasetValidation, DatasetValidationError, OrganizerDataset,
    OrganizerDatasetSource, ValidationIssue,
)
from app.persistence.models import DatasetSource
from app.persistence.repositories import DatasetRepository

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_ROWS = 5000


def invalid(code, message, row=None, field=None):
    raise DatasetValidationError((ValidationIssue(code=code, message=message, row=row, field=field),))


def validate_upload(raw: bytes) -> OrganizerDataset:
    if len(raw) > MAX_UPLOAD_BYTES:
        invalid('FILE_SIZE', 'CSV files must be 2 MB or smaller.')
    try:
        records = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    except (UnicodeDecodeError, csv.Error):
        invalid('CSV', 'Choose a valid UTF-8 CSV with properly closed quoted fields.')
    while records and not any(cell.strip() for cell in records[-1]):
        records.pop()
    count = len(records) - 1
    if not 2 <= count <= MAX_UPLOAD_ROWS:
        invalid('ROW_COUNT', 'Provide between 2 and 5,000 hourly data rows. Empty trailing rows are ignored.')
    # Bound decimal syntax before model validation/arithmetic. PostgreSQL numeric
    # and the integer-cent runtime cannot safely consume arbitrary exponents.
    for line, record in enumerate(records[1:], 2):
        for index, cell in enumerate(record):
            header = records[0][index] if index < len(records[0]) else ''
            if header not in ('timestamp', 'repo_sweep_window_open', 'repo_sweep_mature'):
                if not re.fullmatch(r'[+-]?(?:\d{1,16}(?:\.\d{0,12})?|\.\d{1,12})', cell):
                    invalid('VALUE', 'Use a plain decimal with at most 16 integer and 12 fractional digits.', line, header)
    digest = hashlib.sha256(raw).hexdigest()
    source = OrganizerDatasetSource(
        Path(f'upload/sha256/{digest}.csv'), dataset_name='uploaded_organizer', expected_row_count=count)
    dataset = source.load_bytes(raw, ignore_trailing_empty=True)
    # The financial runtime posts integer USD cents; reject sub-cent customer
    # demand rather than silently rounding it. Supplied net-flow diagnostics stay intact.
    for index, observation in enumerate(dataset.observations, 2):
        for field in ('deposits_usd', 'withdrawals_usd'):
            cents = getattr(observation, field) * 100
            if cents != cents.to_integral_value() or cents > 9_007_199_254_740_991:
                invalid('VALUE', 'Customer flows must be exact cents within the safe integer limit.', index, field)
    for field in ('deposits_usd', 'withdrawals_usd'):
        if sum(getattr(row, field) * 100 for row in dataset.observations) > 9_007_199_254_740_991:
            invalid('TOTAL', 'Combined customer flows exceed the safe integer limit.', field=field)
    return dataset


def store_upload(session, raw):
    dataset = validate_upload(raw)
    existing = session.scalar(select(DatasetSource).where(DatasetSource.content_hash == dataset.metadata.content_hash))
    if existing is not None:
        return existing
    return DatasetRepository(session).store(dataset)


class StoredDatasetSource:
    """Use the run's persisted observations for comparisons, never a fallback file."""
    def __init__(self, session, dataset_id):
        self.session, self.dataset_id = session, dataset_id

    def load(self):
        stored = self.session.get(DatasetSource, self.dataset_id)
        if stored is None:
            raise ValueError('Dataset not found.')
        repository = DatasetRepository(self.session)
        observations = repository.observations(self.dataset_id)
        if len(observations) != stored.row_count:
            raise ValueError('Stored dataset observation count differs from its metadata.')
        return OrganizerDataset(
            metadata=DatasetMetadata(**{field: getattr(stored, field) for field in DatasetMetadata.model_fields}),
            validation=DatasetValidation.model_validate(stored.validation_json), observations=observations)
