"""Report mailer for YTM-DL listening logs.

Handles reading markdown reports, converting them to inline-styled HTML,
generating local preview files in tmp/, and dispatching email payloads
via the Google Apps Script webhook (GmailApp).
"""

import json
import logging
import os
import re
from datetime import date
from typing import Any

import requests

from src.reports.email_template import markdown_to_email_html
from src.reports.milestones import (
    evaluate_milestones,
    format_major_milestone_subject_tag,
    get_period_milestones,
    read_milestones,
    select_email_almost_there,
    sync_milestones,
)
from src.reports.telemetry import get_cadence_dates
from src.util import write_file

logger = logging.getLogger(__name__)
_REPORT_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _extract_report_date(md_content: str) -> date | None:
    """Extracts the first valid `YYYY-MM-DD` date from the report header lines."""
    for line in md_content.splitlines()[:5]:
        match = _REPORT_DATE_RE.search(line)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                continue
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
        returning unlocked milestones for the report window and compact On Deck targets.
        """
        history_path = os.path.join(self.output_dir, "history.csv")
        if not os.path.isfile(history_path):
            return {}

        sync_milestones(output_dir=self.output_dir)
        store = read_milestones(os.path.join(self.output_dir, "meta", "milestones.yaml"))
        target_date = _extract_report_date(md_content)
        if target_date is None and store["meta"].get("last_history_date"):
            target_date = date.fromisoformat(store["meta"]["last_history_date"])

        period_ms: list[dict[str, Any]] = []
        if target_date is not None and self.cadence in ("daily", "weekly", "monthly"):
            start_date, end_date = get_cadence_dates(self.cadence, target_date)
            period_ms = get_period_milestones(self.output_dir, start_date, end_date)

        _, _, _, almost_there = evaluate_milestones(
            output_dir=self.output_dir,
            reference_date=target_date,
            backfill=False,
        )
        return {
            "milestones": period_ms,
            "almost_there": select_email_almost_there(almost_there),
        }

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
    ) -> dict[str, Any]:
        """
        Renders the HTML report and dispatches it via Google Apps Script webhook.
        If dry_run is True, renders HTML and saves preview without dispatching HTTP request.
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
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=timeout,
        )

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw_response": response.text}

        if not response.ok:
            msg = f"Webhook returned status {response.status_code}: {res_json}"
            raise RuntimeError(msg)

        return {
            "status": "sent",
            "status_code": response.status_code,
            "subject": subject,
            "bytes": len(html_content),
            "response": res_json,
        }
