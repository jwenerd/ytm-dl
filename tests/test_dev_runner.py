"""Unit tests for the unified local developer runner (scripts/dev.py)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.dev import (
    cmd_boundary,
    cmd_check,
    cmd_coverage,
    cmd_fix,
    cmd_lint,
    cmd_test,
    main,
    resolve_cmd,
    run_step,
)


class TestDevRunner:
    """Validate dev.py command execution and routing."""

    def test_resolve_cmd_venv(self) -> None:
        """Verify binary resolution when present in venv."""
        with patch.object(Path, "exists", return_value=True):
            cmd = resolve_cmd("custom-tool")
            assert "custom-tool" in cmd[0]

    def test_resolve_cmd_repo_venv(self) -> None:
        """Verify binary resolution when found in REPO_ROOT/venv/bin."""
        with patch.object(Path, "exists", side_effect=[False, True]):
            cmd = resolve_cmd("repo-tool")
            assert "repo-tool" in cmd[0]
            assert "venv/bin" in cmd[0]

    def test_resolve_cmd_found(self) -> None:
        """Verify binary resolution on PATH when absent from venv."""
        with (
            patch.object(Path, "exists", return_value=False),
            patch("shutil.which", return_value="/usr/bin/custom-tool"),
        ):
            assert resolve_cmd("custom-tool") == ["/usr/bin/custom-tool"]

    def test_resolve_cmd_fallback(self) -> None:
        """Verify fallback to python -m when binary is absent from venv and PATH."""
        with (
            patch.object(Path, "exists", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            cmd = resolve_cmd("custom-tool")
            assert len(cmd) == 3
            assert cmd[1] == "-m"
            assert cmd[2] == "custom-tool"

    def test_run_step_success(self) -> None:
        """Verify run_step returns True on exit code 0."""
        mock_proc = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_proc):
            assert run_step("Test Step", ["echo", "hi"]) is True

    def test_run_step_failure(self) -> None:
        """Verify run_step returns False on non-zero exit code."""
        mock_proc = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_proc):
            assert run_step("Test Step", ["false"]) is False

    def test_cmd_fix_and_lint(self) -> None:
        """Verify cmd_fix and cmd_lint invoke correct steps."""
        with patch("scripts.dev.run_step", return_value=True) as mock_run:
            assert cmd_fix(argparse.Namespace()) == 0
            assert mock_run.call_count == 2

            mock_run.reset_mock()
            assert cmd_lint(argparse.Namespace()) == 0
            assert mock_run.call_count == 2

    def test_cmd_boundary(self) -> None:
        """Verify cmd_boundary passes flags properly."""
        with patch("scripts.dev.run_step", return_value=True) as mock_run:
            args = argparse.Namespace(base_ref="main", audit_tree=False)
            assert cmd_boundary(args) == 0
            assert "--base-ref" in mock_run.call_args[0][1]

            mock_run.reset_mock()
            args_audit = argparse.Namespace(base_ref="main", audit_tree=True)
            assert cmd_boundary(args_audit) == 0
            assert "--audit-tree" in mock_run.call_args[0][1]

    def test_cmd_test_and_cov(self) -> None:
        """Verify test and coverage commands."""
        with patch("scripts.dev.run_step", return_value=True) as mock_run:
            assert cmd_test(argparse.Namespace(), ["-k", "test_prepend"]) == 0
            assert "-k" in mock_run.call_args[0][1]

            mock_run.reset_mock()
            assert cmd_coverage(argparse.Namespace()) == 0
            assert "--cov-report=term-missing" in mock_run.call_args[0][1]

    def test_cmd_check_all_pass(self) -> None:
        """Verify cmd_check runs all steps and returns 0 when all succeed."""
        with patch("scripts.dev.run_step", return_value=True) as mock_run:
            args = argparse.Namespace(base_ref="main", fast=False, keep_going=False)
            assert cmd_check(args) == 0
            assert mock_run.call_count == 5

    def test_cmd_check_failure_stop_early(self) -> None:
        """Verify cmd_check aborts on first failure when keep_going=False."""
        with patch("scripts.dev.run_step", side_effect=[True, False, True]):
            args = argparse.Namespace(base_ref="main", fast=False, keep_going=False)
            assert cmd_check(args) == 1

    def test_cmd_check_failure_keep_going(self) -> None:
        """Verify cmd_check continues when keep_going=True."""
        with patch("scripts.dev.run_step", side_effect=[True, False, True, True, True]) as mock_run:
            args = argparse.Namespace(base_ref="main", fast=False, keep_going=True)
            assert cmd_check(args) == 1
            assert mock_run.call_count == 5

    def test_main_dispatching(self) -> None:
        """Verify CLI dispatch to subcommands."""
        with patch("scripts.dev.cmd_check", return_value=0) as mock_check:
            assert main(["check"]) == 0
            assert mock_check.called

        with patch("scripts.dev.cmd_fix", return_value=0) as mock_fix:
            assert main(["fix"]) == 0
            assert mock_fix.called

        with patch("scripts.dev.cmd_lint", return_value=0) as mock_lint:
            assert main(["lint"]) == 0
            assert mock_lint.called

        with patch("scripts.dev.cmd_boundary", return_value=0) as mock_boundary:
            assert main(["boundary"]) == 0
            assert mock_boundary.called

        with patch("scripts.dev.cmd_test", return_value=0) as mock_test:
            assert main(["test"]) == 0
            assert mock_test.called

        with patch("scripts.dev.cmd_coverage", return_value=0) as mock_cov:
            assert main(["cov"]) == 0
            assert mock_cov.called

        # Unrecognized command fallback
        with (
            patch(
                "argparse.ArgumentParser.parse_known_args",
                return_value=(argparse.Namespace(command="other"), []),
            ),
            patch("argparse.ArgumentParser.print_help") as mock_help,
        ):
            assert main(["other"]) == 0
            assert mock_help.called
