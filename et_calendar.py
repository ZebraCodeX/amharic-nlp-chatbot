# -*- coding: utf-8 -*-
"""
et_calendar.py — Ethiopic (በኢትዮጵያ አቆጣጠር) calendar conversions & names.

Pure-stdlib Gregorian ⇄ Ethiopic conversion. The Ethiopic year starts on
Gregorian 11 September (Ethiopian New Year of year Y = Gregorian year Y+7),
has 12 months of exactly 30 days plus a short 13th month, ጳጉሜ (Pagume),
of 5 days (6 in a leap year). Used by ሕሳር to answer "ዛሬ ምን ቀን ነው?"
with the true Amharic date, week-day and era (ዓ.ም).

Functions:
    gregorian_to_ethiopic(y, m, d) -> (year, month 1..13, day)
    ethiopic_to_gregorian(y, m, d) -> (y, m, d)
    weekday(y, m, d)               -> Amharic week-day name for a Gregorian date
    ethiopic_year_leap(y)          -> True when ጳጉሜ has 6 days
    MONTHS / WEEKDAYS
"""

from datetime import date

# + this offset, date.toordinal() equals the Julian Day Number.
JDN_OFFSET = 1721425

MONTHS = ['መስከረም', 'ጥቅምት', 'ኅዳር', 'ታኅሣሥ', 'ጥር', 'የካቲት',
          'መጋቢት', 'ሚያዚያ', 'ግንቦት', 'ሰኔ', 'ሐምሌ', 'ነሐሴ', 'ጳጉሜ']

WEEKDAYS = ['ሰኞ', 'ማክሰኞ', 'ረቡዕ', 'ሐሙስ', 'አርብ', 'ቅዳሜ', 'እሑድ']

# Gregorian month names in Amharic (for the ዓለማዊ / ጎርጎርዮስ answer part).
GREGORIAN_MONTHS = ['ጃንዋሪ', 'ፌብሩዋሪ', 'ማርች', 'ኤፕሪል', 'ሜይ', 'ጁን',
                    'ጁላይ', 'ኦገስት', 'ሴፕቴምበር', 'ኦክቶበር', 'ኖቬምበር', 'ዲሴምበር']


def _jdn(y, m, d):
    """Julian Day Number of a Gregorian date (proleptic, integer, midnight)."""
    return date(y, m, d).toordinal() + JDN_OFFSET


def gregorian_to_jdn(y, m, d):
    return _jdn(y, m, d)


def jdn_to_gregorian(j):
    d = date.fromordinal(j - JDN_OFFSET)
    return d.year, d.month, d.day


def _new_year_jdn(eth_year):
    """Julian Day Number of the Ethiopian New Year day (መስከረም 1)."""
    return _jdn(eth_year + 7, 9, 11)


def gregorian_to_ethiopic(y, m, d):
    """Convert a Gregorian (y, m, d) to (eth_year, month 1..13, day)."""
    j = _jdn(y, m, d)
    lo, hi = 1, 10000
    while lo < hi:                                   # largest Y with New Year ≤ now
        mid = (lo + hi + 1) // 2
        if _new_year_jdn(mid) <= j:
            lo = mid
        else:
            hi = mid - 1
    year = lo
    days = j - _new_year_jdn(year)                   # 0-based day within the year
    if days >= 360:                                  # ጳጉሜ (13th month)
        return year, 13, days - 360 + 1
    return year, days // 30 + 1, days % 30 + 1


def ethiopic_to_gregorian(y, m, d):
    """Convert an Ethiopic (y, month 1..13, d) to a Gregorian (y, m, d)."""
    j = _new_year_jdn(y) + (m - 1) * 30 + (d - 1)
    return jdn_to_gregorian(j)


def _is_leap_gregorian(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def ethiopic_year_leap(eth_year):
    """True when ጳጉሜ has 6 days (the Ethiopian year spanning a Gregorian Feb 29)."""
    return _is_leap_gregorian(eth_year + 8)


def weekday(y, m, d):
    """Amharic week-day name of a *Gregorian* date (JDN ≡ 0 is ሰኞ/Monday)."""
    return WEEKDAYS[_jdn(y, m, d) % 7]