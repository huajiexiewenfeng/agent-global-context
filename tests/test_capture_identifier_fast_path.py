"""Preserve identifier rejection semantics while avoiding per-character work."""
import cProfile
import pstats

import pytest

from agc_runtime import capture_schema as schema


def legacy_identifier(value, name, *, nullable=False):
    value = schema._nfc_string(value, name, maximum=128, nullable=nullable)
    if value is None:
        return None
    if not schema._IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be an ASCII identifier")
    return value


def outcome(parser, value, nullable):
    try:
        return ('accepted', parser(value, 'id', nullable=nullable))
    except ValueError as error:
        return ('rejected', str(error))


def test_valid_ascii_identifier_avoids_unicode_character_scan():
    value = '01a07c2c-57f0-78c2-beca-15febfcf6e03'
    profile = cProfile.Profile()
    profile.enable()
    result = schema._identifier(value, 'id')
    profile.disable()
    assert result == value
    category_calls = sum(stats[1] for (_, _, name), stats in pstats.Stats(profile).stats.items()
                         if 'unicodedata.category' in name)
    assert category_calls == 0


@pytest.mark.parametrize('nullable', [False, True])
def test_identifier_matches_existing_acceptance_and_errors(nullable):
    values = [None, 0, False, [], {}, b'id', '', ' ', 'a' * 128, 'a' * 129,
              'a-b_c.d:e', 'a\n', '\u00e9', 'e\u0301', '\u4e2d',
              'x\u200b', 'x\ud800', 'x\ue000', 'x\U0001f600', 'x\U0010ffff']
    for code in range(128):
        values.extend([chr(code), 'a' + chr(code), chr(code) + 'a'])
    for value in values:
        assert outcome(schema._identifier, value, nullable) == outcome(legacy_identifier, value, nullable)
