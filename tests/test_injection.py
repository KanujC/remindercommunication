from datetime import date

from dunning_studio.injection import build_tokens, inject, unresolved_tokens
from dunning_studio.schemas import InvoiceFacts


def test_build_tokens_and_inject():
    facts = InvoiceFacts(
        amount_minor=4900, currency="EUR", due_date=date(2026, 6, 15), account_ref="REF-1",
        pay_link="https://pay.example.com/ref-1", locale="en-GB", channel="email", reminder_index=1,
    )
    tokens = build_tokens("Jane", "ACME", facts)
    template = "Dear {{CUSTOMER_NAME}}, pay {{AMOUNT}} by {{DUE_DATE}}. {{DISCLOSURE}} {{PAY_LINK}} - {{MERCHANT_NAME}}"
    text = inject(template, tokens)
    assert "{{" not in text
    assert "Jane" in text
    assert "€49.00" in text
    assert unresolved_tokens(text) == []


def test_unresolved_tokens_detected():
    assert unresolved_tokens("please pay {{AMOUNT}} now") == ["{{AMOUNT}}"]
