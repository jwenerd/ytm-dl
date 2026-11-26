"""Report mailer for YTM-DL listening logs.

Handles reading markdown reports, converting them to inline-styled HTML,
generating local preview files in tmp/, and dispatching email payloads
via the Google Apps Script webhook (GmailApp).
"""

import argparse
import json
import logging
import os
import re
import time
from datetime import date
from typing import Any

import requests

from src.reports.email_template import markdown_to_email_html
from src.reports.milestones import (
    detect_obsessions,
    evaluate_milestones,
    format_major_milestone_subject_tag,
    get_period_milestones,
    read_milestones,
    select_email_almost_there,
    sync_milestones,
)
from src.reports.rotator import read_reports_meta
from src.reports.telemetry import get_cadence_dates
from src.util import write_file

logger = logging.getLogger(__name__)
VALID_CADENCES = ("daily", "weekly", "monthly")
_RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
_REPORT_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_REPORT_WEEK_RE = re.compile(r"\b(\d{4})-W(\d{2})\b")
_REPORT_MONTH_RE = re.compile(r"\b(\d{4})-(\d{2})(?!-\d)\b")
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_REPORT_MONTH_NAME_RE = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)


def _parse_period_to_date(text: str) -> date | None:
    """Parses a daily (`YYYY-MM-DD`), ISO week (`YYYY-Www`), or month period into a date."""
    for match in _REPORT_DATE_RE.finditer(text):
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            continue

    for match in _REPORT_WEEK_RE.finditer(text):
        try:
            return date.fromisocalendar(int(match.group(1)), int(match.group(2)), 4)
        except ValueError:
            continue

    for match in _REPORT_MONTH_RE.finditer(text):
        try:
            return date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            continue

    for match in _REPORT_MONTH_NAME_RE.finditer(text):
        month_num = _MONTH_NAMES[match.group(1).lower()]
        return date(int(match.group(2)), month_num, 1)

    return None


def _extract_report_date(md_content: str) -> date | None:
    """Extracts a representative date from daily, weekly, or monthly report header lines."""
    for line in md_content.splitlines()[:5]:
        parsed = _parse_period_to_date(line)
        if parsed is not None:
            return parsed
    return None


class ReportMailer:
    """Separate process and class responsible for HTML generation and email dispatch."""

    def __init__(
        self,
        cadence: str = "daily",
        report_path: str | None = None,
        output_dir: str = "output",
    ):
        self.cadence = cadence.lower()
        self.output_dir = output_dir
        self.report_path = (
            report_path
            if report_path
            else os.path.join(output_dir, "reports", f"{self.cadence}.md")
        )

    def read_markdown(self) -> str:
        """Reads the source markdown report."""
        if not os.path.isfile(self.report_path):
            msg = f"Report file not found: {self.report_path}"
            raise FileNotFoundError(msg)
        with open(self.report_path, encoding="utf-8") as f:
            return f.read()

    def build_milestone_context(self, md_content: str) -> dict[str, Any]:
        """
        Ensures milestones are synced from `history.csv` before generating email output,
        returning period milestones plus On Deck targets (daily) or Obsessions (weekly/monthly).
        """
        history_path = os.path.join(self.output_dir, "history.csv")
        if not os.path.isfile(history_path):
            return {"cadence": self.cadence}

        sync_milestones(output_dir=self.output_dir)
        store = read_milestones(os.path.join(self.output_dir, "meta", "milestones.yaml"))
        target_date = _extract_report_date(md_content)
        if target_date is None:
            reports_meta = read_reports_meta(os.path.join(self.output_dir, "meta", "reports.yaml"))
            last_period = (reports_meta.get(self.cadence) or {}).get("last_period")
            if last_period:
                target_date = _parse_period_to_date(str(last_period))
        if target_date is None and store["meta"].get("last_history_date"):
            target_date = date.fromisoformat(store["meta"]["last_history_date"])

        period_ms: list[dict[str, Any]] = []
        end_date: date | None = None
        if target_date is not None and self.cadence in VALID_CADENCES:
            start_date, end_date = get_cadence_dates(self.cadence, target_date)
            limit = 8 if self.cadence in ("weekly", "monthly") else 6
            period_ms = get_period_milestones(self.output_dir, start_date, end_date, limit=limit)

        if self.cadence == "daily":
            _, _, _, almost_there = evaluate_milestones(
                output_dir=self.output_dir,
                reference_date=target_date,
                backfill=False,
            )
            return {
                "cadence": self.cadence,
                "milestones": period_ms,
                "almost_there": select_email_almost_there(almost_there),
            }

        ctx: dict[str, Any] = {
            "cadence": self.cadence,
            "milestones": period_ms,
        }
        if end_date is not None:
            obs = detect_obsessions(self.output_dir, reference_date=end_date)
            if any(
                obs.get(k)
                for k in ("tracks_on_repeat", "artist_signals", "album_binges", "taste_phases")
            ):
                ctx["obsessions"] = obs
        return ctx

    def extract_subject(
        self,
        md_content: str,
        milestones: list[dict[str, Any]] | None = None,
    ) -> str:
        """Extracts the email subject line from the markdown title with optional milestone tag."""
        base = f"{self.cadence.capitalize()} Listening Log"
        for line in md_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                clean_title = re.sub(r"[*_`]", "", title)
                clean_title = re.sub(
                    r"[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]+", "", clean_title
                )
                clean_title = re.sub(r"^[\W_]+", "", clean_title).strip()
                if clean_title:
                    base = clean_title
                break
        tag = format_major_milestone_subject_tag(milestones or [])
        return f"{base} {tag}" if tag else base

    def render_html(
        self,
        save_preview: bool = True,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """
        Renders the markdown report into standalone, responsive HTML.
        Saves a local preview copy in tmp/ (never in output/ to avoid committing).
        Returns (html_content, preview_path).
        """
        md_content = self.read_markdown()
        effective_ctx = self.build_milestone_context(md_content) if context is None else context
        html_content = markdown_to_email_html(md_content, context=effective_ctx or None)

        preview_path = os.path.join("tmp", f"email_preview_{self.cadence}.html")
        if save_preview:
            try:
                write_file(preview_path, html_content)
                logger.info("Saved local email preview to %s", preview_path)
            except Exception as e:
                logger.warning("Could not save preview file %s: %s", preview_path, e)

        return html_content, preview_path

    def send(
        self,
        webhook_url: str | None = None,
        recipient: str | None = None,
        dry_run: bool = False,
        timeout: int = 30,
        max_retries: int = 2,
        retry_backoff: float = 1.0,
    ) -> dict[str, Any]:
        """
        Renders the HTML report and dispatches it via Google Apps Script webhook.
        Retries transient network errors and 429/5xx responses before failing.
        """
        md_content = self.read_markdown()
        ctx = self.build_milestone_context(md_content)
        subject = self.extract_subject(md_content, milestones=ctx.get("milestones"))
        html_content, preview_path = self.render_html(save_preview=True, context=ctx)

        if dry_run:
            logger.info("Dry-run email render complete. Subject: %s", subject)
            return {
                "status": "dry_run",
                "cadence": self.cadence,
                "subject": subject,
                "bytes": len(html_content),
                "preview_path": preview_path,
            }

        url = webhook_url or os.environ.get("YTM_SHEET_UPDATE_URL")
        if not url:
            msg = "Missing webhook URL. Set YTM_SHEET_UPDATE_URL or pass webhook_url."
            raise ValueError(msg)

        payload: dict[str, Any] = {
            "action": "send_email",
            "cadence": self.cadence,
            "subject": subject,
            "html_body": html_content,
        }
        if recipient:
            payload["recipient"] = recipient

        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = json.dumps(payload)
        attempts = max(0, max_retries) + 1

        for attempt in range(attempts):
            try:
                response = requests.post(url, data=body, headers=headers, timeout=timeout)
            except requests.RequestException as exc:
                if attempt + 1 >= attempts:
                    raise
                logger.warning(
                    "Webhook request failed (%s); retrying (%d/%d)...",
                    exc,
                    attempt + 1,
                    attempts - 1,
                )
                time.sleep(retry_backoff * (attempt + 1))
                continue

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt + 1 < attempts:
                logger.warning(
                    "Webhook returned %d; retrying (%d/%d)...",
                    response.status_code,
                    attempt + 1,
                    attempts - 1,
                )
                time.sleep(retry_backoff * (attempt + 1))
                continue
            break

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw_response": response.text}

        if not response.ok:
            msg = f"Webhook returned status {response.status_code}: {res_json}"
            raise RuntimeError(msg)

        return {
            "status": "sent",
            "cadence": self.cadence,
            "status_code": response.status_code,
            "subject": subject,
            "bytes": len(html_content),
            "response": res_json,
        }


def load_generated_cadences(
    path: str = os.path.join("tmp", "reports_generated.txt"),
) -> list[str]:
    """Reads generated cadences from `tmp/reports_generated.txt` in canonical order."""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        found = {line.strip().lower() for line in f if line.strip()}
    return [cad for cad in VALID_CADENCES if cad in found]


def dispatch_report_emails(
    cadences: list[str],
    output_dir: str = "output",
    webhook_url: str | None = None,
    recipient: str | None = None,
    dry_run: bool = False,
    delay_seconds: float = 1.5,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """
    Dispatches report emails sequentially for requested cadences.
    Expands `'all'`, deduplicates in canonical order, and isolates per-cadence failures.
    """
    expanded: list[str] = []
    for raw in cadences:
        cad = raw.strip().lower()
        if cad == "all":
            expanded.extend(VALID_CADENCES)
        elif cad in VALID_CADENCES:
            expanded.append(cad)
        else:
            msg = f"Unknown cadence: {raw!r}. Expected daily, weekly, monthly, or all."
            raise ValueError(msg)

    ordered = [cad for cad in VALID_CADENCES if cad in set(expanded)]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for idx, cad in enumerate(ordered):
        if idx > 0 and not dry_run and delay_seconds > 0:
            time.sleep(delay_seconds)
        mailer = ReportMailer(cadence=cad, output_dir=output_dir)
        try:
            res = mailer.send(
                webhook_url=webhook_url,
                recipient=recipient,
                dry_run=dry_run,
            )
            results.append(res)
        except Exception as exc:
            logger.error("Failed to dispatch %s report email: %s", cad, exc)
            errors.append({"cadence": cad, "error": str(exc)})

    return results, errors


def run_mail_cli(argv: list[str] | None = None) -> dict[str, Any]:
    """CLI entrypoint for `python ytm-dl.py mail`."""
    parser = argparse.ArgumentParser(prog="ytm-dl.py mail")
    parser.add_argument(
        "cadences",
        nargs="*",
        help="Cadences to mail (daily, weekly, monthly, all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render HTML previews without sending",
    )
    parser.add_argument(
        "--generated",
        action="store_true",
        help="Dispatch cadences listed in --generated-file",
    )
    parser.add_argument(
        "--generated-file",
        default=os.path.join("tmp", "reports_generated.txt"),
        help="Path to newline-delimited generated cadences file",
    )
    parser.add_argument("--output-dir", default="output", help="Base output directory")
    args = parser.parse_args(argv)

    if args.generated:
        target_cadences = load_generated_cadences(args.generated_file)
        if not target_cadences:
            print("ℹ No generated reports to email.")
            return {"sent": [], "errors": []}
    else:
        target_cadences = args.cadences or ["daily"]

    try:
        results, errors = dispatch_report_emails(
            target_cadences,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"✗ Mailer error: {exc}")
        raise SystemExit(1) from exc

    for res in results:
        print(f"✓ Mailer result ({res['cadence']}): {res}")
    for err in errors:
        print(f"✗ Mailer error ({err['cadence']}): {err['error']}")

    if errors:
        raise SystemExit(1)

    return {"sent": results, "errors": errors}
