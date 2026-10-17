"""Store/retrieve caller-supplied records; caller owns the transaction.

No method posts a cash movement, chooses a trade, accrues interest, or computes
valuation/P&L. flush() checks constraints; only the caller may commit/rollback.
"""

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.data.organizer import EXPECTED_COLUMNS, DatasetMetadata, HourlyObservation, OrganizerDataset
from app.persistence.models import DatasetSource, OrganizerObservation, SimulationRun


def configuration_identity(configuration: dict) -> str:
    canonical = json.dumps(configuration, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class DatasetRepository:
    def __init__(self, session):
        self.session = session

    def store(self, dataset: OrganizerDataset) -> DatasetSource:
        """Insert an immutable validated snapshot, safely repeatable by dataset ID."""
        values = dataset.metadata.model_dump()
        values["validation_json"] = dataset.validation.model_dump(mode="json")
        self.session.execute(insert(DatasetSource).values(**values).on_conflict_do_nothing())
        stored = self.session.get(DatasetSource, dataset.metadata.dataset_id)
        if stored is None or any(getattr(stored, key) != value for key, value in values.items()):
            raise ValueError("Dataset identity already exists with different metadata")
        rows = [dict(row.model_dump(), dataset_id=stored.dataset_id) for row in dataset]
        for offset in range(0, len(rows), 500):
            self.session.execute(insert(OrganizerObservation).on_conflict_do_nothing(), rows[offset:offset + 500])
        count = self.session.scalar(select(func.count()).select_from(OrganizerObservation).where(
            OrganizerObservation.dataset_id == stored.dataset_id
        ))
        if count != dataset.metadata.row_count:
            raise ValueError("Persisted observation count differs from dataset metadata")
        if self.observations(stored.dataset_id) != dataset.observations:
            raise ValueError("Persisted observations differ from the immutable source snapshot")
        return stored

    def metadata(self, dataset_id: str) -> DatasetMetadata | None:
        stored = self.session.get(DatasetSource, dataset_id)
        if stored is None:
            return None
        return DatasetMetadata(**{name: getattr(stored, name) for name in DatasetMetadata.model_fields})

    def observations(self, dataset_id: str, *, through=None) -> tuple[HourlyObservation, ...]:
        query = select(OrganizerObservation).where(OrganizerObservation.dataset_id == dataset_id)
        if through is not None:
            query = query.where(OrganizerObservation.timestamp <= through)
        rows = self.session.scalars(query.order_by(OrganizerObservation.timestamp))
        return tuple(HourlyObservation(**{name: getattr(row, name) for name in EXPECTED_COLUMNS}) for row in rows)


class RunRepository:
    def __init__(self, session):
        self.session = session

    def add(self, run: SimulationRun) -> SimulationRun:
        if run.source_type not in ("ORGANIZER_HISTORICAL", "SYNTHETIC"):
            raise ValueError("New runs require an explicit source type")
        if run.configuration_hash != configuration_identity(run.policy_json):
            raise ValueError("Configuration hash does not identify policy_json")
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id):
        return self.session.get(SimulationRun, run_id)


class RunScopedRepository:
    def __init__(self, session, model):
        if not hasattr(model, "run_id"):
            raise TypeError("A run-scoped persistence model is required")
        self.session = session
        self.model = model

    def add(self, record):
        if not isinstance(record, self.model):
            raise TypeError("Record does not match repository model")
        run = self.session.get(SimulationRun, record.run_id)
        if run is None or run.source_type is None or record.source_type != run.source_type:
            raise ValueError("Record must identify its owning run and source type")
        if record.dataset_id != run.dataset_id:
            raise ValueError("Record source dataset differs from its owning run")
        if run.source_type == "ORGANIZER_HISTORICAL":
            if record.source_observation_timestamp is None:
                raise ValueError("Historical records require an organizer observation")
            if hasattr(record, "timestamp") and record.timestamp is not None:
                raise ValueError("Do not populate a legacy timezone-aware timestamp from organizer time")
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, run_id, record_id):
        return self.session.scalar(select(self.model).where(
            self.model.run_id == run_id, self.model.id == record_id
        ))

    def list_for_run(self, run_id):
        return tuple(self.session.scalars(select(self.model).where(
            self.model.run_id == run_id
        ).order_by(self.model.id)))
