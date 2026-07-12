"""Deterministic customer segmentation. See CLAUDE.md 5.1. First match wins."""

from typing import Literal

from dunning_studio.schemas import CustomerRecord

Segment = Literal["reliable", "occasional", "defaulter"]


def segment_customer(customer: CustomerRecord) -> Segment:
    if customer.prior_defaults >= 2 or customer.on_time_rate < 0.70:
        return "defaulter"
    if (
        customer.prior_defaults == 1
        or customer.on_time_rate < 0.95
        or customer.days_past_due_avg > 7
    ):
        return "occasional"
    return "reliable"
