# Utility functions for musical key transposition

from typing import List, Dict

KEY_TO_SEMITONE: Dict[str, int] = {
    'C': 0, 'C#': 1, 'Db': 1,
    'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8,
    'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11,
}

SEMITONE_TO_KEY: Dict[int, str] = {
    0: 'C',
    1: 'C#/Db',
    2: 'D',
    3: 'D#/Eb',
    4: 'E',
    5: 'F',
    6: 'F#/Gb',
    7: 'G',
    8: 'G#/Ab',
    9: 'A',
    10: 'A#/Bb',
    11: 'B'
}

INSTRUMENT_TRANSPOSITIONS: Dict[str, int] = {
    'Rhythm Chart': 0,
    'Acoustic Guitar': 0,
    'Flute 1/2': 0,
    'Flute/Oboe 1/2/3': 0,
    'Oboe': 0,
    'Clarinet 1/2': -2,
    'Bass Clarinet': -2,
    'Bassoon': 0,
    'French Horn 1/2': -7,
    'Trumpet 1,2': -2,
    'Trumpet 3': -2,
    'Trombone 1/2': 0,
    'Trombone 3/Tuba': 0,
    'Alto Sax': -9,
    'Tenor Sax 1/2': -2,
    'Bari Sax': -9,
    'Timpani': 0,
    'Percussion': 0,
    'Violin 1/2': 0,
    'Viola': 0,
    'Cello': 0,
    'Double Bass': 0,
    'String Reduction': 0,
    'String Bass': 0,
    'Lead Sheet (SAT)': 0,
}

VALID_KEYS = set(KEY_TO_SEMITONE.keys())


def normalize_key(key: str) -> str:
    """Normalize a key string (e.g. 'ab ' -> 'Ab')."""
    key = key.strip()
    if not key:
        return ""
    key = key.split()[0]
    note = key[0].upper()
    accidental = key[1:].replace("B", "b")
    return note + accidental


def get_interval_name(semitones: int) -> str:
    intervals = {
        0: 'Perfect Unison',
        1: 'Minor Second',
        2: 'Major Second',
        3: 'Minor Third',
        4: 'Major Third',
        5: 'Perfect Fourth',
        6: 'Tritone',
        7: 'Perfect Fifth',
        8: 'Minor Sixth',
        9: 'Major Sixth',
        10: 'Minor Seventh',
        11: 'Major Seventh',
        12: 'Octave'
    }
    return intervals.get(semitones % 12, f'{semitones} semitones')


def _modular_distance(a: int, b: int) -> (int, str):
    """Return the smallest distance and direction from a to b."""
    up = (b - a) % 12
    down = (a - b) % 12
    if up < down:
        return up, 'above' if up != 0 else 'none'
    if down < up:
        return down, 'below' if down != 0 else 'none'
    # up == down -> symmetrical (e.g. tritone or unison)
    return up, 'none' if up != 0 else 'none'


def get_transposition_suggestions(available_keys: List[str], selected_instrument: str, target_key: str) -> Dict[str, List[dict]]:
    target_key = normalize_key(target_key)
    if target_key not in KEY_TO_SEMITONE:
        return {'direct': [], 'closest': []}

    if selected_instrument not in INSTRUMENT_TRANSPOSITIONS:
        return {'direct': [], 'closest': []}

    target_semitone = KEY_TO_SEMITONE[target_key]

    matches_direct = []
    matches_closest = []

    for instrument, T_O in INSTRUMENT_TRANSPOSITIONS.items():
        if instrument == selected_instrument:
            continue
        required_written_semitone = (target_semitone - T_O) % 12
        required_written_key = SEMITONE_TO_KEY.get(required_written_semitone, 'Unknown')

        if required_written_key in available_keys:
            matches_direct.append({
                'instrument': instrument,
                'key': required_written_key,
                'difference': 0,
                'interval_direction': 'none',
                'interval': 'Perfect Unison'
            })
        else:
            available_semitones = [KEY_TO_SEMITONE[k] for k in available_keys if k in KEY_TO_SEMITONE]
            if not available_semitones:
                continue

            diffs = []
            for semitone in available_semitones:
                diff, direction = _modular_distance(required_written_semitone, semitone)
                diffs.append((diff, semitone, direction))
            diffs.sort(key=lambda x: x[0])
            closest_diff, closest_semitone, interval_direction = diffs[0]
            closest_key = SEMITONE_TO_KEY.get(closest_semitone, 'Unknown')
            interval_name = get_interval_name(closest_diff)
            matches_closest.append({
                'instrument': instrument,
                'key': closest_key,
                'difference': closest_diff,
                'interval_direction': interval_direction,
                'interval': interval_name
            })

    matches_closest.sort(key=lambda s: s['difference'])
    return {'direct': matches_direct, 'closest': matches_closest}
