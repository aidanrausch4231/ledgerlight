"""Printable user units only; never installs or invokes systemd."""

SERVICE = """[Unit]
Description=Sync ledgerlight accounts and daily balances

[Service]
Type=oneshot
ExecStart=%h/.local/bin/ledgerlight sync
"""

TIMER = """[Unit]
Description=Sync ledgerlight every six hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""


def units():
    return {"service": SERVICE, "timer": TIMER}
