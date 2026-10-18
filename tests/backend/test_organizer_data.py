"""Source-contract tests, independent of forecasting, databases, or trading."""

import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.data.organizer import (
    EXPECTED_COLUMNS, NUMERIC_COLUMNS, DatasetValidationError,
    HourlyObservation, OrganizerDatasetSource,
)


SOURCE = Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv"


@pytest.fixture(scope="module")
def raw_rows():
    return list(csv.DictReader(io.StringIO(SOURCE.read_text(encoding="utf-8-sig"))))


@pytest.fixture(scope="module")
def dataset():
    return OrganizerDatasetSource(SOURCE).load()


@pytest.fixture
def write_source(tmp_path, raw_rows):
    def write(rows=None, columns=EXPECTED_COLUMNS, expected_count=None):
        rows = rows if rows is not None else [dict(r) for r in raw_rows[:2]]
        path = tmp_path / "organizer.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows([row.get(c, "") for c in columns] for row in rows)
        return OrganizerDatasetSource(path, expected_row_count=(
            len(rows) if expected_count is None else expected_count
        ))
    return write


def test_official_schema_and_all_rows(dataset, raw_rows):
    assert len(EXPECTED_COLUMNS) == 16
    assert tuple(raw_rows[0]) == EXPECTED_COLUMNS
    assert len(dataset) == dataset.metadata.row_count == len(raw_rows) == 8760
    # Check every numeric source cell, not just example values or averages.
    for actual, source in zip(dataset, raw_rows):
        for column in NUMERIC_COLUMNS:
            value = getattr(actual, column)
            assert isinstance(value, Decimal)
            assert value.is_finite()
            assert value.as_tuple() == Decimal(source[column]).as_tuple()
        assert actual.timestamp == datetime.strptime(source["timestamp"], "%Y-%m-%d %H:%M:%S")
        assert actual.repo_sweep_window_open == (source["repo_sweep_window_open"] == "True")
        assert actual.repo_sweep_mature == (source["repo_sweep_mature"] == "True")


def test_official_time_and_deterministic_access(dataset):
    times = [row.timestamp for row in dataset]
    assert times[0] == dataset.metadata.first_timestamp == datetime(2026, 1, 1)
    assert times[-1] == dataset.metadata.last_timestamp == datetime(2026, 12, 31, 23)
    assert all(t.tzinfo is None for t in times)
    assert all(b - a == timedelta(hours=1) for a, b in zip(times, times[1:]))
    assert len(set(times)) == len(times)
    assert dataset.metadata.native_interval_seconds == 3600
    assert dataset.metadata.timezone_status == "UNSPECIFIED"
    assert dataset.observation_at(12) == dataset.observations[12]
    assert dataset.history_through(12) == dataset.observations[:13]
    for index in (-1, len(dataset)):
        with pytest.raises(IndexError):
            dataset.observation_at(index)
        with pytest.raises(IndexError):
            dataset.history_through(index)


def test_official_reconciliation_is_measured_and_source_is_preserved(dataset, raw_rows):
    residuals = [Decimal(r["net_flow_usd"]) - (
        Decimal(r["deposits_usd"]) - Decimal(r["withdrawals_usd"])
    ) for r in raw_rows]
    report = dataset.validation.reconciliation
    assert report.exact_matches == sum(r == 0 for r in residuals) == 6642
    assert report.one_cent_differences == sum(abs(r) == Decimal("0.01") for r in residuals) == 2118
    assert report.other_differences == sum(r != 0 and abs(r) != Decimal("0.01") for r in residuals) == 0
    assert report.total_residual_usd == sum(residuals) == Decimal("0.10")
    assert report.max_absolute_residual_usd == max(map(abs, residuals)) == Decimal("0.01")
    mismatch = dataset.observation_at(14)
    assert mismatch.net_flow_usd == Decimal(raw_rows[14]["net_flow_usd"]) == Decimal("165091.77")
    assert mismatch.derived_net_flow_usd == Decimal("165091.78")
    assert mismatch.net_flow_residual_usd == Decimal("-0.01")
    assert mismatch.reconciliation == "ONE_CENT_DIFFERENCE"
    assert dataset.observation_at(0).net_flow_usd < 0


def test_official_repo_schedule(dataset):
    assert dataset.validation.sweep_window_count == sum(
        r.timestamp.hour == 17 for r in dataset
    ) == 365
    assert dataset.validation.maturity_count == sum(r.timestamp.hour == 8 for r in dataset) == 365
    assert all(r.repo_sweep_window_open == (r.timestamp.hour == 17) for r in dataset)
    assert all(r.repo_sweep_mature == (r.timestamp.hour == 8) for r in dataset)


def test_provenance_reproducibility_and_no_source_writes(dataset):
    original = SOURCE.read_bytes()
    modified_time = SOURCE.stat().st_mtime_ns
    reloaded = OrganizerDatasetSource(SOURCE).load()
    assert reloaded == dataset
    assert reloaded.metadata.content_hash == hashlib.sha256(original).hexdigest()
    assert reloaded.metadata.dataset_id.endswith(reloaded.metadata.content_hash)
    assert reloaded.metadata.source_type == "ORGANIZER_CSV"
    assert reloaded.metadata.validation_status == "VALIDATED_WITH_DIAGNOSTICS"
    assert SOURCE.read_bytes() == original
    assert SOURCE.stat().st_mtime_ns == modified_time


def test_frozen_records_and_metadata(dataset):
    for obj, attribute, value in (
        (dataset.observation_at(0), "net_flow_usd", Decimal(0)),
        (dataset.metadata, "row_count", 1), (dataset, "observations", ()),
        (dataset.validation, "sweep_window_count", 0),
    ):
        with pytest.raises(ValidationError):
            setattr(obj, attribute, value)
    assert isinstance(dataset.observations, tuple)


def test_relative_path_ignores_working_directory(monkeypatch, tmp_path, dataset):
    monkeypatch.chdir(tmp_path)
    result = OrganizerDatasetSource(Path("treasury_4tier_dataset.csv")).load()
    assert result.metadata.content_hash == dataset.metadata.content_hash
    assert result.metadata.source_path == "treasury_4tier_dataset.csv"


def test_environment_configuration(monkeypatch, tmp_path):
    path = tmp_path / "external.csv"
    monkeypatch.setenv("ORGANIZER_DATASET_PATH", str(path))
    configured = Settings(_env_file=None)
    monkeypatch.setattr("app.config.settings", configured)
    assert OrganizerDatasetSource().path == path
    with pytest.raises(FileNotFoundError):
        OrganizerDatasetSource().load()  # never falls back to synthetic data


def test_fractional_bps_and_high_precision_are_preserved(raw_rows):
    row = dict(raw_rows[0], tier1_repo_rate_apy="4.29200000000000000000000000000000001")
    observation = HourlyObservation.model_validate(row)
    assert observation.tier1_repo_rate_apy.as_tuple() == Decimal(row["tier1_repo_rate_apy"]).as_tuple()
    assert HourlyObservation.model_validate(raw_rows[0]).tier1_repo_rate_apy * 100 == Decimal("429.2")
    assert observation.tier2_bond_price_index == Decimal(raw_rows[0]["tier2_bond_price_index"])


@pytest.mark.parametrize("field", NUMERIC_COLUMNS)
@pytest.mark.parametrize("value", ["", "not-a-number", "NaN", "Infinity", "-Infinity", 4.292])
def test_invalid_source_numbers(field, value, raw_rows):
    with pytest.raises(ValidationError):
        HourlyObservation.model_validate(dict(raw_rows[0], **{field: value}))


@pytest.mark.parametrize("field,value", [
    ("deposits_usd", "-1"), ("withdrawals_usd", "-1"),
    ("tier2_bond_price_index", "0"), ("tier3_stock_index_price", "-1"),
    ("tier2_bond_mod_duration", "0"), ("tier3_stock_volatility_pct", "-1"),
    ("tier1_early_redemption_haircut_pct", "-1"),
    ("tier2_bond_liquidation_haircut_pct", "100.01"),
    ("tier3_stock_liquidation_haircut_pct", "-1"),
    ("emergency_overdraft_penalty_apr_pct", "-1"),
])
def test_invalid_financial_domains(field, value, raw_rows):
    with pytest.raises(ValidationError):
        HourlyObservation.model_validate(dict(raw_rows[0], **{field: value}))


@pytest.mark.parametrize("timestamp", [
    "invalid", "2026-02-30 00:00:00", "2026-01-01 00:15:00",
    "2026-01-01T00:00:00Z", datetime(2026, 1, 1, tzinfo=timezone.utc),
])
def test_invalid_or_reinterpreted_timestamps(timestamp, raw_rows):
    with pytest.raises(ValidationError):
        HourlyObservation.model_validate(dict(raw_rows[0], timestamp=timestamp))


@pytest.mark.parametrize("flag", ["repo_sweep_window_open", "repo_sweep_mature"])
@pytest.mark.parametrize("value", ["1", "FALSE", "", "yes"])
def test_invalid_boolean_flags(flag, value, raw_rows):
    with pytest.raises(ValidationError):
        HourlyObservation.model_validate(dict(raw_rows[0], **{flag: value}))


@pytest.mark.parametrize("columns", [
    EXPECTED_COLUMNS[:-1], EXPECTED_COLUMNS + ("unexpected",),
    EXPECTED_COLUMNS[:-1] + (EXPECTED_COLUMNS[0],),
])
def test_missing_extra_and_duplicate_columns(columns, write_source):
    with pytest.raises(DatasetValidationError) as error:
        write_source(columns=columns).load()
    assert error.value.issues[0].code == "SCHEMA"


@pytest.mark.parametrize("change,code", [
    ("duplicate", "DUPLICATE_TIMESTAMP"), ("unsorted", "TIMESTAMP_ORDER"),
    ("gap", "HOURLY_GAP"), ("wrong_count", "ROW_COUNT"),
    ("sweep", "REPO_SCHEDULE"), ("maturity", "REPO_SCHEDULE"),
    ("missing_sweep", "REPO_SCHEDULE"), ("missing_maturity", "REPO_SCHEDULE"),
    ("invalid_value", "VALUE"),
])
def test_dataset_validation_rejects_invalid_records(change, code, write_source, raw_rows):
    rows = [dict(r) for r in raw_rows[:24]]
    if change == "duplicate":
        rows[1]["timestamp"] = rows[0]["timestamp"]
    elif change == "unsorted":
        rows[0], rows[1] = rows[1], rows[0]
    elif change == "gap":
        rows.pop(2)
    elif change in ("sweep", "maturity"):
        rows[0]["repo_sweep_window_open" if change == "sweep" else "repo_sweep_mature"] = "True"
    elif change == "missing_sweep":
        rows[17]["repo_sweep_window_open"] = "False"
    elif change == "missing_maturity":
        rows[8]["repo_sweep_mature"] = "False"
    elif change == "invalid_value":
        rows[0]["deposits_usd"] = "NaN"
    source = write_source(rows, expected_count=25 if change == "wrong_count" else len(rows))
    with pytest.raises(DatasetValidationError) as error:
        source.load()
    assert code in {issue.code for issue in error.value.issues}


@pytest.mark.parametrize("bad_row,code", [("a,b\n", "ROW_WIDTH"), ('\"unclosed', "CSV")])
def test_malformed_csv_rows(bad_row, code, write_source):
    source = write_source()
    with source.path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(bad_row)
    with pytest.raises(DatasetValidationError) as error:
        source.load()
    assert code in {issue.code for issue in error.value.issues}


def test_reconciliation_diagnostics_do_not_correct_or_reject_source(write_source, raw_rows):
    rows = [dict(raw_rows[0], deposits_usd="1.00", withdrawals_usd="2.00", net_flow_usd=value)
            for value in ("-1.00", "-0.99", "-0.98")]
    for i, row in enumerate(rows):
        row["timestamp"] = f"2026-01-01 {i:02}:00:00"
    result = write_source(rows).load()
    assert [r.reconciliation for r in result] == [
        "EXACT_MATCH", "ONE_CENT_DIFFERENCE", "OTHER_DIFFERENCE"
    ]
    assert [r.net_flow_usd for r in result] == [Decimal(r["net_flow_usd"]) for r in rows]
    assert result.validation.reconciliation.other_differences == 1
    assert result.metadata.validation_status == "VALIDATED_WITH_DIAGNOSTICS"


def test_content_hash_changes_when_bytes_change(write_source):
    source = write_source()
    first = source.load()
    source.path.write_bytes(source.path.read_bytes().replace(b"4.292", b"4.293", 1))
    second = source.load()
    assert first.metadata.content_hash != second.metadata.content_hash
    assert first.metadata.dataset_id != second.metadata.dataset_id


def test_exact_diagnostics_under_low_decimal_context(raw_rows):
    row = dict(raw_rows[0], deposits_usd="123456789.123456789", withdrawals_usd="0.000000001",
               net_flow_usd="123456789.123456788")
    with localcontext() as context:
        context.prec = 3
        observation = HourlyObservation.model_validate(row)
        assert observation.derived_net_flow_usd == Decimal("123456789.123456788")
        assert observation.net_flow_residual_usd == 0
        assert observation.reconciliation == "EXACT_MATCH"
