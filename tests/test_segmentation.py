import pytest

from dunning_studio.schemas import CustomerRecord
from dunning_studio.segmentation import segment_customer


def _customer(**overrides) -> CustomerRecord:
    base = dict(
        customer_id="c1", customer_name="Jane", on_time_rate=0.99, prior_defaults=0,
        days_past_due_avg=0.0, last_payment_days_ago=1, account_age_days=100,
    )
    base.update(overrides)
    return CustomerRecord(**base)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"prior_defaults": 2}, "defaulter"),
        ({"prior_defaults": 1}, "occasional"),
        ({"on_time_rate": 0.69}, "defaulter"),
        ({"on_time_rate": 0.70}, "occasional"),
        ({"on_time_rate": 0.94}, "occasional"),
        ({"on_time_rate": 0.95}, "reliable"),
        ({"days_past_due_avg": 7.01}, "occasional"),
        ({"days_past_due_avg": 7.0}, "reliable"),
        ({}, "reliable"),
        ({"prior_defaults": 2, "on_time_rate": 0.99}, "defaulter"),
    ],
)
def test_segmentation_boundaries(overrides, expected):
    assert segment_customer(_customer(**overrides)) == expected
