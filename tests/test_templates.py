import pytest

from dunning_studio.template_loader import CHANNELS, LOCALES, SEGMENTS, load_static_template, validate_all_templates


def test_all_24_templates_exist_and_load():
    count = 0
    for segment in SEGMENTS:
        for locale in LOCALES:
            for channel in CHANNELS:
                text = load_static_template(segment, locale, channel)
                assert text.strip()
                count += 1
    assert count == 24


def test_validate_all_templates_passes():
    validate_all_templates()  # raises on any A1..A6 failure


def test_missing_template_raises():
    with pytest.raises(FileNotFoundError):
        load_static_template("reliable", "en-GB", "carrier_pigeon")
