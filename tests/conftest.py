"""Shared test fixtures."""

import pytest

from web_search_mcp.utils import validation


@pytest.fixture(autouse=True)
def offline_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve every hostname to a fixed public IP so tests never touch real DNS.

    IP-literal and localhost checks still run as normal, so the SSRF tests keep
    their meaning.
    """

    monkeypatch.setattr(validation, "_resolved_addresses", lambda _hostname: {"93.184.216.34"})
