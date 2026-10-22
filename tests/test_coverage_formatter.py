"""Unit tests for scoped PR coverage formatter."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.format_pr_coverage import (
    extract_diff_coverage_summary,
    filter_coverage_markdown,
    generate_pr_comment,
    get_changed_files,
    main,
    unescape_markdown,
)

SAMPLE_COVERAGE_MD = """| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| src/api.py                      |      167 |       71 |     57% | 54-55, 67  |
| src/catalog.py                  |       68 |        7 |     90% | 29-30      |
| src/output.py                   |      114 |       17 |     85% | 84-99      |
| scripts/dev.py                  |      103 |        0 |    100% |           |
| scripts/check\\_boundaries.py    |       93 |        0 |    100% |           |
| **TOTAL**                       | **2312** |  **333** | **86%** |           |
"""


class TestCoverageFormatter:
    """Validate scoped PR coverage filtering and reporting."""

    def test_unescape_markdown(self) -> None:
        """Verify markdown escaping characters are removed."""
        assert unescape_markdown(r"scripts/check\_boundaries.py") == "scripts/check_boundaries.py"
        assert unescape_markdown(r"src/file\_name.py") == "src/file_name.py"
        assert unescape_markdown("plain.py") == "plain.py"

    def test_filter_coverage_markdown_with_matches(self) -> None:
        """Verify filtering isolates only changed files."""
        changed = ["src/output.py", "scripts/check_boundaries.py", "README.md"]
        table, total_count = filter_coverage_markdown(SAMPLE_COVERAGE_MD, changed)

        assert total_count == 5
        assert "| `src/output.py` | 114 | 17 | 85% | 84-99 |" in table
        assert "| `scripts/check_boundaries.py` | 93 | 0 | 100% | None |" in table
        assert "src/api.py" not in table
        assert "src/catalog.py" not in table

    def test_filter_coverage_markdown_no_production_matches(self) -> None:
        """Verify message when only docs or tests are modified."""
        changed = ["README.md", ".github/workflows/pr.yml", "tests/test_foo.py"]
        table, total_count = filter_coverage_markdown(SAMPLE_COVERAGE_MD, changed)

        assert total_count == 5
        assert "_No production Python files modified in this PR._" in table

    def test_filter_coverage_markdown_empty_or_malformed(self) -> None:
        """Verify robust handling of empty coverage input."""
        table, total_count = filter_coverage_markdown("", ["foo.py"])
        assert total_count == 0
        assert "_No coverage data available._" in table

    def test_extract_diff_coverage_summary(self, tmp_path: Path) -> None:
        """Verify extraction of diff-cover percentage."""
        # Non-existent file
        assert "100%" in extract_diff_coverage_summary(None)

        # No lines diff
        diff_file = tmp_path / "diff_cov.md"
        diff_file.write_text("No lines with coverage information in this diff.", encoding="utf-8")
        assert "No new executable lines" in extract_diff_coverage_summary(diff_file)

        # Standard diff coverage
        diff_file.write_text("# Diff Coverage\nTotal: 100.0%", encoding="utf-8")
        assert "100.0% diff coverage" in extract_diff_coverage_summary(diff_file)

        # Partial diff coverage
        diff_file.write_text("| Total | 95.5% |", encoding="utf-8")
        assert "95.5% diff coverage" in extract_diff_coverage_summary(diff_file)

        # Fallback pct match
        diff_file.write_text("Report shows 88% overall", encoding="utf-8")
        assert "88% diff coverage" in extract_diff_coverage_summary(diff_file)

        # No percentage found
        diff_file.write_text("Plain text with no numbers", encoding="utf-8")
        assert "100% (Passed)" in extract_diff_coverage_summary(diff_file)

    def test_generate_pr_comment_structure(self, tmp_path: Path) -> None:
        """Verify full comment markdown generation."""
        cov_file = tmp_path / "coverage.md"
        cov_file.write_text(SAMPLE_COVERAGE_MD, encoding="utf-8")

        diff_file = tmp_path / "diff_cov.md"
        diff_file.write_text("Total: 100%", encoding="utf-8")

        with patch("scripts.format_pr_coverage.get_changed_files", return_value=["src/output.py"]):
            comment = generate_pr_comment(
                coverage_md_path=cov_file,
                diff_cover_path=diff_file,
                include_hints=True,
            )

            assert "<!-- pr-coverage-report -->" in comment
            assert "🛡️ **Branch Boundary Guard**" in comment
            assert "🎯 **PR Diff Coverage**" in comment
            assert "#### 📁 Coverage for Files Changed in this PR" in comment
            assert "| `src/output.py` | 114 | 17 | 85% | 84-99 |" in comment
            assert "src/api.py" not in comment.split("<details>")[0]
            assert "💡 Agent Remediation Steps" in comment
            assert "<details>" in comment

    def test_get_changed_files_status_fallback(self) -> None:
        """Verify fallback to git status when git diff fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Exception("diff failed"),
                Exception("diff failed"),
                Exception("diff failed"),
                type(
                    "Proc", (), {"returncode": 0, "stdout": " M src/output.py\n?? scratch.py\n"}
                )(),
            ]
            files = get_changed_files()
            assert files == ["src/output.py"]

    def test_cli_main_execution(self, tmp_path: Path) -> None:
        """Verify CLI main entrypoint writes output file."""
        cov_file = tmp_path / "coverage.md"
        cov_file.write_text(SAMPLE_COVERAGE_MD, encoding="utf-8")
        out_file = tmp_path / "output_comment.md"

        ret = main(["--coverage-md", str(cov_file), "--output", str(out_file)])
        assert ret == 0
        assert out_file.exists()
        assert "### 📊 PR Quality & Test Coverage Report" in out_file.read_text(encoding="utf-8")

    def test_cli_main_stdout(self, tmp_path: Path, capsys) -> None:
        """Verify CLI main entrypoint prints to stdout if no output path provided."""
        cov_file = tmp_path / "coverage.md"
        cov_file.write_text(SAMPLE_COVERAGE_MD, encoding="utf-8")
        ret = main(["--coverage-md", str(cov_file)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "### 📊 PR Quality & Test Coverage Report" in captured.out

    def test_get_changed_files_complete_failure(self) -> None:
        """Verify get_changed_files returns empty list when all git commands fail."""
        with patch("subprocess.run", side_effect=Exception("total git failure")):
            assert get_changed_files() == []
