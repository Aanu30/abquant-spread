"""A note reader that understands days: today / tomorrow / the day after tomorrow and weekday names, in Finnish,
Swedish and English (RULES.md: a weekday name means that weekday 2 to 6 days after the request arrives; a time
without a day is on the arrival day). It extends the kit's same-day reader (spread.starter.window_from_note)."""
from __future__ import annotations

import re
from typing import Optional

from .env import ROOT  # noqa: F401
from spread.starter import AFTER, BEFORE, DELIVERY, RANGE, window_from_note

DAY = 1440
DAY_WORDS = [  # longest first
    (re.compile(r"ylihuomenna|i övermorgon|övermorgon|day after tomorrow"), 2),
    (re.compile(r"huomenna|huom\.|i morgon|imorgon|tomorrow|tmrw|tmr\b|tomorow|tommorow"), 1),
    (re.compile(r"tänään|idag|today|tänä päivänä"), 0),
]
WEEKDAYS = [
    (0, r"maanantai\w*|\bma\b\.?|måndag\w*|\bmån\b\.?|monday|\bmon\b\.?"),
    (1, r"tiistai\w*|\bti\b\.?|tisdag\w*|\btis\b\.?|tuesday|\btue\b\.?|\btues\b\.?"),
    (2, r"keskiviikko\w*|\bke\b\.?|onsdag\w*|\bons\b\.?|wednesday|\bwed\b\.?"),
    (3, r"torstai\w*|\bto\b\.?|torsdag\w*|\btors\b\.?|thursday|\bthu\b\.?|\bthurs\b\.?"),
    (4, r"perjantai\w*|\bpe\b\.?|fredag\w*|\bfre\b\.?|friday|\bfri\b\.?"),
    (5, r"lauantai\w*|\bla\b\.?|lördag\w*|\blör\b\.?|saturday|\bsat\b\.?"),
]
WEEKDAY_RE = [(d, re.compile(p)) for d, p in WEEKDAYS]
# a clock time: "klo 14", "kl. 14.30", "14:30", "1 pm", "2pm", "11.30"
CLOCK = re.compile(r"(?:klo|kl\.?)\s*(\d{1,2})(?:[.:]?(\d{2}))?|\b(\d{1,2})[.:](\d{2})\b|\b(\d{1,2})\s*(am|pm)\b")
# direction cues, read over a wider span than the kit's; "not (ready) before X" and payment holds mean from X on
AFTER2 = re.compile(r"jälkeen|jäleken|alkaen|aikaisintaan|vasta|valmis|noudettavissa|maksu|maksettu|after|from|earliest|"
                    r"not before|not ready|no pickup before|not befroe|ready|released|paid|payment|clears|ei ennen|efter|"
                    r"tidigast|inte före|klar|betal|först")
CORRECT = re.compile(r"correction|korjaus|rättelse|oops|sorry|tarkoitin|i mean|menar")
DENY = re.compile(r"(?:\bnot|\bei|\binte|\bnej)\s*$")


def _clock(m) -> Optional[int]:
    if m.group(5):
        h = int(m.group(5)) % 12 + (12 if m.group(6) == "pm" else 0)
        mi = 0
    else:
        h = int(m.group(1) or m.group(3))
        mi = int(m.group(2) or m.group(4) or 0)
        tail = m.string[m.end():m.end() + 4]
        if re.match(r"\s*pm", tail) and h < 12:
            h += 12
    if h > 24 or mi > 59:
        return None
    return h * 60 + mi


def _day_offset(context: str, arrived: int) -> Optional[int]:
    for rx, off in DAY_WORDS:
        if rx.search(context):
            return off
    dow_arr = (arrived // DAY) % 7
    for d, rx in WEEKDAY_RE:
        if rx.search(context):
            off = (d - dow_arr) % 7
            if off < 2:
                off += 7
            return off if off <= 6 else None
    return None


def note_times(text: str, arrived: int) -> list:
    """[(absolute minute, 'after' | 'before')] for each clock time with a direction, the day read from its context."""
    t = RANGE.sub(" ", text.lower())
    out = []
    for m in CLOCK.finditer(t):
        mins = _clock(m)
        if mins is None:
            continue
        before_txt = t[max(0, m.start() - 40):m.start()]
        if DENY.search(before_txt) and not re.search(r"(not|ei|inte)\s*(before|ennen|före)\s*$", before_txt):
            continue  # "not 14:30": a denied time
        off = _day_offset(t[max(0, m.start() - 40):m.end() + 12], arrived)
        day = arrived // DAY + (off or 0)
        near = t[max(0, m.start() - 45):m.end() + 16]
        if CORRECT.search(t[max(0, m.start() - 30):m.start()]) and out:
            out[-1] = (day * DAY + mins, out[-1][1])  # a correction replaces the time before it
            continue
        if AFTER2.search(near):
            out.append((day * DAY + mins, "after"))
        elif BEFORE.search(near):
            out.append((day * DAY + mins, "before"))
    return out


def window(note: Optional[dict], base: dict, stop: str, arrived: int) -> dict:
    """The kit's window, then narrowed by day-aware times. Never wider than the kit's."""
    w = window_from_note(note, base, stop)
    if not note:
        return w
    text = note["text"].lower()
    if bool(DELIVERY.search(text)) != (stop == "delivery"):
        return w
    start, end = w["from"], w["to"]
    times = note_times(text, arrived)
    afters = [m for m, k in times if k == "after"]
    befores = [m for m, k in times if k == "before"]
    if stop == "pickup" and afters:
        start = max(start, max(afters))  # a correction comes last; the latest "from" is the safe one
    if stop == "delivery" and befores:
        end = min(end, min(befores))
    if start > end:
        return w if stop == "delivery" else {"from": start, "to": max(start, w["to"])}
    return {"from": start, "to": end}
