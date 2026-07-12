"""Deterministic gate asserts A1..A10. Pure functions over (text, facts, tone_spec, ...).
See CLAUDE.md section 7.1. Hard failures route to the fallback ladder; soft failures
alone trigger a single regeneration before falling back.
"""

import re
import unicodedata

from langdetect import DetectorFactory, detect_langs

from dunning_studio.disclosures import get_disclosure
from dunning_studio.injection import unresolved_tokens
from dunning_studio.schemas import GateCheck, InvoiceFacts, ToneSpec, format_amount, format_due_date

DetectorFactory.seed = 0

HARD = "hard"
SOFT = "soft"

BLOCKLIST = [
    "lawsuit", "sue", "police", "criminal", "schufa", "blacklist",
    "debt collector at your door", "final warning or else", "deadbeat", "shame",
    "immediately or", "arrest", "seizure", "wage garnishment",
    "credit score will be destroyed",
]

_PROMISE_PATTERNS = [
    re.compile(r"waiv\w+", re.IGNORECASE),
    re.compile(r"discount", re.IGNORECASE),
    re.compile(r"extend\w+ deadline", re.IGNORECASE),
    re.compile(r"no fees", re.IGNORECASE),
    re.compile(r"we guarantee", re.IGNORECASE),
]

_CURRENCY_LIKE = re.compile(r"(?:€\s?\d(?:[\d.,]*\d)?)|(?:\d(?:[\d.,]*\d)?\s?€)")
_DATE_LIKE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
_INJECTION_PHRASES = ["ignore previous", "system prompt", "disregard instructions"]

_LOCALE_LANG = {"de-DE": "de", "nl-NL": "nl", "en-GB": "en", "sv-SE": "sv"}


def check_a1_amount(text: str, facts: InvoiceFacts) -> GateCheck:
    expected = format_amount(facts.amount_minor, facts.currency, facts.locale)
    occurrences = text.count(expected)
    other_matches = [m for m in _CURRENCY_LIKE.findall(text) if m != expected]
    passed = occurrences >= 1 and not other_matches
    detail = f"expected={expected!r} occurrences={occurrences} other_matches={other_matches}"
    return GateCheck(check_id="A1", passed=passed, detail=detail)


def check_a2_due_date(text: str, facts: InvoiceFacts) -> GateCheck:
    expected = format_due_date(facts.due_date, facts.locale)
    occurrences = text.count(expected)
    stripped = text.replace(expected, "")
    other_matches = _DATE_LIKE.findall(stripped)
    passed = occurrences >= 1 and not other_matches
    detail = f"expected={expected!r} occurrences={occurrences} other_matches={other_matches}"
    return GateCheck(check_id="A2", passed=passed, detail=detail)


def check_a3_account_ref(text: str, facts: InvoiceFacts) -> GateCheck:
    if facts.channel == "sms":
        return GateCheck(check_id="A3", passed=True, detail="sms channel: account_ref optional")
    passed = facts.account_ref in text
    return GateCheck(check_id="A3", passed=passed, detail=f"account_ref={facts.account_ref!r} present={passed}")


def check_a4_no_unresolved_tokens(text: str) -> GateCheck:
    tokens = unresolved_tokens(text)
    stray_braces = text.count("{") != text.count("}") or bool(re.search(r"\{(?!\{)|(?<!\})\}", text))
    passed = not tokens and not stray_braces
    return GateCheck(check_id="A4", passed=passed, detail=f"unresolved={tokens} stray_braces={stray_braces}")


def check_a5_blocklist(text: str) -> GateCheck:
    normalized = unicodedata.normalize("NFC", text).lower()
    hits = [term for term in BLOCKLIST if term.lower() in normalized]
    return GateCheck(check_id="A5", passed=not hits, detail=f"hits={hits}")


def check_a6_disclosure(text: str, facts: InvoiceFacts) -> GateCheck:
    expected = get_disclosure(facts.locale, facts.reminder_index)
    passed = expected in text
    return GateCheck(check_id="A6", passed=passed, detail=f"expected={expected!r} present={passed}")


def check_a7_channel_limits(text: str, facts: InvoiceFacts) -> GateCheck:
    if facts.channel == "email":
        word_count = len(text.split())
        passed = 40 <= word_count <= 120
        detail = f"email word_count={word_count}"
    else:
        char_count = len(text)
        single_paragraph = "\n\n" not in text.strip()
        passed = char_count <= 300 and single_paragraph
        detail = f"sms char_count={char_count} single_paragraph={single_paragraph}"
    return GateCheck(check_id="A7", passed=passed, detail=detail)


def check_a8_language_match(text: str, facts: InvoiceFacts) -> GateCheck:
    expected_lang = _LOCALE_LANG[facts.locale]
    try:
        candidates = detect_langs(text)
    except Exception as exc:  # langdetect raises on empty/ambiguous text
        return GateCheck(check_id="A8", passed=False, detail=f"detect_langs failed: {exc}")
    top = candidates[0]
    passed = top.lang == expected_lang and top.prob >= 0.8
    detail = f"expected={expected_lang} detected={top.lang} prob={top.prob:.2f}"
    return GateCheck(check_id="A8", passed=passed, detail=detail)


def check_a9_unauthorised_promise(text: str) -> GateCheck:
    hits = [p.pattern for p in _PROMISE_PATTERNS if p.search(text)]
    return GateCheck(check_id="A9", passed=not hits, detail=f"hits={hits}")


def _ngrams(words: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


def check_a10_injection_echo(text: str, customer_name: str, merchant_name: str) -> GateCheck:
    lowered = text.lower()
    phrase_hits = [p for p in _INJECTION_PHRASES if p in lowered]

    ngram_hits: list[str] = []
    text_words = re.findall(r"\w+", lowered)
    for source in (customer_name, merchant_name):
        source_words = re.findall(r"\w+", source.lower())
        if len(source_words) < 4:
            continue
        for gram in _ngrams(source_words, 4):
            if gram in _ngrams(text_words, 4):
                ngram_hits.append(" ".join(gram))

    passed = not phrase_hits and not ngram_hits
    detail = f"phrase_hits={phrase_hits} ngram_hits={ngram_hits}"
    return GateCheck(check_id="A10", passed=passed, detail=detail)


SEVERITY = {
    "A1": HARD, "A2": HARD, "A3": HARD, "A4": HARD, "A5": HARD,
    "A6": HARD, "A7": SOFT, "A8": SOFT, "A9": HARD, "A10": HARD,
}


def run_all(
    text: str,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    customer_name: str,
    merchant_name: str,
) -> list[GateCheck]:
    """Run A1..A10. Always runs all checks (eval-mode semantics); callers short-circuit if needed."""
    return [
        check_a1_amount(text, facts),
        check_a2_due_date(text, facts),
        check_a3_account_ref(text, facts),
        check_a4_no_unresolved_tokens(text),
        check_a5_blocklist(text),
        check_a6_disclosure(text, facts),
        check_a7_channel_limits(text, facts),
        check_a8_language_match(text, facts),
        check_a9_unauthorised_promise(text),
        check_a10_injection_echo(text, customer_name, merchant_name),
    ]
