"""Smoke tests for CLI entry points."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vendor_fabric.agentic.main import main


class TestCLIEntryPoint:
    """Smoke tests for the vendor-fabric-agent CLI."""

    def test_no_args_prints_help(self, capsys) -> None:
        """Running with no args should print help text."""
        with patch("sys.argv", ["vendor-fabric-agent"]):
            main()
        captured = capsys.readouterr()
        assert "vendor-fabric-agent" in captured.out.lower() or "usage" in captured.out.lower()

    def test_help_flag(self) -> None:
        """--help should exit 0."""
        with (
            patch("sys.argv", ["vendor-fabric-agent", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

    def test_list_command_with_no_packages(self, tmp_path, capsys) -> None:
        """'list' should work even with no packages found."""
        # Create empty packages dir
        (tmp_path / "packages").mkdir()

        with (
            patch("sys.argv", ["vendor-fabric-agent", "list"]),
            patch(
                "vendor_fabric.agentic.main.discover_packages",
                return_value={},
            ),
            patch(
                "vendor_fabric.agentic.main.list_crews",
                return_value={},
            ),
        ):
            main()

        captured = capsys.readouterr()
        assert "No packages" in captured.out or "crews" in captured.out.lower()

    def test_list_command_json_output(self, capsys) -> None:
        """'list --json' should produce valid JSON."""
        import json

        with (
            patch("sys.argv", ["vendor-fabric-agent", "list", "--json"]),
            patch(
                "vendor_fabric.agentic.main.list_crews",
                return_value={},
            ),
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "crews" in data
        assert isinstance(data["crews"], list)

    def test_run_missing_package_and_crew_exits_2(self) -> None:
        """'run' without package or crew should exit with code 2."""
        with (
            patch("sys.argv", ["vendor-fabric-agent", "run"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 2

    def test_run_nonexistent_package_exits_2(self) -> None:
        """'run' with a non-existent package should exit with code 2."""
        with (
            patch("sys.argv", ["vendor-fabric-agent", "run", "nonexistent", "some_crew", "--input", "test"]),
            patch("vendor_fabric.agentic.main.discover_packages", return_value={}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 2

    def test_info_nonexistent_package_exits_2(self) -> None:
        """'info' with non-existent package should exit with code 2."""
        with (
            patch("sys.argv", ["vendor-fabric-agent", "info", "nonexistent", "some_crew"]),
            patch("vendor_fabric.agentic.main.discover_packages", return_value={}),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 2

    def test_info_nonexistent_crew_exits_2(self, tmp_path) -> None:
        """'info' with non-existent crew should exit with code 2."""
        config_dir = tmp_path / ".crewai"
        config_dir.mkdir()
        (config_dir / "manifest.yaml").write_text("crews: {}\n")

        with (
            patch("sys.argv", ["vendor-fabric-agent", "info", "pkg", "missing_crew"]),
            patch(
                "vendor_fabric.agentic.main.discover_packages",
                return_value={"pkg": config_dir},
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 2


class TestModuleEntryPoint:
    """Test running as python -m vendor_fabric.agentic."""

    def test_module_is_importable(self) -> None:
        """The __main__.py module should be importable."""
        import vendor_fabric.agentic.__main__  # noqa: F401


class TestListRunnersCommand:
    """Smoke tests for list-runners command."""

    def test_list_runners_command(self, capsys) -> None:
        """'list-runners' should execute without error."""
        with patch("sys.argv", ["vendor-fabric-agent", "list-runners"]):
            main()
        captured = capsys.readouterr()
        # Should show some output (either runners or header)
        assert len(captured.out) > 0
