"""Tone resolution: segment x archetype x reminder index -> ToneSpec. See CLAUDE.md section 5."""

from typing import Literal

from dunning_studio.schemas import CustomerRecord, InvoiceFacts, MerchantProfile, ToneSpec
from dunning_studio.segmentation import Segment, segment_customer

REGISTER_NOTES: dict[str, str] = {
    "formal": (
        "Third person or formal address, complete sentences, no contractions, "
        "no exclamation marks, no emoji."
    ),
    "friendly": (
        "First person plural, contractions allowed, warm but concise, "
        "at most one exclamation mark, no emoji."
    ),
    "neutral": (
        "Second person, plain declaratives, minimal adjectives, "
        "no exclamation marks, no emoji."
    ),
}

_FIRMNESS_TABLE: dict[Segment, dict[Literal[1, 2, 3], int]] = {
    "reliable": {1: 1, 2: 2, 3: 3},
    "occasional": {1: 2, 2: 3, 3: 4},
    "defaulter": {1: 3, 2: 4, 3: 5},
}


def resolve_firmness(segment: Segment, reminder_index: Literal[1, 2, 3]) -> int:
    return _FIRMNESS_TABLE[segment][reminder_index]


def resolve_tone(
    customer: CustomerRecord, merchant: MerchantProfile, invoice: InvoiceFacts
) -> ToneSpec:
    segment = segment_customer(customer)
    firmness = resolve_firmness(segment, invoice.reminder_index)
    return ToneSpec(
        segment=segment,
        archetype=merchant.voice,
        firmness=firmness,
        register_notes=REGISTER_NOTES[merchant.voice],
    )
