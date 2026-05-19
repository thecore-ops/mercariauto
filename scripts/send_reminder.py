"""Send a reminder email from GitHub Actions cron.

This runs in GitHub Actions (no Mercari access, no Playwright). It just sends
a Gmail SMTP email saying "open your Mac and run the script."

Required env vars (set as GitHub Secrets):
- GMAIL_USER          (e.g. you@gmail.com)
- GMAIL_APP_PASSWORD  (Gmail app password, https://myaccount.google.com/apppasswords)
- GMAIL_TO            (recipient - usually same as GMAIL_USER)
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def main() -> None:
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("GMAIL_TO") or user
    if not user or not pw:
        print("GMAIL_USER and GMAIL_APP_PASSWORD must be set", file=sys.stderr)
        sys.exit(2)

    msg = EmailMessage()
    msg["Subject"] = "[mercariauto] 値下げ実行のお時間です（更新版）"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(
        "メルカリの値下げ実行リマインダーです。\n\n"
        "Macを開いて以下を実行してください:\n\n"
        "    cd \"/Users/yuki/Desktop/THE CORE AIデータ/メルカリ価格調整自動化\"\n"
        "    source .venv/bin/activate\n"
        "    python -m mercari_auto.main\n\n"
        "実行後、結果のサマリーメールが届きます。\n"
    )

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
        smtp.login(user, pw)
        smtp.send_message(msg)
    print(f"Reminder sent to {to}")


if __name__ == "__main__":
    main()
