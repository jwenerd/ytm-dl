"""Report mailer for YTM-DL listening logs.

Handles reading markdown reports, converting them to inline-styled HTML,
generating local preview files in tmp/, and dispatching email payloads
via the Google Apps Script webhook (GmailApp).
"""

import json
import logging
import os
import re
from typing import Any

import requests

from src.reports.email_template import markdown_to_email_html
from src.util import write_file

logger = logging.getLogger(__name__)


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

    def extract_subject(self, md_content: str) -> str:
        """Extracts the email subject line from the markdown title."""
        for line in md_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                # Clean markdown characters from title if any
                return re.sub(r"[*_`]", "", title)
        return f"🎧 {self.cadence.capitalize()} Listening Log"

    def render_html(self, save_preview: bool = True) -> tuple[str, str]:
        """
        Renders the markdown report into standalone, responsive HTML.
        Saves a local preview copy in tmp/ (never in output/ to avoid committing).
        Returns (html_content, preview_path).
        """
        md_content = self.read_markdown()
        html_content = markdown_to_email_html(md_content, context=None)

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
        subject = self.extract_subject(md_content)
        html_content, preview_path = self.render_html(save_preview=True)

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

        headers = {"Content-Type": "application/json"}
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
