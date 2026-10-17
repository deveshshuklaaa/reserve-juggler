"""Read the authoritative organizer CSV without normalization or resampling.

Organizer CSV -> OrganizerDatasetSource -> validation -> HourlyObservation.
The immutable observations and content identity are inputs for future historical
replay, which is intentionally not implemented here.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Annotated, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


NATIVE_INTERVAL = timedelta(hours=1)
Nonnegative = Annotated[Decimal, Field(ge=0)]
Positive = Annotated[Decimal, Field(gt=0)]
Haircut = Annotated[Decimal, Field(ge=0, le=100)]
NUMERIC_COLUMNS = (
    "deposits_usd", "withdrawals_usd", "net_flow_usd", "tier1_repo_rate_apy",
    "tier2_bond_yield_pct", "tier2_bond_price_index", "tier2_bond_mod_duration",
    "tier3_stock_index_price", "tier3_stock_volatility_pct",
    "tier1_early_redemption_haircut_pct", "tier2_bond_liquidation_haircut_pct",
    "tier3_stock_liquidation_haircut_pct", "emergency_overdraft_penalty_apr_pct",
)


def _exact_difference(left: Decimal, right: Decimal) -> Decimal:
    # Diagnostics must not inherit a caller's low Decimal arithmetic precision.
    with localcontext() as context:
        context.prec = max(1, max(left.adjusted(), right.adjusted()) - min(
            left.as_tuple().exponent, right.as_tuple().exponent
        ) + 3)
        return left - right


def _exact_total(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as context:
        context.prec = max(1, max(v.adjusted() for v in values) - min(
            v.as_tuple().exponent for v in values
        ) + len(str(len(values))) + 3)
        return sum(values, Decimal(0))


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class HourlyObservation(FrozenModel):
    timestamp: datetime
    deposits_usd: Nonnegative
    withdrawals_usd: Nonnegative
    net_flow_usd: Decimal
    repo_sweep_window_open: bool
    repo_sweep_mature: bool
    tier1_repo_rate_apy: Decimal
    tier2_bond_yield_pct: Decimal
    tier2_bond_price_index: Positive
    tier2_bond_mod_duration: Positive
    tier3_stock_index_price: Positive
    tier3_stock_volatility_pct: Nonnegative
    tier1_early_redemption_haircut_pct: Haircut
    tier2_bond_liquidation_haircut_pct: Haircut
    tier3_stock_liquidation_haircut_pct: Haircut
    emergency_overdraft_penalty_apr_pct: Nonnegative

    @field_validator(*NUMERIC_COLUMNS, mode="before")
    @classmethod
    def exact_decimal(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("Source numbers must be decimal strings or Decimal, never floats")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid decimal value") from exc
        if not number.is_finite():
            raise ValueError("Source numbers must be finite")
        return number

    @field_validator("repo_sweep_window_open", "repo_sweep_mature", mode="before")
    @classmethod
    def source_boolean(cls, value):
        if isinstance(value, bool):
            return value
        if value not in ("True", "False"):
            raise ValueError("Source flags must be True or False")
        return value == "True"

    @field_validator("timestamp", mode="before")
    @classmethod
    def source_timestamp(cls, value):
        if isinstance(value, str):
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
                raise ValueError("Expected YYYY-MM-DD HH:MM:SS")
            value = parsed
        if not isinstance(value, datetime) or value.tzinfo is not None:
            raise ValueError("Organizer timestamps have unspecified timezone")
        if value.minute or value.second or value.microsecond:
            raise ValueError("Organizer timestamps must align to an hourly boundary")
        return value

    @property
    def derived_net_flow_usd(self) -> Decimal:
        return _exact_difference(self.deposits_usd, self.withdrawals_usd)

    @property
    def net_flow_residual_usd(self) -> Decimal:
        """Supplied net flow minus deposits-minus-withdrawals; never a correction."""
        return _exact_difference(self.net_flow_usd, self.derived_net_flow_usd)

    @property
    def reconciliation(self) -> Literal["EXACT_MATCH", "ONE_CENT_DIFFERENCE", "OTHER_DIFFERENCE"]:
        residual = self.net_flow_residual_usd
        if residual == 0:
            return "EXACT_MATCH"
        if residual.copy_abs() == Decimal("0.01"):
            return "ONE_CENT_DIFFERENCE"
        return "OTHER_DIFFERENCE"


EXPECTED_COLUMNS = tuple(HourlyObservation.model_fields)


class ValidationIssue(FrozenModel):
    code: str
    row: int | None = None  # CSV line number, including the header
    field: str | None = None
    message: str


class DatasetValidationError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]):
        self.issues = issues
        super().__init__("; ".join(f"{i.code} row={i.row} field={i.field}: {i.message}" for i in issues))


class ReconciliationSummary(FrozenModel):
    exact_matches: int
    one_cent_differences: int
    other_differences: int
    total_residual_usd: Decimal
    max_absolute_residual_usd: Decimal


class DatasetMetadata(FrozenModel):
    dataset_id: str
    dataset_name: str
    source_type: Literal["ORGANIZER_CSV"] = "ORGANIZER_CSV"
    source_path: str
    hash_algorithm: Literal["sha256"] = "sha256"
    content_hash: str
    row_count: int
    first_timestamp: datetime
    last_timestamp: datetime
    native_interval_seconds: Literal[3600] = 3600
    timezone_status: Literal["UNSPECIFIED"] = "UNSPECIFIED"
    validation_status: Literal["VALIDATED", "VALIDATED_WITH_DIAGNOSTICS"]


class DatasetValidation(FrozenModel):
    reconciliation: ReconciliationSummary
    sweep_window_count: int
    maturity_count: int


class OrganizerDataset(FrozenModel):
    metadata: DatasetMetadata
    validation: DatasetValidation
    observations: tuple[HourlyObservation, ...]

    def __len__(self) -> int:
        return len(self.observations)

    def __iter__(self) -> Iterator[HourlyObservation]:
        return iter(self.observations)

    def observation_at(self, index: int) -> HourlyObservation:
        """Zero-based chronological access; an invalid index never wraps around."""
        if not 0 <= index < len(self):
            raise IndexError("Observation index outside dataset")
        return self.observations[index]

    def history_through(self, index: int) -> tuple[HourlyObservation, ...]:
        """Inclusive observed prefix for future replay; does not expose later rows."""
        self.observation_at(index)
        return self.observations[:index + 1]


def _configured_path() -> Path:
    from app.config import settings
    return settings.ORGANIZER_DATASET_PATH


@dataclass(frozen=True)
class OrganizerDatasetSource:
    path: Path = field(default_factory=_configured_path)
    dataset_name: str = "treasury_4tier_dataset"
    expected_row_count: int = 8760

    def __post_init__(self):
        object.__setattr__(self, "path", Path(self.path))
        if self.expected_row_count <= 0:
            raise ValueError("Expected row count must be positive")

    def load(self) -> OrganizerDataset:
        """Validate a single byte snapshot, then expose only immutable observations."""
        path = self.path
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        raw = path.read_bytes()  # read-only, and hash exactly the bytes being parsed
        digest = hashlib.sha256(raw).hexdigest()
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            header = next(reader, [])
            if len(header) != len(EXPECTED_COLUMNS) or set(header) != set(EXPECTED_COLUMNS):
                raise DatasetValidationError((ValidationIssue(
                    code="SCHEMA", message=f"Expected exactly these columns: {EXPECTED_COLUMNS}"
                ),))
            records = [(reader.line_num, row) for row in reader]
        except (UnicodeDecodeError, csv.Error) as exc:
            raise DatasetValidationError((ValidationIssue(code="CSV", message=str(exc)),)) from exc

        issues = []
        if len(records) != self.expected_row_count:
            issues.append(ValidationIssue(code="ROW_COUNT", message=(
                f"Expected {self.expected_row_count} observations; found {len(records)}"
            )))
        observations = []
        seen = set()
        previous = None
        for line, record in records:
            if len(record) != len(header):
                issues.append(ValidationIssue(code="ROW_WIDTH", row=line, message="Malformed CSV row"))
                continue
            try:
                observation = HourlyObservation.model_validate(dict(zip(header, record)))
            except ValidationError as exc:
                issues.extend(ValidationIssue(code="VALUE", row=line, field=str(e["loc"][0]),
                                              message=e["msg"]) for e in exc.errors())
                continue
            timestamp = observation.timestamp
            if timestamp in seen:
                issues.append(ValidationIssue(code="DUPLICATE_TIMESTAMP", row=line,
                                              message=str(timestamp)))
            if previous is not None:
                if timestamp <= previous:
                    issues.append(ValidationIssue(code="TIMESTAMP_ORDER", row=line,
                                                  message="Timestamps must strictly increase"))
                elif timestamp - previous != NATIVE_INTERVAL:
                    issues.append(ValidationIssue(code="HOURLY_GAP", row=line,
                                                  message="Adjacent timestamps must be one hour apart"))
            seen.add(timestamp)
            previous = timestamp
            for flag, hour in (("repo_sweep_window_open", 17), ("repo_sweep_mature", 8)):
                if getattr(observation, flag) != (timestamp.hour == hour):
                    issues.append(ValidationIssue(code="REPO_SCHEDULE", row=line, field=flag,
                                                  message=f"Flag must be true only at {hour:02}:00"))
            observations.append(observation)
        if issues:
            raise DatasetValidationError(tuple(issues))

        observations = tuple(observations)
        residuals = tuple(o.net_flow_residual_usd for o in observations)
        summary = ReconciliationSummary(
            exact_matches=sum(o.reconciliation == "EXACT_MATCH" for o in observations),
            one_cent_differences=sum(o.reconciliation == "ONE_CENT_DIFFERENCE" for o in observations),
            other_differences=sum(o.reconciliation == "OTHER_DIFFERENCE" for o in observations),
            total_residual_usd=_exact_total(residuals),
            max_absolute_residual_usd=max(r.copy_abs() for r in residuals),
        )
        return OrganizerDataset(
            metadata=DatasetMetadata(
                dataset_id=f"{self.dataset_name}:sha256:{digest}", dataset_name=self.dataset_name,
                source_path=self.path.as_posix(), content_hash=digest, row_count=len(observations),
                first_timestamp=observations[0].timestamp, last_timestamp=observations[-1].timestamp,
                validation_status="VALIDATED_WITH_DIAGNOSTICS" if any(residuals) else "VALIDATED",
            ),
            validation=DatasetValidation(
                reconciliation=summary,
                sweep_window_count=sum(o.repo_sweep_window_open for o in observations),
                maturity_count=sum(o.repo_sweep_mature for o in observations),
            ),
            observations=observations,
        )


if __name__ == "__main__":
    dataset = OrganizerDatasetSource().load()
    print(json.dumps({"metadata": dataset.metadata.model_dump(mode="json"),
                      "validation": dataset.validation.model_dump(mode="json")}, indent=2))
