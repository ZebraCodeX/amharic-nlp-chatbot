# -*- coding: utf-8 -*-
"""
letters.py — Ethiopic "letter" (fidel family) helpers.

Amharic syllables are laid out in the main Ethiopic block in families of 8 code
points (7 vowel orders + 1 reserved slot). The base of a family is therefore
``0x1200 + ((cp - 0x1200) // 8) * 8``. Grouping words by that base gives the
classic Amharic dictionary index: ሀ ለ ሐ መ ሠ … ፀ ፈ ፐ.
"""
ETHIOPIC_START = 0x1200
ETHIOPIC_END = 0x137F
ORDER_SLOTS = 8


def base_of(ch):
    """Base fidel character of ``ch`` (e.g. ሁ→ሀ, ጨ→ጨ), or None if not Ethiopic."""
    if not ch:
        return None
    cp = ord(ch[0])
    if ETHIOPIC_START <= cp <= ETHIOPIC_END:
        return chr(ETHIOPIC_START + ((cp - ETHIOPIC_START) // ORDER_SLOTS) * ORDER_SLOTS)
    return None


def letter_of(word):
    """First fidel family of ``word`` (skips leading punctuation/spaces)."""
    for ch in word or '':
        base = base_of(ch)
        if base:
            return base
    return None


def family_order():
    """Every possible family base in the main Ethiopic block, in order."""
    span = ETHIOPIC_END - ETHIOPIC_START + 1
    return [chr(ETHIOPIC_START + i * ORDER_SLOTS) for i in range(span // ORDER_SLOTS)]
