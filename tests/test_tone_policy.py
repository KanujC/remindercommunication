import pytest

from dunning_studio.tone_policy import resolve_firmness


@pytest.mark.parametrize(
    "segment,reminder_index,expected",
    [
        ("reliable", 1, 1), ("reliable", 2, 2), ("reliable", 3, 3),
        ("occasional", 1, 2), ("occasional", 2, 3), ("occasional", 3, 4),
        ("defaulter", 1, 3), ("defaulter", 2, 4), ("defaulter", 3, 5),
    ],
)
def test_firmness_table(segment, reminder_index, expected):
    assert resolve_firmness(segment, reminder_index) == expected


def test_firmness_monotonic_within_segment():
    for segment in ("reliable", "occasional", "defaulter"):
        values = [resolve_firmness(segment, i) for i in (1, 2, 3)]
        assert values == sorted(values)
        assert len(set(values)) == 3
