"""Offline catalog fixtures; tests never depend on the user's downloaded library."""

from pathlib import Path

from jcc_assistant.lineup.catalog import PortraitCatalog

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_catalog(root=None):
    return PortraitCatalog(root or FIXTURES / "portraits")
