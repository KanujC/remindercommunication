"""Golden-set CSV loading. Pure parsing, shared by cli.py and eval/run_eval.py."""

import csv
from datetime import date
from pathlib import Path

from dunning_studio.schemas import CustomerRecord, InvoiceFacts, MerchantProfile

GOLDEN_SET_COLUMNS = [
    "case_id", "segment_expected", "archetype", "reminder_index", "locale", "channel",
    "customer_name", "merchant_name", "on_time_rate", "prior_defaults", "days_past_due_avg",
    "last_payment_days_ago", "account_age_days", "amount_minor", "due_date", "account_ref",
    "expected_outcome", "adversarial", "notes",
]


class InvalidRowError(ValueError):
    """Raised when a golden-set row cannot be turned into valid schema objects (e.g. due_date missing)."""


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_to_case(row: dict[str, str]) -> tuple[CustomerRecord, MerchantProfile, InvoiceFacts]:
    try:
        customer = CustomerRecord(
            customer_id=row["case_id"],
            customer_name=row["customer_name"],
            on_time_rate=float(row["on_time_rate"]),
            prior_defaults=int(row["prior_defaults"]),
            days_past_due_avg=float(row["days_past_due_avg"]),
            last_payment_days_ago=int(row["last_payment_days_ago"]),
            account_age_days=int(row["account_age_days"]),
        )
        merchant = MerchantProfile(
            merchant_id=row["case_id"],
            merchant_name=row["merchant_name"],
            voice=row["archetype"],
        )
        facts = InvoiceFacts(
            amount_minor=int(row["amount_minor"]),
            currency="EUR",
            due_date=date.fromisoformat(row["due_date"]),
            account_ref=row["account_ref"],
            pay_link="https://pay.example.com/" + row["account_ref"].lower(),
            locale=row["locale"],
            channel=row["channel"],
            reminder_index=int(row["reminder_index"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidRowError(f"row {row.get('case_id', '?')!r} is invalid: {exc}") from exc
    return customer, merchant, facts


def load_case(csv_path: Path, case_id: str) -> tuple[CustomerRecord, MerchantProfile, InvoiceFacts]:
    for row in read_rows(csv_path):
        if row["case_id"] == case_id:
            return row_to_case(row)
    raise KeyError(f"case_id not found in {csv_path}: {case_id}")
