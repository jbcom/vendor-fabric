"""Tests for Google project activity helpers without Google SDK imports."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from extended_data.containers import ExtendedList, extend_data

from vendor_fabric.google.services import GoogleServicesMixin


class DummyGoogleServices(GoogleServicesMixin):
    """Small concrete test double for GoogleServicesMixin."""

    def __init__(self, empty_projects: set[str]) -> None:
        self.empty_projects = empty_projects
        self.logger = MagicMock()

    def is_project_empty(self, project_id: str) -> bool:
        return project_id in self.empty_projects

    def extend_result(self, value: Any) -> Any:
        return extend_data(value)


def test_find_inactive_projects_uses_activity_threshold_for_empty_projects() -> None:
    """Recently active empty projects are not reported as inactive."""
    connector = DummyGoogleServices({"old", "recent", "unknown"})
    projects: dict[str, dict[str, Any]] = {
        "old": {
            "projectId": "old",
            "lifecycleState": "ACTIVE",
            "updateTime": "2000-01-01T00:00:00Z",
        },
        "recent": {
            "projectId": "recent",
            "lifecycleState": "ACTIVE",
            "updateTime": "2999-01-01T00:00:00Z",
        },
        "unknown": {
            "projectId": "unknown",
            "lifecycleState": "ACTIVE",
        },
    }

    inactive = connector.find_inactive_projects(projects, days_since_activity=90)

    assert isinstance(inactive, ExtendedList)
    assert {project["projectId"] for project in inactive} == {"old", "unknown"}
    assert projects["old"]["inactive_reason"] == "no_resources_since=2000-01-01"
    assert projects["unknown"]["inactive_reason"] == "no_resources"
    assert "inactive_reason" not in projects["recent"]


def test_find_inactive_projects_keeps_non_empty_active_projects() -> None:
    """Active projects with resources are not inactive solely because timestamps are old."""
    connector = DummyGoogleServices(set())
    projects = {
        "active": {
            "projectId": "active",
            "lifecycleState": "ACTIVE",
            "updateTime": "2000-01-01T00:00:00Z",
        }
    }

    assert connector.find_inactive_projects(projects, days_since_activity=90) == []


def test_find_inactive_projects_rejects_negative_activity_threshold() -> None:
    """Negative activity thresholds fail instead of silently widening the query."""
    connector = DummyGoogleServices(set())

    with pytest.raises(ValueError, match="days_since_activity"):
        connector.find_inactive_projects({}, days_since_activity=-1)
