import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transposition_utils import get_transposition_suggestions


def test_direct_transposition():
    available = ['D']
    res = get_transposition_suggestions(available, 'Clarinet 1/2', 'C')
    assert res['direct'], 'Expected a direct match'
    match = res['direct'][0]
    assert match['key'] == 'D'
    assert match['difference'] == 0


def test_wraparound_distance():
    available = ['B']
    res = get_transposition_suggestions(available, 'Clarinet 1/2', 'B')
    assert res['closest'], 'Expected a closest match'
    match = next((m for m in res['closest'] if m['instrument'] == 'Tenor Sax 1/2'), None)
    assert match is not None
    assert match['key'] == 'B'
    assert match['difference'] == 2
    assert match['interval'] == 'Major Second'
