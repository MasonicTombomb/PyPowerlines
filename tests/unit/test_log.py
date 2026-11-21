"""Tests for :mod:`pypowerlines._log`."""

import json
import logging
from pathlib import Path
from typing import Any

import annunciator
import pytest
from annunciator.testing import EventCapture

import pypowerlines
from pypowerlines._log import (
    MESSAGES,
    PROVENANCE,
    ROOT_LOGGER_NAME,
    configure_logging,
    get_logger,
    record_provenance,
    shutdown_logging,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Return the events of a JSON-lines log file."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# -- Catalogue -------------------------------------------------------------------


def test_catalogue_is_registered_under_ppl_prefix() -> None:
    assert MESSAGES.prefix == "PPL"
    assert annunciator.get_catalogue("PPL") is MESSAGES


def test_catalogue_codes_follow_numbering_scheme() -> None:
    # 0001-0099 run, 0100-0199 input, 0200-0299 numerical, 0900-0999 internal.
    allowed = [range(1, 100), range(100, 200), range(200, 300), range(900, 1000)]
    for definition in MESSAGES:
        assert any(definition.number in r for r in allowed), definition.code


def test_every_catalogue_entry_has_cause_and_remedy() -> None:
    for definition in MESSAGES:
        assert definition.cause, definition.code
        assert definition.remedy, definition.code


def test_provenance_code() -> None:
    assert PROVENANCE == "PPL-N-0001"


# -- Loggers ----------------------------------------------------------------------


def test_get_logger_returns_same_named_logger() -> None:
    log = get_logger("pypowerlines.solver")
    assert log.name == "pypowerlines.solver"
    assert get_logger("pypowerlines.solver") is log


def test_library_import_is_silent() -> None:
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)


# -- Configuration -----------------------------------------------------------------


def test_configure_logging_writes_json_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "run.log.jsonl"
    configure_logging("INFO", log_file, console=False)
    get_logger("pypowerlines.test").info("hello", answer=42)
    shutdown_logging()

    events = _read_jsonl(log_file)
    assert len(events) == 1
    assert events[0]["message"] == "hello"
    assert events[0]["fields"] == {"answer": 42}


def test_configure_logging_respects_level(tmp_path: Path) -> None:
    log_file = tmp_path / "run.log.jsonl"
    configure_logging("WARNING", log_file, console=False)
    log = get_logger("pypowerlines.test")
    log.info("dropped")
    log.warning("kept")
    shutdown_logging()

    assert [e["message"] for e in _read_jsonl(log_file)] == ["kept"]


def test_configure_logging_without_file(tmp_path: Path) -> None:
    config = configure_logging(console=False)
    assert config.file is None
    assert config.logger_name == ROOT_LOGGER_NAME


def test_configure_logging_rejects_bad_level() -> None:
    with pytest.raises(annunciator.ConfigurationError):
        configure_logging("LOUD", console=False)


def test_shutdown_logging_is_idempotent() -> None:
    shutdown_logging()
    shutdown_logging()
    assert not annunciator.is_configured()


# -- Provenance ----------------------------------------------------------------------


def test_record_provenance_returns_manifest(annunciator_events: EventCapture) -> None:
    info = {"schema_version": "1.0", "options": {"relaxation": 1.0}}
    manifest = record_provenance(info)

    assert manifest["pypowerlines_version"] == pypowerlines.__version__
    assert manifest["extra"] == info
    assert set(manifest["packages"]) >= {"numpy", "scipy", "pandas", "pydantic", "PyYAML"}
    assert "user" not in manifest  # personal data is not recorded


def test_record_provenance_logs_one_event(annunciator_events: EventCapture) -> None:
    manifest = record_provenance({"schema_version": "1.0"})

    event = annunciator_events.assert_logged(PROVENANCE, count=1)
    assert event.fields["manifest"] == manifest
    assert pypowerlines.__version__ in event.message


def test_record_provenance_does_not_alias_input(annunciator_events: EventCapture) -> None:
    info: dict[str, Any] = {"schema_version": "1.0"}
    manifest = record_provenance(info)
    info["schema_version"] = "changed"
    assert manifest["extra"]["schema_version"] == "1.0"
