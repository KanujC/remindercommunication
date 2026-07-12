"""Static fallback template loading and startup validation. See CLAUDE.md I5, section 8 step 2."""

from datetime import date
from pathlib import Path
from typing import Literal

from dunning_studio.gates.deterministic import (
    check_a1_amount, check_a2_due_date, check_a3_account_ref,
    check_a4_no_unresolved_tokens, check_a5_blocklist, check_a6_disclosure,
)
from dunning_studio.injection import build_tokens, inject
from dunning_studio.schemas import GateCheck, InvoiceFacts

SEGMENTS = ("reliable", "occasional", "defaulter")
LOCALES = ("de-DE", "nl-NL", "en-GB", "sv-SE")
CHANNELS = ("email", "sms")

_STATIC_DIR = Path(__file__).parent / "templates" / "static"


def _template_name(segment: str, locale: str, channel: str) -> str:
    return f"{segment}_{locale}_{channel}.txt"


def load_static_template(segment: str, locale: str, channel: str) -> str:
    path = _STATIC_DIR / _template_name(segment, locale, channel)
    if not path.is_file():
        raise FileNotFoundError(f"missing static template: {_template_name(segment, locale, channel)}")
    return path.read_text(encoding="utf-8")


def _sample_facts(locale: str, channel: str, reminder_index: Literal[1, 2, 3]) -> InvoiceFacts:
    return InvoiceFacts(
        amount_minor=4900,
        currency="EUR",
        due_date=date(2026, 7, 1),
        account_ref="ACC-0001",
        pay_link="https://pay.example.com/acc-0001",
        locale=locale,
        channel=channel,
        reminder_index=reminder_index,
    )


def _run_a1_a6(text: str, facts: InvoiceFacts) -> list[GateCheck]:
    return [
        check_a1_amount(text, facts),
        check_a2_due_date(text, facts),
        check_a3_account_ref(text, facts),
        check_a4_no_unresolved_tokens(text),
        check_a5_blocklist(text),
        check_a6_disclosure(text, facts),
    ]


def validate_all_templates() -> None:
    """Load every (segment, locale, channel) template and assert A1..A6 pass by construction (I5)."""
    for segment in SEGMENTS:
        for locale in LOCALES:
            for channel in CHANNELS:
                raw = load_static_template(segment, locale, channel)
                for reminder_index in (1, 2, 3):
                    facts = _sample_facts(locale, channel, reminder_index)
                    tokens = build_tokens("Sample Customer", "Sample Merchant", facts)
                    text = inject(raw, tokens)
                    checks = _run_a1_a6(text, facts)
                    failures = [c for c in checks if not c.passed]
                    if failures:
                        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failures)
                        raise RuntimeError(
                            f"static template {segment}_{locale}_{channel}.txt failed gates: {detail}"
                        )
