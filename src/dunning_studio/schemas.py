"""Pydantic v2 data contracts for the Dunning Studio pipeline. See CLAUDE.md section 4."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerRecord(StrictModel):
    customer_id: str
    customer_name: str  # UNTRUSTED (I2)
    on_time_rate: float
    prior_defaults: int
    days_past_due_avg: float
    last_payment_days_ago: int
    account_age_days: int


class MerchantProfile(StrictModel):
    merchant_id: str
    merchant_name: str  # UNTRUSTED (I2)
    voice: Literal["formal", "friendly", "neutral"]


class InvoiceFacts(StrictModel):
    amount_minor: int
    currency: Literal["EUR"]
    due_date: date
    account_ref: str
    pay_link: HttpUrl
    locale: Literal["de-DE", "nl-NL", "en-GB", "sv-SE"]
    channel: Literal["email", "sms"]
    reminder_index: Literal[1, 2, 3]


class ToneSpec(StrictModel):
    segment: Literal["reliable", "occasional", "defaulter"]
    archetype: Literal["formal", "friendly", "neutral"]
    firmness: Literal[1, 2, 3, 4, 5]
    register_notes: str


class GateCheck(StrictModel):
    check_id: str
    passed: bool
    detail: str


class GateResult(StrictModel):
    passed: bool
    checks: list[GateCheck]
    judge_scores: dict[str, int] | None = None


class SendDecision(StrictModel):
    case_id: str
    final_text: str
    source: Literal["generated", "regenerated", "static_template", "held"]
    tone_spec: ToneSpec
    gate_result: GateResult
    fallback_steps_taken: int
    model_calls: int
    latency_ms: int


_CURRENCY_SYMBOL = {"EUR": "€"}


def _group_thousands(int_part: str, sep: str) -> str:
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    return sep.join(groups)


def format_amount(amount_minor: int, currency: Literal["EUR"], locale: str) -> str:
    """Locale-aware money formatting. The single source of truth (gate A1 depends on it)."""
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise TypeError("amount_minor must be an int (cents); floats are never allowed for money")
    if amount_minor < 0:
        raise ValueError("amount_minor must be non-negative")
    symbol = _CURRENCY_SYMBOL[currency]
    major, minor = divmod(amount_minor, 100)
    int_part = str(major)

    if locale == "de-DE":
        grouped = _group_thousands(int_part, ".")
        return f"{grouped},{minor:02d} {symbol}"
    if locale == "nl-NL":
        grouped = _group_thousands(int_part, ".")
        return f"{symbol} {grouped},{minor:02d}"
    if locale == "en-GB":
        grouped = _group_thousands(int_part, ",")
        return f"{symbol}{grouped}.{minor:02d}"
    if locale == "sv-SE":
        grouped = _group_thousands(int_part, " ")
        return f"{grouped},{minor:02d} {symbol}"
    raise ValueError(f"unsupported locale: {locale}")


_MONTH_NAMES = {
    "de-DE": ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"],
    "nl-NL": ["", "januari", "februari", "maart", "april", "mei", "juni", "juli",
              "augustus", "september", "oktober", "november", "december"],
    "en-GB": ["", "January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"],
    "sv-SE": ["", "januari", "februari", "mars", "april", "maj", "juni", "juli",
              "augusti", "september", "oktober", "november", "december"],
}


def format_due_date(due_date: date, locale: str) -> str:
    """Locale-aware due-date formatting. Single source of truth (gate A2 depends on it)."""
    if locale not in _MONTH_NAMES:
        raise ValueError(f"unsupported locale: {locale}")
    month_name = _MONTH_NAMES[locale][due_date.month]
    if locale == "de-DE":
        return f"{due_date.day}. {month_name} {due_date.year}"
    if locale in ("nl-NL", "sv-SE"):
        return f"{due_date.day} {month_name} {due_date.year}"
    if locale == "en-GB":
        return f"{due_date.day} {month_name} {due_date.year}"
    raise ValueError(f"unsupported locale: {locale}")
