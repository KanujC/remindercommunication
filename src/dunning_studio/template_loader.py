"""Static fallback template loading and startup validation. See CLAUDE.md I5, section 8 step 2."""

from datetime import date
from pathlib import Path
from typing import Literal

from dunning_studio.gates.deterministic import run_static_checks
from dunning_studio.injection import build_tokens, inject
from dunning_studio.schemas import InvoiceFacts

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
                    checks = run_static_checks(text, facts)
                    failures = [c for c in checks if not c.passed]
                    if failures:
                        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failures)
                        raise RuntimeError(
                            f"static template {segment}_{locale}_{channel}.txt failed gates: {detail}"
                        )
