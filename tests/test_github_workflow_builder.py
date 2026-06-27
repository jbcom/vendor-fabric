"""Tests for GitHub workflow builder utility."""

from __future__ import annotations

from unittest.mock import patch

from ruamel.yaml import YAML

from cloud_connectors import github as github_module
from cloud_connectors.github import build_github_actions_workflow


def test_build_github_actions_workflow_generates_yaml():
    jobs = {
        "build": {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"name": "Checkout", "uses": "actions/checkout@v4"},
                {"name": "Run tests", "run": "pytest"},
            ],
        }
    }

    with patch(
        "cloud_connectors.github.wrap_raw_data_for_export",
        wraps=github_module.wrap_raw_data_for_export,
    ) as mock_wrap_for_export:
        workflow_yaml = build_github_actions_workflow(
            workflow_name="CI",
            jobs=jobs,
            concurrency_group="ci-main",
            environment_variables={"FOO": "bar"},
            secrets={"TOKEN": "GITHUB_TOKEN"},
            events={"push": True, "pull_request": False},
            inputs={"run-tests": {"required": False, "type": "boolean", "default": True}},
        )

    parsed = YAML().load(workflow_yaml)

    assert parsed["name"] == "CI"
    assert parsed["concurrency"] == "ci-main"
    assert parsed["env"]["FOO"] == "bar"
    assert parsed["env"]["TOKEN"] == "${{secrets.GITHUB_TOKEN}}"
    assert "workflow_dispatch" in parsed["on"]
    assert parsed["jobs"]["build"]["steps"][1]["run"] == "pytest"
    mock_wrap_for_export.assert_called_once()
    assert mock_wrap_for_export.call_args.kwargs == {"allow_encoding": "yaml"}
