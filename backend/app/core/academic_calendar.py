"""
School term calendar.

Attendance records only carry a date, so term-scoped queries map a term name
to a date window. The windows follow the Kenyan three-term year and together
cover the whole calendar year, so every date belongs to exactly one term
(holidays fall into the term they follow).
"""

from datetime import date

# term name -> ((start month, start day), (end month, end day))
TERM_WINDOWS = {
    "Term 1": ((1, 1), (4, 30)),
    "Term 2": ((5, 1), (8, 31)),
    "Term 3": ((9, 1), (12, 31)),
}


def term_date_range(term: str, academic_year: str) -> tuple[date, date]:
    """Return the inclusive (start, end) dates of a term. Raises ValueError if unknown."""
    if term not in TERM_WINDOWS:
        raise ValueError(f"Unknown term '{term}'. Expected one of: {', '.join(TERM_WINDOWS)}.")
    try:
        year = int(academic_year)
    except (TypeError, ValueError):
        raise ValueError(f"Academic year must be a number, got '{academic_year}'.")

    (start_month, start_day), (end_month, end_day) = TERM_WINDOWS[term]
    return date(year, start_month, start_day), date(year, end_month, end_day)


def term_for_date(day: date) -> tuple[str, str]:
    """Return the (term, academic_year) a date falls in."""
    for term, ((sm, sd), (em, ed)) in TERM_WINDOWS.items():
        if date(day.year, sm, sd) <= day <= date(day.year, em, ed):
            return term, str(day.year)
    raise ValueError(f"No term covers {day}.")  # unreachable while windows cover the year
