"""Send Gmail summary notifications via SMTP (App Password)."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from .config import NotifyConfig
from .state import RunLogEntry


def send_summary(notify: NotifyConfig, entries: Iterable[RunLogEntry], dry_run: bool = False) -> None:
    if not notify.enabled:
        return

    entries = list(entries)
    lowered = [e for e in entries if e.result == "lowered"]
    skipped = [e for e in entries if e.result.startswith("skipped")]
    errors = [e for e in entries if e.result.startswith("error")]

    subject = (
        f"[mercariauto{' DRY-RUN' if dry_run else ''}] "
        f"値下げ {len(lowered)}件 / スキップ {len(skipped)}件 / エラー {len(errors)}件"
    )

    lines: list[str] = []
    lines.append(f"値下げ: {len(lowered)}件")
    for e in lowered:
        lines.append(f"  - {e.title or e.item_id}: {e.before_price}円 → {e.after_price}円")
    lines.append("")
    lines.append(f"スキップ: {len(skipped)}件")
    for e in skipped:
        lines.append(f"  - {e.title or e.item_id}: {e.result} (現在 {e.before_price}円)")
    lines.append("")
    lines.append(f"エラー: {len(errors)}件")
    for e in errors:
        lines.append(f"  - {e.title or e.item_id}: {e.result} {e.message or ''}")

    body = "\n".join(lines)
    _send(notify, subject, body)


def send_reminder(notify: NotifyConfig, days_since_last_run: int | None) -> None:
    """Send a reminder email asking the user to open their Mac and run the script."""
    subject = "[mercariauto] 値下げ実行のお時間です"
    if days_since_last_run is None:
        when = "まだ一度も実行されていません。"
    else:
        when = f"前回実行から {days_since_last_run} 日経過しています。"
    body = (
        f"{when}\n\n"
        "Macを開いて以下を実行してください:\n\n"
        "    cd ~/path/to/mercariauto\n"
        "    python -m mercari_auto.main\n\n"
        "実行が完了すると結果メールが届きます。\n"
    )
    _send(notify, subject, body)


def _send(notify: NotifyConfig, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = notify.gmail_user
    msg["To"] = notify.to
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
        smtp.login(notify.gmail_user, notify.gmail_app_password)
        smtp.send_message(msg)
