"""Stage the existing deck body with native-host entry exports.

This only adjusts the namespace declaration; Amu performs compilation. The
result still requires an OS runtime, renderer and persistence adapter.
"""
from pathlib import Path

def stage(root: Path) -> str:
    source = (root / 'src/zuhyo/deck.kotoba').read_text(encoding='utf-8')
    original = '(ns zuhyo.deck (:export [main]))'
    if not source.startswith(original):
        raise ValueError('unexpected deck module declaration')
    header = '(ns zuhyo.deck (:export [init view step snap-encode snap-decode main]))'
    return header + source[len(original):]
