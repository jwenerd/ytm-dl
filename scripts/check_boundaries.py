#!/usr/bin/env python3
"""Branch boundary and credential safety enforcement.

Guarantees adherence to AGENTS.md:
'Never commit output CSVs, reports, API artifacts, or credentials to main.
main-output is the designated target branch for datasets in output/.'
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ALLOWED_OUTPUT_FILES = {"output/.keep"}
DATA_EXTENSIONS = (".csv", ".csv.gz")
ALLOWED_DATA_PREFIXES = ("tests/", "tests\\")
CREDENTIAL_FILES = {"browser.json", "oauth.json", ".env", ".clasprc.json"}


def is_boundary_violation(filepath: str) -> bool:
    """Return True if filepath represents a forbidden data/secret file on main."""
    norm_path = filepath.strip().replace("\\", "/")
    if not norm_path:
        return False

    basename = norm_path.split("/")[-1]

    # Check 1: Sensitive credential files
    if basename in CREDENTIAL_FILES or norm_path in CREDENTIAL_FILES:
        return True

    # Check 2: Any file inside output/ except output/.keep
    if norm_path.startswith("output/") and norm_path not in ALLOWED_OUTPUT_FILES:
        return True

    # Check 3: Any file inside artifacts/
    if norm_path.startswith("artifacts/"):
        return True

    # Check 4: Any CSV data files outside tests/
    return bool(
        any(norm_path.endswith(ext) for ext in DATA_EXTENSIONS)
        and not norm_path.startswith(ALLOWED_DATA_PREFIXES)
    )


def find_boundary_violations(files: Iterable[str]) -> list[str]:
    """Filter an iterable of filepaths and return only those that violate branch boundaries."""
    return [f for f in files if is_boundary_violation(f)]


def get_changed_files_against_base(
    base_ref: str = "main", repo_root: Path | None = None
) -> list[str]:
    """Retrieve list of modified/added files in the current branch against base branch."""
    cwd = repo_root or Path.cwd()
    candidates = [f"origin/{base_ref}...HEAD", f"{base_ref}...HEAD", "HEAD~1...HEAD"]

    for ref_spec in candidates:
        try:
            res = subprocess.run(
                ["git", "diff", "--name-only", ref_spec],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            continue

    # Fallback to git status if diffing fails
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return [
                line[3:].strip()
                for line in res.stdout.splitlines()
                if len(line) > 3 and not line.startswith("??")
            ]
    except Exception:
        pass
    return []


def get_tracked_files(repo_root: Path | None = None) -> list[str]:
    """Retrieve all tracked files in the repository using git ls-files."""
    cwd = repo_root or Path.cwd()
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass

    # Filesystem fallback
    tracked = []
    for path in cwd.rglob("*"):
        if path.is_file() and not any(part.startswith(".") for part in path.parts):
            tracked.append(str(path.relative_to(cwd)).replace("\\", "/"))
    return tracked


def format_violation_report(violations: list[str]) -> str:
    """Format human- and agent-readable violation diagnostics."""
    lines = [
        "🛑 ===================================================================",
        "🛑 BRANCH BOUNDARY OR SECRET LEAK VIOLATION DETECTED",
        "🛑 ===================================================================",
        "",
        "According to AGENTS.md:",
        "  'Never commit output CSVs, reports, API artifacts, or credentials to main.",
        "   main-output is the designated target branch for output datasets.'",
        "",
        f"Detected {len(violations)} forbidden file(s) targeted for main:",
    ]
    for v in violations:
        lines.append(f"  ❌ {v}")
    lines.extend(
        [
            "",
            "How to resolve:",
            "  1. Remove forbidden data files: git rm --cached <file>",
            "  2. YTM datasets belong exclusively on the 'main-output' branch.",
            "  3. API artifacts and tokens (browser.json/oauth.json) must never be committed.",
            "  4. Test fixtures must reside in 'tests/'.",
            "===================================================================",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for boundary checking."""
    parser = argparse.ArgumentParser(
        description="Verify branch boundaries (no YTM data, output/, artifacts/, or secrets on main)."
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Target base branch to diff against (e.g. main). If set, checks git diff.",
    )
    parser.add_argument(
        "--audit-tree",
        action="store_true",
        help="Audit all tracked files in the repository tree instead of just changed files.",
    )
    parser.add_argument(
        "--repo-dir",
        default=None,
        help="Path to repository root (defaults to current working directory).",
    )

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_dir).resolve() if args.repo_dir else Path.cwd()

    if args.audit_tree:
        files_to_check = get_tracked_files(repo_root)
    elif args.base_ref:
        files_to_check = get_changed_files_against_base(args.base_ref, repo_root)
    else:
        changed = get_changed_files_against_base("main", repo_root)
        files_to_check = changed if changed else get_tracked_files(repo_root)

    violations = find_boundary_violations(files_to_check)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if violations:
        report = format_violation_report(violations)
        print(report, file=sys.stderr)

        if step_summary_path:
            with Path(step_summary_path).open("a", encoding="utf-8") as f:
                f.write("\n### 🛑 Branch Boundary Violation Detected\n\n")
                f.write(
                    "> **AGENTS.md Policy Violation:** Forbidden output data, artifacts, or secrets detected.\n\n"
                )
                f.write("| Violating File |\n| :--- |\n")
                for v in violations:
                    f.write(f"| `❌ {v}` |\n")
                f.write("\n")
        return 1

    print("✅ Branch boundaries verified: No output data, artifacts, or secrets detected on main.")
    if step_summary_path:
        with Path(step_summary_path).open("a", encoding="utf-8") as f:
            f.write(
                "\n✅ **Branch Boundaries:** Clean (no data files, artifacts, or secrets on `main`)\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
