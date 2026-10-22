#!/usr/bin/env python3
"""Unified developer and agent workflow CLI for ytm-dl.

Provides simple subcommands for linting, formatting, testing, coverage analysis,
branch boundary auditing, and full CI-parity pre-flight checks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_cmd(tool_name: str) -> list[str]:
    """Find CLI binary in active venv, repo venv, PATH, or fallback to sys.executable -m."""
    venv_bin = Path(sys.prefix) / "bin" / tool_name
    if venv_bin.exists():
        return [str(venv_bin)]

    for candidate_dir in (REPO_ROOT / "venv" / "bin", REPO_ROOT / ".venv" / "bin"):
        cand_bin = candidate_dir / tool_name
        if cand_bin.exists():
            return [str(cand_bin)]

    bin_path = shutil.which(tool_name)
    if bin_path:
        return [bin_path]
    return [sys.executable, "-m", tool_name]


COV_TARGETS = [
    "--cov=src",
    "--cov=scripts",
]


def run_step(name: str, cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a subprocess step, echoing the command and checking returncode."""
    print(f"▶ [{name}] {' '.join(str(c) for c in cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=False)
    if res.returncode != 0:
        print(f"❌ {name} FAILED (exit code {res.returncode})\n", flush=True)
        return False
    print(f"✓ {name} PASSED\n", flush=True)
    return True


def cmd_fix(args: argparse.Namespace) -> int:
    """Auto-fix linting, import sorting, and formatting with Ruff."""
    del args
    print("🎨 Auto-fixing linting and formatting with Ruff...\n")
    s1 = run_step("Ruff Check & Fix", [*resolve_cmd("ruff"), "check", "--fix", "."])
    s2 = run_step("Ruff Format", [*resolve_cmd("ruff"), "format", "."])
    return 0 if (s1 and s2) else 1


def cmd_lint(args: argparse.Namespace) -> int:
    """Run Ruff linter and formatter check."""
    del args
    print("🩺 Running Ruff linter and formatter check...\n")
    s1 = run_step("Ruff Lint", [*resolve_cmd("ruff"), "check", "."])
    s2 = run_step("Ruff Format Check", [*resolve_cmd("ruff"), "format", "--check", "."])
    return 0 if (s1 and s2) else 1


def cmd_boundary(args: argparse.Namespace) -> int:
    """Run branch boundary audit."""
    print("🛡️ Running branch boundary audit...\n")
    base_ref = getattr(args, "base_ref", "main")
    cmd = [sys.executable, "scripts/check_boundaries.py", "--base-ref", base_ref]
    if getattr(args, "audit_tree", False):
        cmd = [sys.executable, "scripts/check_boundaries.py", "--audit-tree"]
    return 0 if run_step("Branch Boundary Audit", cmd) else 1


def cmd_test(args: argparse.Namespace, extra_args: list[str] | None = None) -> int:
    """Run pytest suite."""
    del args
    print("🧪 Running pytest test suite...\n")
    cmd = [*resolve_cmd("pytest"), *(extra_args or [])]
    return 0 if run_step("Pytest Execution", cmd) else 1


def cmd_coverage(args: argparse.Namespace) -> int:
    """Run full pytest suite with coverage analysis and XML/Markdown exports."""
    del args
    print("📊 Running full test suite with coverage reporting...\n")
    Path("tmp").mkdir(exist_ok=True)
    cmd = [
        *resolve_cmd("pytest"),
        *COV_TARGETS,
        "--cov-report=term-missing",
        "--cov-report=markdown:tmp/coverage.md",
        "--cov-report=xml:tmp/coverage.xml",
    ]
    return 0 if run_step("Pytest & Coverage", cmd) else 1


def cmd_check(args: argparse.Namespace) -> int:
    """Run complete pre-flight check matching GitHub Actions PR CI."""
    print("🚀 Running complete pre-flight CI check suite...\n")
    base_ref = getattr(args, "base_ref", "main")
    Path("tmp").mkdir(exist_ok=True)

    steps: list[tuple[str, list[str]]] = [
        (
            "Branch Boundary Audit",
            [sys.executable, "scripts/check_boundaries.py", "--base-ref", base_ref],
        ),
        ("Ruff Linter", [*resolve_cmd("ruff"), "check", "."]),
        ("Ruff Formatter", [*resolve_cmd("ruff"), "format", "--check", "."]),
        (
            "Pytest & Coverage",
            [
                *resolve_cmd("pytest"),
                *COV_TARGETS,
                "--cov-report=term-missing",
                "--cov-report=markdown:tmp/coverage.md",
                "--cov-report=xml:tmp/coverage.xml",
            ],
        ),
    ]

    # Add diff-cover if not --fast
    if not getattr(args, "fast", False):
        steps.append(
            (
                "Diff Coverage Gate",
                [
                    *resolve_cmd("diff-cover"),
                    "tmp/coverage.xml",
                    "--compare-branch",
                    f"origin/{base_ref}",
                    "--fail-under",
                    "100",
                ],
            )
        )

    failed: list[str] = []
    for name, cmd in steps:
        if not run_step(name, cmd):
            failed.append(name)
            if not getattr(args, "keep_going", False):
                break

    if failed:
        print("❌ Pre-flight checks failed on:")
        for f in failed:
            print(f"  • {f}")
        print("\n💡 Suggested remediations:")
        print("  - To fix formatting/lint: python scripts/dev.py fix")
        print("  - To run single step: python scripts/dev.py [lint|test|boundary|cov]")
        return 1

    print("✨ All pre-flight checks PASSED! Repository is ready for pull request.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI argument parser and dispatcher."""
    parser = argparse.ArgumentParser(
        description="Unified local developer and agent CLI runner for ytm-dl.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # check
    check_p = subparsers.add_parser(
        "check",
        help="Run full CI pre-flight validation (boundaries, lint, format, pytest, diff-cover)",
    )
    check_p.add_argument("--base-ref", default="main", help="Target base branch to compare against")
    check_p.add_argument("--fast", action="store_true", help="Skip diff-cover execution")
    check_p.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running remaining steps even if one fails",
    )

    # fix
    subparsers.add_parser("fix", help="Auto-fix Ruff lint issues and format files")

    # lint
    subparsers.add_parser("lint", help="Run Ruff linter and format check")

    # boundary
    boundary_p = subparsers.add_parser(
        "boundary", help="Audit branch boundaries (no data or secrets on main)"
    )
    boundary_p.add_argument("--base-ref", default="main", help="Base branch")
    boundary_p.add_argument("--audit-tree", action="store_true", help="Audit entire tracked tree")

    # test
    subparsers.add_parser("test", help="Run pytest suite (supports passthrough args like -k)")

    # cov
    subparsers.add_parser("cov", help="Run pytest with coverage reports")

    args, extra = parser.parse_known_args(argv)

    if not args.command or args.command == "check":
        return cmd_check(args)
    if args.command == "fix":
        return cmd_fix(args)
    if args.command == "lint":
        return cmd_lint(args)
    if args.command == "boundary":
        return cmd_boundary(args)
    if args.command == "test":
        return cmd_test(args, extra)
    if args.command == "cov":
        return cmd_coverage(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
