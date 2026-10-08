"""Repeatable synthetic fixtures, never real bank data."""

from datetime import timedelta

from ledgerlight.db import connect
from ledgerlight.money import today


def seed() -> dict:
    merchants = [
        ("Demo Coffee Co", "Food & Drink", -5.5),
        ("Demo Market", "Groceries", -42.0),
        ("Demo Transit", "Transport", -12.0),
        ("Demo Streaming", "Entertainment", -9.0),
        ("Demo Espresso", "Food & Drink", -4.0),
        ("Bean There Cafe", "Food & Drink", -6.0),
    ]
    current_day = today()
    start = current_day - timedelta(days=119)
    transactions = []
    for day in range(120):
        # Keep the prior 90-day dataset's IDs and amounts stable, including
        # parents of user-created splits. New slots add the extra coffee shops.
        choices = merchants[:4] if day < 90 else merchants
        merchant, category, amount = choices[day % len(choices)]
        transactions.append(
            (
                f"demo-expense-{day}",
                "demo-checking",
                str(start + timedelta(days=day)),
                merchant,
                merchant,
                amount,
                category,
            )
        )
        if day % 30 == 0:
            transactions.append(
                (
                    f"demo-income-{day}",
                    "demo-checking",
                    str(start + timedelta(days=day)),
                    "Demo Payroll",
                    "Demo Employer",
                    2500.0,
                    "Income",
                )
            )
    with connect() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO accounts (id, name, balance) VALUES (?, ?, ?)",
            [
                ("demo-checking", "Synthetic Demo Checking", 1234.5),
                ("demo-savings", "Synthetic Demo Savings", 5000.0),
            ],
        )
        # Only refresh the synthetic date on existing demo-owned rows. Keep
        # amounts, effective categories and all user extras/references intact.
        connection.executemany(
            "INSERT INTO transactions "
            "(id, account_id, date, name, merchant, amount, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET date=excluded.date "
            "WHERE transactions.account_id=excluded.account_id",
            transactions,
        )
        connection.executemany(
            "INSERT OR IGNORE INTO balance_snapshots "
            "(date, account_id, current, available) VALUES (?, ?, ?, ?)",
            [
                (
                    str(current_day - timedelta(days=89 - day)),
                    account,
                    balance + day * 2,
                    balance + day * 2,
                )
                for day in range(90)
                for account, balance in [
                    ("demo-checking", 1056.5),
                    ("demo-savings", 4822),
                ]
            ],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO recurring_streams "
            "(id, account_id, direction, description, merchant, frequency, "
            "average_amount, last_amount, last_date, predicted_next_date, "
            "is_active, status, category) VALUES "
            "(?, 'demo-checking', ?, ?, ?, 'MONTHLY', ?, ?, ?, ?, 1, 'MATURE', ?)",
            [
                (
                    f"demo-recurring-{direction}",
                    direction,
                    name,
                    name,
                    amount,
                    amount,
                    str(current_day),
                    str(current_day + timedelta(days=30)),
                    category,
                )
                for direction, name, amount, category in [
                    ("in", "Demo Payroll", 2500, "Income"),
                    ("out", "Demo Streaming", -9, "Entertainment"),
                ]
            ],
        )
    return {"synthetic": True, "accounts": 2, "transactions": len(transactions)}
