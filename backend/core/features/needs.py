"""What a feature must know before it looks anything up, and asking staff for what is missing.

A feature declares its details (`Detail`): found by an entity type's pattern (a reference),
picked by staff from the values the pack lists (`choose`), or a date. Its `Needs` say which:
details asked first, one at a time (which system to look in), then sets of details of which any
one complete set is enough (a reference; or a number and a date), which may depend on a detail
asked first (each system is searched by different details).

Staff are guided, one question at a time, in code:

1. what is asked first (the system), as buttons;
2. with several ways to find it and nothing given yet, how they want to find it ("Transaction
   reference" or "Phone number and date"), as buttons;
3. the values of that way, in words.

A value typed after its way was chosen can only be what was asked for: a ten-digit number is
the phone number when staff chose "Phone number and date", though an account number looks the
same. Staff who give everything at once are not asked again; but a value that could be two
details (a number that is a phone number or an account number) is never guessed: staff are
asked which, unless the way they chose, or the system they named, takes only one of them.

Everything here is code, no model: what a message gives is read by patterns, by the listed
values' names, and by a date reader; what is missing is worked out from the declaration, and the
question built from the details' labels and titles. A small model told "ask for what you need"
skips the question, asks for what it has, or guesses a value; a declaration is asked the same
way every time, and costs no model step.

What was asked last and the way chosen are kept with the details (`ASKED`, `WAY`), so the reply
is read against them.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from core.types import Detail, Feature

WANT = "To look this up I need {wanted}."
WHICH_ONE = "Which is it?"
HOW = "How would you like to find it?"
WHICH_IS = "Is {value} {options}?"
ASKED = "_asked"  # in the details: what was asked last (a detail, WAY_ASKED, WHICH_ASKED)
WAY = "_way"  # in the details: the way staff chose, its details joined by "+"
WAY_ASKED, WHICH_ASKED, VALUES_ASKED = "way", "which", "values"
MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        1,
    )
    for name in names
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"


@dataclass(frozen=True)
class Ask:
    """What to ask staff: the question; what is asked (a detail's name, or WAY_ASKED,
    WHICH_ASKED, VALUES_ASKED), kept to read the reply against; and for a choice, the options
    as (value, title), shown as buttons."""

    question: str
    asked: str
    choices: tuple[tuple[str, str], ...] = ()


def given(
    feature: Feature, text: str, entities: Mapping[str, str], today: date | None = None
) -> dict[str, str]:
    """The feature's details that `text` gives: detail name -> value. `entities`: the entities
    found in the text (type -> id). A value may be given for two details (a number fitting two
    patterns): `update` settles which."""
    found: dict[str, str] = {}
    for detail in feature.details:
        value = _value(detail, text, entities, today or date.today())
        if value is not None:
            found[detail.name] = value
    return found


def update(
    feature: Feature,
    known: Mapping[str, str],
    text: str,
    entities: Mapping[str, str],
    today: date | None = None,
) -> dict[str, str]:
    """The details `known`, with what `text` gives: read as the reply to what was asked last
    (the way to find it, or which detail a value is), then for any detail it gives."""
    known = dict(known)
    asked = known.pop(ASKED, None)
    if feature.needs is None:
        return known
    details = {d.name: d for d in feature.details}
    if asked == WAY_ASKED:
        ways = {_key(s): _way_title(s, details) for s in feature.needs.sets_for(known)}
        if (way := _named(text, ways)) is not None:
            known[WAY] = way
    elif asked == WHICH_ASKED and (clash := _clash(feature, known)) is not None:
        options = {name: _title(details[name]) for name in clash[1]}
        if (chosen := _named(text, options)) is not None:
            for name in clash[1]:
                if name != chosen:
                    known.pop(name, None)
    known.update(given(feature, text, entities, today))
    return _settled(feature, known)


def missing(feature: Feature, known: Mapping[str, str]) -> Ask | None:
    """What to ask for next, given the details `known`; None when the feature can look up."""
    needs = feature.needs
    if needs is None:
        return None
    details = {d.name: d for d in feature.details}
    for name in needs.first:
        if name not in known:
            return _ask_one(details[name])
    if (clash := _clash(feature, known)) is not None:
        value, names = clash
        options = " or ".join(details[name].label for name in names)
        choices = tuple((name, _title(details[name])) for name in names)
        return Ask(WHICH_IS.format(value=value, options=options), WHICH_ASKED, choices)
    sets = needs.sets_for(known)
    if not sets or any(all(name in known for name in s) for s in sets):
        return None
    chosen = [s for s in sets if _key(s) == known.get(WAY)]
    # Started on a set (a phone number given): only the sets it is part of, so what is asked
    # for goes with it ("the date"), not every other way ("the reference, or the date").
    started = [s for s in sets if any(name in known for name in s)]
    if not chosen and not started and len(sets) > 1:
        ways = tuple((_key(s), _way_title(s, details)) for s in sets)
        return Ask(HOW, WAY_ASKED, ways)
    wanted = _once(
        tuple(name for name in s if name not in known) for s in chosen or started or sets
    )
    phrases = [_and([details[name].label for name in names]) for names in wanted]
    return Ask(WANT.format(wanted=_or(phrases)), VALUES_ASKED)


def _settled(feature: Feature, known: dict[str, str]) -> dict[str, str]:
    """A value given for several details is kept only for those it can be: the ones in the way
    staff chose, or in a set that applies (USSD is not searched by account). If more than one
    remains, staff are asked (`missing`)."""
    assert feature.needs is not None
    sets = feature.needs.sets_for(known)
    way = next((s for s in sets if _key(s) == known.get(WAY)), None)
    applies = set(way) if way is not None else {name for s in sets for name in s}
    clash = _clash(feature, known)
    while clash is not None:
        _, names = clash
        keep = [name for name in names if name in applies] or list(names)
        if len(keep) == len(names):
            break
        for name in names:
            if name not in keep:
                known.pop(name)
        clash = _clash(feature, known)
    return known


def _clash(feature: Feature, known: Mapping[str, str]) -> tuple[str, list[str]] | None:
    """A value known for two or more details found by pattern, and those details."""
    by_value: dict[str, list[str]] = {}
    for detail in feature.details:
        if detail.entity is not None and detail.name in known:
            by_value.setdefault(known[detail.name], []).append(detail.name)
    return next(((v, names) for v, names in by_value.items() if len(names) > 1), None)


def _ask_one(detail: Detail) -> Ask:
    if detail.choose:
        return Ask(detail.ask or WHICH_ONE, detail.name, detail.choose)
    return Ask(detail.ask or WANT.format(wanted=detail.label), detail.name)


def _key(names: Sequence[str]) -> str:
    return "+".join(names)


def _title(detail: Detail) -> str:
    """The detail's name on a button: its title, else its label ("the reference": Reference)."""
    words = detail.title or re.sub(r"^the\s+", "", detail.label)
    return words[:1].upper() + words[1:]


def _way_title(names: Sequence[str], details: Mapping[str, Detail]) -> str:
    """A way on a button: "Phone number and date"."""
    titles = [_title(details[name]) for name in names]
    return _and([titles[0], *(t[:1].lower() + t[1:] for t in titles[1:])])


def _named(text: str, options: Mapping[str, str]) -> str | None:
    """The one option (value -> title) `text` names, by its title; None if none or several."""
    named = {value for value, title in options.items() if _names(text, title)}
    return named.pop() if len(named) == 1 else None


def _value(detail: Detail, text: str, entities: Mapping[str, str], today: date) -> str | None:
    if detail.entity is not None:
        return entities.get(detail.entity)
    if detail.choose:
        return _chosen(detail, text)
    if detail.date:
        return read_date(text, today, detail.nearest)
    if detail.period:
        return read_period(text, today, detail.nearest)
    return None


def _chosen(detail: Detail, text: str) -> str | None:
    """The one listed value the text names, by its title, its id or its other words; None if
    it names none, or more than one (that is staff's to say, not ours to guess)."""
    words = dict(detail.words)
    named = {
        value
        for value, title in detail.choose
        if any(_names(text, w) for w in (title, value.replace("_", " "), *words.get(value, ())))
    }
    return named.pop() if len(named) == 1 else None


def _names(text: str, words: str) -> bool:
    return bool(re.search(rf"(?i)(?<!\w){re.escape(words)}(?!\w)", text))


def read_date(text: str, today: date, nearest: bool = False) -> str | None:
    """The date `text` gives, as YYYY-MM-DD: 2026-10-11, 11/10/2026 (day first), 11 October,
    October 11, today, yesterday, tomorrow. A day and month with no year is the latest one not
    after today, or with `nearest` the one nearest today. None if it gives none, or one that is
    not a date."""
    lowered = text.lower()
    if re.search(r"\btoday\b", lowered):
        return today.isoformat()
    if re.search(r"\byesterday\b", lowered):
        return (today - timedelta(days=1)).isoformat()
    if re.search(r"\btomorrow\b", lowered):
        return (today + timedelta(days=1)).isoformat()
    if found := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lowered):
        year, month, day = (int(g) for g in found.groups())
        return _iso(year, month, day)
    if found := re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", lowered):
        day, month, year = (int(g) for g in found.groups())
        return _iso(year, month, day)
    found = re.search(rf"\b{_DAY}\s+(?:of\s+)?({_MONTH})\b\.?(?:,?\s+(\d{{4}}))?", lowered)
    if found:
        day, month, year = int(found[1]), MONTHS[found[2]], found[3]
    elif found := re.search(rf"\b({_MONTH})\.?\s+{_DAY}\b(?:,?\s+(\d{{4}}))?", lowered):
        day, month, year = int(found[2]), MONTHS[found[1]], found[3]
    else:
        return None
    return _in_year(day, month, year, today, nearest)


# Between the two ends of a period: "10-14", "10 to 14", "10 until 14".
_TO = r"\s*(?:-|–|\bto\b|\buntil\b|\btill\b|\bthrough\b)\s*"
_WORD_TO = r"\s+(?:to|until|till|through|–|-)\s+"  # between two whole dates


def read_period(text: str, today: date, nearest: bool = False) -> str | None:
    """The period `text` gives, as "YYYY-MM-DD/YYYY-MM-DD": "10 to 14 November", "10-14 Nov",
    "Nov 10-14", "from 10 Nov to 2 Dec", two dates in any form `read_date` reads, or one date
    (a single day). Without a year, the start is placed as `read_date` places it, and the end
    on or after it: in a later month of the next year (28 Dec to 3 Jan), never the same month a
    year on. None if it gives no date, or an end before the start."""
    lowered = text.lower()
    one_month = rf"\b{_DAY}{_TO}{_DAY}\s+(?:of\s+)?({_MONTH})\b\.?(?:,?\s+(\d{{4}}))?"
    if found := re.search(one_month, lowered):
        month = MONTHS[found[3]]
        start = _in_year(int(found[1]), month, found[4], today, nearest)
        return _period(start, _on_or_after(start, int(found[2]), month))
    month_first = rf"\b({_MONTH})\.?\s+{_DAY}{_TO}{_DAY}\b(?:,?\s+(\d{{4}}))?"
    if found := re.search(month_first, lowered):
        month = MONTHS[found[1]]
        start = _in_year(int(found[2]), month, found[4], today, nearest)
        return _period(start, _on_or_after(start, int(found[3]), month))
    halves = re.split(_WORD_TO, lowered, maxsplit=1)
    start = read_date(halves[0], today, nearest)
    if start is None:
        return None
    if len(halves) == 1:
        return _period(start, start)
    if re.search(r"\d{4}", halves[1]):
        end = read_date(halves[1], date.fromisoformat(start))
    else:  # read in the start's year, then placed after it
        end = _rolled(read_date(halves[1], date(int(start[:4]), 12, 31)), start)
    return _period(start, end or start)


def _period(start: str | None, end: str | None) -> str | None:
    if start is None or end is None or end < start:
        return None
    return f"{start}/{end}"


def _on_or_after(start: str | None, day: int, month: int) -> str | None:
    """The day of `month` on or after `start`: the end of a period given with one month."""
    if start is None:
        return None
    return _rolled(_iso(int(start[:4]), month, day), start)


def _rolled(end: str | None, start: str) -> str | None:
    """An end read in the start's year that falls before it: the next year's, if its month comes
    earlier in the year (28 Dec to 3 Jan); in the same month (14 to 10 Nov) it stays before the
    start, and the period is refused."""
    if end is None or end >= start or int(end[5:7]) >= int(start[5:7]):
        return end
    return _iso(int(end[:4]) + 1, int(end[5:7]), int(end[8:10]))


def _in_year(day: int, month: int, year: str | None, today: date, nearest: bool) -> str | None:
    """A day and month in `year`; without one, the latest not after `today`, or with
    `nearest` the one nearest today (last year's, this year's or next year's)."""
    if year is not None:
        return _iso(int(year), month, day)
    if nearest:
        options = [d for y in (-1, 0, 1) if (d := _iso(today.year + y, month, day)) is not None]
        return min(options, key=lambda d: abs(date.fromisoformat(d) - today), default=None)
    this_year = _iso(today.year, month, day)
    if this_year is not None and this_year <= today.isoformat():
        return this_year
    return _iso(today.year - 1, month, day)


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _once(items: Sequence[tuple[str, ...]]) -> list[tuple[str, ...]]:
    kept: list[tuple[str, ...]] = []
    for item in items:
        if item and item not in kept:
            kept.append(item)
    return kept


def _and(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _or(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])}, or {parts[-1]}"
