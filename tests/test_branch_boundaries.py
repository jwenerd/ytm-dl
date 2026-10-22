"""Tests for branch boundary enforcement and repository hygiene."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_boundaries import (
    find_boundary_violations,
    format_violation_report,
    get_changed_files_against_base,
    get_tracked_files,
    is_boundary_violation,
    main,
)


class TestBranchBoundaries:
    """Validate boundary and secret prevention rules defined in AGENTS.md."""

    def test_is_boundary_violation_rules(self) -> None:
        """Verify boundary violation detection for individual filepaths."""
        # Forbidden output/ files
        assert is_boundary_violation("output/history.csv") is True
        assert is_boundary_violation("output/liked_songs.csv") is True
        assert is_boundary_violation("output/reports/daily.md") is True
        assert is_boundary_violation("output/meta/reports.yaml") is True
        assert is_boundary_violation("output/mixes/Energy.csv") is True

        # Allowed output/ placeholder
        assert is_boundary_violation("output/.keep") is False

        # Forbidden credentials and secrets
        assert is_boundary_violation("browser.json") is True
        assert is_boundary_violation("oauth.json") is True
        assert is_boundary_violation(".env") is True
        assert is_boundary_violation("config/.env") is True
        assert is_boundary_violation(".clasprc.json") is True
        assert is_boundary_violation("appscript/.clasprc.json") is True

        # Forbidden artifacts/
        assert is_boundary_violation("artifacts/api_results_123.yaml") is True

        # Raw CSV data committed outside tests/
        assert is_boundary_violation("history.csv") is True
        assert is_boundary_violation("data/export.csv.gz") is True

        # Allowed test fixtures and test files
        assert is_boundary_violation("tests/fixtures/sample.csv") is False
        assert is_boundary_violation("tests/fixtures/history.csv") is False
        assert is_boundary_violation("tests/test_output.py") is False

        # Allowed source code and docs
        assert is_boundary_violation("src/output.py") is False
        assert is_boundary_violation("ytm-dl.py") is False
        assert is_boundary_violation("README.md") is False
        assert is_boundary_violation("pyproject.toml") is False
        assert is_boundary_violation("") is False

    def test_find_boundary_violations(self) -> None:
        """Verify batch filtering of file paths."""
        file_list = [
            "src/api.py",
            "output/history.csv",
            "tests/fixtures/history.csv",
            "browser.json",
            "output/.keep",
        ]
        violations = find_boundary_violations(file_list)
        assert violations == ["output/history.csv", "browser.json"]

    def test_format_violation_report(self) -> None:
        """Verify diagnostic message formatting."""
        report = format_violation_report(["output/history.csv", "browser.json"])
        assert "main-output" in report
        assert "output/history.csv" in report
        assert "browser.json" in report

    def test_current_repo_tree_is_clean(self) -> None:
        """Verify that current repository tree on main contains zero boundary violations."""
        tracked = get_tracked_files()
        assert len(tracked) > 0
        violations = find_boundary_violations(tracked)
        assert violations == [], f"Found branch boundary violations in repo tree: {violations}"

    def test_cli_audit_tree_success(self) -> None:
        """Verify CLI exits 0 on clean tree audit."""
        ret = main(["--audit-tree"])
        assert ret == 0

    def test_cli_violation_fails(self, monkeypatch) -> None:
        """Verify CLI returns exit code 1 when violations are detected."""
        with patch(
            "scripts.check_boundaries.get_changed_files_against_base",
            return_value=["output/history.csv"],
        ):
            ret = main(["--base-ref", "main"])
            assert ret == 1

    def test_cli_step_summary_reporting(self, tmp_path: Path, monkeypatch) -> None:
        """Verify step summary is written when GITHUB_STEP_SUMMARY env var is present."""
        summary_file = tmp_path / "step_summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        # Success case
        with patch(
            "scripts.check_boundaries.get_changed_files_against_base",
            return_value=[],
        ):
            ret = main(["--base-ref", "main"])
            assert ret == 0
            assert summary_file.exists()
            assert "Branch Boundaries" in summary_file.read_text(encoding="utf-8")

        # Failure case
        summary_file.unlink()
        with patch(
            "scripts.check_boundaries.get_changed_files_against_base",
            return_value=["output/reports/daily.md"],
        ):
            ret = main(["--base-ref", "main"])
            assert ret == 1
            content = summary_file.read_text(encoding="utf-8")
            assert "Branch Boundary Violation Detected" in content
            assert "output/reports/daily.md" in content

    def test_get_changed_files_fallback(self) -> None:
        """Verify fallback behavior handles invalid base ref gracefully."""
        files = get_changed_files_against_base("non_existent_branch_xyz_12345")
        assert isinstance(files, list)

    def test_get_changed_files_status_fallback(self) -> None:
        """Verify git status porcelain fallback when git diff fails."""
        mock_diff_fail = patch("subprocess.run")
        with mock_diff_fail as mock_run:
            mock_run.side_effect = [
                Exception("git diff failed"),
                Exception("git diff failed"),
                Exception("git diff failed"),
                type(
                    "Proc",
                    (),
                    {"returncode": 0, "stdout": " M modified.py\n?? untracked.py\n"},
                )(),
            ]
            files = get_changed_files_against_base("main")
            assert files == ["modified.py"]

    def test_get_tracked_files_filesystem_fallback(self, tmp_path: Path) -> None:
        """Verify get_tracked_files falls back to rglob when git ls-files fails."""
        test_file = tmp_path / "foo.py"
        test_file.write_text("print('test')")
        hidden_file = tmp_path / ".hidden" / "bar.py"
        hidden_file.parent.mkdir(parents=True)
        hidden_file.write_text("hidden")

        with patch("subprocess.run", side_effect=Exception("git ls-files failed")):
            files = get_tracked_files(tmp_path)
            assert "foo.py" in files
            assert all(".hidden" not in f for f in files)

    def test_cli_default_args(self) -> None:
        """Verify CLI default args execution."""
        with patch("scripts.check_boundaries.get_changed_files_against_base", return_value=[]):
            ret = main([])
            assert ret == 0

    def test_get_changed_files_complete_failure(self) -> None:
        """Verify get_changed_files returns empty list when git status also throws."""
        with patch("subprocess.run", side_effect=Exception("complete git failure")):
            files = get_changed_files_against_base("main")
            assert files == []
