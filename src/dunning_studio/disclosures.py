"""Required disclosure strings by (locale, reminder_index). Verbatim, gate A6 depends on these."""

from typing import Literal

DISCLOSURES: dict[str, dict[int, str]] = {
    "en-GB": {
        1: "This is a payment reminder regarding your account.",
        2: "This is a second payment reminder regarding your account.",
        3: "If payment is not received, we may proceed with next steps in the collections process.",
    },
    "de-DE": {
        1: "Dies ist eine Zahlungserinnerung zu Ihrem Konto.",
        2: "Dies ist die zweite Zahlungserinnerung zu Ihrem Konto.",
        3: "Sollte die Zahlung ausbleiben, können wir die nächsten Schritte im Inkassoprozess einleiten.",
    },
    "nl-NL": {
        1: "Dit is een betalingsherinnering voor uw account.",
        2: "Dit is de tweede betalingsherinnering voor uw account.",
        3: "Als de betaling uitblijft, kunnen wij de volgende stappen in het incassoproces starten.",
    },
    "sv-SE": {
        1: "Detta är en betalningspåminnelse för ditt konto.",
        2: "Detta är den andra betalningspåminnelsen för ditt konto.",
        3: "Om betalning uteblir kan vi inleda nästa steg i inkassoprocessen.",
    },
}


def get_disclosure(locale: str, reminder_index: Literal[1, 2, 3]) -> str:
    return DISCLOSURES[locale][reminder_index]
