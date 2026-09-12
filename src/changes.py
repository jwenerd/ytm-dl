import os
import threading
from dataclasses import dataclass, field

from .util import write_file


@dataclass
class ChangeRecord:
    emoji: str
    label: str
    count: int
    log_message: str
    details: list[str] = field(default_factory=list)


class ChangeTracker:
    _lock = threading.Lock()
    _records: list[ChangeRecord] = []

    @classmethod
    def reset(cls) -> None:
        """Clears all recorded changes."""
        with cls._lock:
            cls._records.clear()

    @classmethod
    def record(
        cls,
        emoji: str,
        label: str,
        count: int,
        log_message: str,
        details: list[str] | None = None,
    ) -> None:
        """Thread-safely records a modified file or dataset."""
        with cls._lock:
            cls._records.append(
                ChangeRecord(
                    emoji=emoji,
                    label=label,
                    count=count,
                    log_message=log_message,
                    details=list(details) if details else [],
                )
            )

    @classmethod
    def get_changes(cls) -> list[ChangeRecord]:
        """Returns a copy of the list of recorded changes."""
        with cls._lock:
            return list(cls._records)

    @classmethod
    def format_commit_message(cls, run_option: str = "") -> str:
        """
        Builds a Git commit message with:
        - Subject: Run info + concise summary of modified files (or emoji list if >3 datasets).
        - Body: Detailed emoji output lines for only modified files/shelves.
        """
        job = os.getenv("GITHUB_JOB") or "run"
        event_name = os.getenv("GITHUB_EVENT_NAME") or "local"
        run_number = os.getenv("GITHUB_RUN_NUMBER") or ""
        run_opt = run_option or os.getenv("RUN_OPTION") or ""

        if run_opt:
            prefix = f"{job}({run_opt}) {event_name}"
        else:
            prefix = f"{job} {event_name}"

        if run_number:
            prefix = f"{prefix} #{run_number}"

        records = cls.get_changes()

        if not records:
            subject = f"{prefix}: ☕ Up to date"
            body = "No data files modified."
            return f"{subject}\n\n{body}\n"

        if len(records) <= 3:
            items_str = ", ".join(
                f"{r.emoji} {r.label} (+{r.count})" if r.count > 0 else f"{r.emoji} {r.label}"
                for r in records
            )
            subject = f"{prefix}: {items_str}"
            if len(subject) > 100:
                emojis = " ".join(r.emoji for r in records)
                subject = f"{prefix}: {emojis} ({len(records)} datasets updated)"
        else:
            emojis = " ".join(r.emoji for r in records)
            subject = f"{prefix}: {emojis} ({len(records)} datasets updated)"

        body_lines: list[str] = []
        for r in records:
            body_lines.append(r.log_message)
            for d in r.details:
                body_lines.append(f"  {d}")

        body = "\n".join(body_lines)
        return f"{subject}\n\n{body}\n"

    @classmethod
    def write_commit_message(
        cls, filepath: str = "tmp/commit_message.txt", run_option: str = ""
    ) -> str:
        """Formats and writes the commit message to a file for CI consumption."""
        content = cls.format_commit_message(run_option=run_option)
        write_file(filepath, content)
        return content
