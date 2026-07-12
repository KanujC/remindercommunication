from datetime import date

import pytest
from pydantic import ValidationError

from dunning_studio.schemas import CustomerRecord, InvoiceFacts, format_amount, format_due_date


def test_customer_record_round_trip():
    c = CustomerRecord(
        customer_id="c1", customer_name="Jane", on_time_rate=0.9, prior_defaults=0,
        days_past_due_avg=1.0, last_payment_days_ago=5, account_age_days=200,
    )
    assert CustomerRecord.model_validate(c.model_dump()) == c


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        CustomerRecord(
            customer_id="c1", customer_name="Jane", on_time_rate=0.9, prior_defaults=0,
            days_past_due_avg=1.0, last_payment_days_ago=5, account_age_days=200,
            unexpected_field="nope",
        )


def test_invoice_facts_rejects_missing_due_date():
    with pytest.raises(ValidationError):
        InvoiceFacts(
            amount_minor=100, currency="EUR", account_ref="A1",
            pay_link="https://example.com/a1", locale="en-GB", channel="email", reminder_index=1,
        )


@pytest.mark.parametrize(
    "amount_minor,locale,expected",
    [
        (4900, "de-DE", "49,00 €"),
        (123456, "de-DE", "1.234,56 €"),
        (4900, "en-GB", "€49.00"),
        (123456, "en-GB", "€1,234.56"),
        (4900, "nl-NL", "€ 49,00"),
        (4900, "sv-SE", "49,00 €"),
        (100, "de-DE", "1,00 €"),
        (1, "de-DE", "0,01 €"),
    ],
)
def test_format_amount(amount_minor, locale, expected):
    assert format_amount(amount_minor, "EUR", locale) == expected


def test_format_amount_no_floats_ever():
    # amount_minor must be an int; passing a float should be coerced/rejected by callers,
    # not silently truncated by format_amount.
    with pytest.raises(TypeError):
        format_amount(49.0, "EUR", "de-DE")  # type: ignore[arg-type]


def test_format_due_date_de():
    assert format_due_date(date(2026, 7, 12), "de-DE") == "12. Juli 2026"


def test_format_due_date_en():
    assert format_due_date(date(2026, 7, 1), "en-GB") == "1 July 2026"
