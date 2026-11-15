"""Reads a dealer's note (Finnish, Swedish or English) into the facts the world acts on.

The rules for days and times are in RULES.md: a time without a day is on the arrival day; "huomenna / i morgon /
tomorrow" is the next day; a weekday name is that weekday 2 to 6 days after arrival; digits are a 24-hour clock unless
am or pm follows; an hour in words is a working hour from 9 to 17, and "half three" is 14:30; a correction replaces
the time before it, and a denied time ("not 3pm") does not count.

`python -m abquant.notes` scores the reader against what the reveals say each note meant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

DAY = 24 * 60


@dataclass
class Facts:
    pickup_from: Optional[int] = None      # world minute from which the car can be collected (ready, or released after payment)
    pickup_open: Optional[int] = None      # the pickup site's real hours, minutes of the day
    pickup_close: Optional[int] = None
    delivery_open: Optional[int] = None    # the delivery site's real hours
    delivery_close: Optional[int] = None
    deadline: Optional[int] = None         # a tighter deadline, world minute
    manual: bool = False
    plates: bool = False
    summer_tyres: bool = False
    times: int = 0                         # clock times and ranges found
    used: int = 0                          # ... of which the reader gave a meaning

    @property
    def unsure(self) -> bool:
        return self.used < self.times


MANUAL = re.compile(r"manuaal|manuell|\bmanual\b|käsivaih|kasivaih|stick shift|keppi")
NOT_MANUAL = re.compile(r"(ei|not|inte|no)\s+(ole\s+)?(a\s+)?manua|automaatti,?\s+ei\s+manua")
PLATES = re.compile(r"ilman kilp|ei kilp|kilvet poist|kilvet puuttu|kilvet pois|kilvet irrot|ei rekkar|rekkarit puuttu|ilman rekkar|koekilv|siirtokilv|"
                    r"no plates|without plates|plates removed|plates off|unregistered|trade plates|not registered|utan skylt|saknar skylt|inga skylt|"
                    r"skyltar\w* borttag|skyltar\w* avtag|oregistrer|provskylt|rekisteröimät|rekisteroimat|ei rekisterikilp")
TYRES_ON = re.compile(r"kes[äa]renk\w*\s+alla|kes[äa]renkail|talvirenkaita ei|ei talvirenk|talvirenkaat vaihtamatta|"
                      r"on summer|summer tyres on|summers? still on|still on summer|no winter tyres|winter tyres not|sommardäck på|inga vinterdäck|på sommardäck|"
                      r"kes[äa]kumit alla|kes[äa]kumeilla")
DELIVERY = re.compile(r"kohde|kohtee|vastaanot|toimitus|toimite|perill|destination|deliver|arriv|receiv|drop.?off|leveran|levere|mottag|framme|m[åa]let|"
                      r"asiakas nouta|asiakas tulee|customer picks|customer collects|kunden h[äa]mtar|must be there|be there by|oltava silloin")
IGNORE = re.compile(r"myyj[äa] paikalla|myyj[äa] kotona|asiakas kotona|asiakas paikalla|seller (is )?(at )?home|customer (is )?(at )?home|s[äa]ljaren hemma|kunden hemma")
NOT_BEFORE = re.compile(r"ei ennen|not before|inte f[öo]re|no pickup before|ej f[öo]re")
FROM = re.compile(r"aikaisint|earliest|alkaen|l[äa]htien|j[äa]lkeen|\bafter\b|\bfrom\b|\befter\b|tidigast|f[öo]rst\b|valmis|\bready\b|\bklar\b|\bvasta\b|"
                  r"\bsaa\b|released|luovut|handover|hand over|pays first|pays|maksaa|maksun|betalar|payment clears|clears|betal|voi noutaa|voi hakea|can be collected|"
                  r"kan h[äa]mtas|noudettavissa|haettavissa|won'?t be ready|not ready")
CLOSE = re.compile(r"kiinni|sulke|sulje|\bclose|st[äa]ng|\basti\b|saakka|until|\btill\b|ei en[äa][äa]|ei ket[äa][äa]n|nobody|no one|ingen")
UNTIL = re.compile(r"ennen|menness[äa]|viim|\bbefore\b|\bby\b|latest|f[öo]re|senast|oltava|must be|m[åa]ste")
MUST_ARRIVE = re.compile(r"viim|menness[äa]|\bby\b|latest|senast|oltava|must|m[åa]ste|silloin|nouta|tulee|picks|collects|h[äa]mtar")
CORRECTION = re.compile(r"correction|korjaus|eikun|ei kun|\bsiis\b|tarkoitan|r[äa]ttelse|jag menar|i mean|sorry|anteeksi|\boho\b")
DENIED = re.compile(r"\b(not|ei|inte|ej)\s+(klo\s+|kl\s+|at\s+)?$")

TODAY = re.compile(r"t[äa]n[äa][äa]n|\bidag\b|\btoday\b")
TOMORROW = re.compile(r"\bhuomenna\b|\bi\s?morgon\b|\bimorron\b|\btomorrow\b|\btmrw\b|\btmr\b")
AFTER_TOMORROW = re.compile(r"ylihuomenna|i\s?[öo]vermorgon|day after tomorrow")
WEEKDAY_RE = [re.compile(p) for p in (
    r"maanantai\w*|\bma\b|m[åa]ndag\w*|\bm[åa]n\b|monday|\bmon\b",
    r"tiistai\w*|\bti\b|tisdag\w*|\btis\b|tuesday|\btues?\b",
    r"keskiviik\w*|\bke\b|onsdag\w*|\bons\b|wednesday|\bweds?\b",
    r"torstai\w*|\bto\b|torsdag\w*|\btors\b|thursday|\bthu\b|\bthurs?\b",
    r"perjantai\w*|\bpe\b|fredag\w*|\bfre\b|friday|\bfri\b",
    r"lauantai\w*|\bla\b|l[öo]rdag\w*|\bl[öo]r\b|saturday|\bsat\b",
    r"sunnuntai\w*|\bsu\b|s[öo]ndag\w*|\bs[öo]n\b|sunday|\bsun\b")]

# an hour in words is the working hour with that number, 9 to 17 (RULES.md): "two" is 14:00
HOUR_STEMS = [("yksitoista", 11), ("yhdeltätoista", 11), ("kaksitoista", 12), ("kahdeltatoista", 12), ("yhdeks", 9), ("kymmen", 10),
              ("yhde", 13), ("yhte", 13), ("yht", 13), ("yks", 13), ("kahde", 14), ("kahte", 14), ("kaht", 14), ("kaks", 14), ("kolm", 15), ("nelj", 16), ("viide", 17), ("viite", 17), ("viit", 17), ("viis", 17),
              ("elva", 11), ("tolv", 12), ("nio", 9), ("tio", 10), ("ett", 13), ("två", 14), ("tva", 14), ("tre", 15), ("fyra", 16), ("fem", 17),
              ("eleven", 11), ("twelve", 12), ("noon", 12), ("nine", 9), ("ten", 10), ("one", 13), ("two", 14), ("three", 15), ("four", 16), ("five", 17)]
FI_HOUR = r"(?:\w*toista|yhdeks\w*|kymmen\w*|yhde\w*|yhte\w*|yht[äa]|kahde\w*|kahte\w*|kahta|kolme\w*|nelj\w*|viide\w*|viite\w*|viitt[äa])"
OTHER_HOUR = r"(?:ett|två|tva|tre|fyra|fem|nio|tio|elva|tolv|one|two|three|four|five|nine|ten|eleven|twelve|noon)"
ANY_HOUR = "(" + FI_HOUR + "|" + OTHER_HOUR + ")"
RANGE = re.compile(r"(?<![\d:])(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|to|till)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?![\d:])")
CLOCK = re.compile(r"\b(?:klo|kl|at)\s*(\d{1,2})(?::(\d{2}))?(?!\d)\s*(am|pm)?|(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])\s*(am|pm)?|(?<![\d:.])\b(\d{1,2})\s*(am|pm)\b")
HALF = re.compile(r"\b(?:puoli|halv|half)\s+" + ANY_HOUR)
WORD_CLOCK = re.compile(r"\b(?:klo|kl|at|by|ennen|viim\w*|vid|f[öo]re|efter|before|after|until|till|senast)\s+" + ANY_HOUR + r"\b"
                        r"|\b(" + FI_HOUR + r")\b(?=\s+(?:j[äa]lkeen|menness[äa]|asti|saakka|alkaen))"
                        r"|\b(yhdelt[äa]\w*|kahdelta\w*|kolmelta|nelj[äa]lt[äa]|viidelt[äa]|yhdeks[äa]lt[äa]|kymmenelt[äa])\b|\b(noon)\b")
ABBREV = re.compile(r"\b(viim|klo|kl|n|ma|ti|ke|to|pe|la|su|mån|man|tis|ons|tors|fre|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|esim|ref|nro|puh|tel|t)\.")

# words worth recognising through a typo: day words and the cues above
VOCAB = ["huomenna", "ylihuomenna", "tomorrow", "imorgon", "tänään", "today", "maanantai", "maanantaina", "tiistai", "tiistaina", "keskiviikko", "keskiviikkona",
         "torstai", "torstaina", "perjantai", "perjantaina", "lauantai", "lauantaina", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
         "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "vastaanotto", "vastaanottava", "mottagning", "destination", "toimitus", "toimitusosoite",
         "perillä", "closes", "kiinni", "sulkee", "correction", "korjaus", "manuaali", "manuell", "manual", "manuaalivaihteinen", "manuaalivaihteet",
         "kesärenkaat", "kesärenkailla", "sommardäck", "summer", "talvirenkaita", "valmis", "aikaisintaan", "viimeistään", "mennessä", "jälkeen", "alkaen",
         "earliest", "latest", "before", "after", "until", "nouto", "noutaa", "haettava", "pickup", "collect", "arkisin", "weekdays", "vardagar", "receiving",
         "delivery", "deliver", "kilvet", "rekisterikilvet", "plates", "ready", "framme", "senast", "customer", "asiakas"]
VOCAB_SET = set(VOCAB)


def edits(a: str, b: str, limit: int) -> int:
    """Optimal-string-alignment distance (insert, delete, substitute, swap two neighbours), cut off above `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


_canon_cache: dict = {}


def canon(word: str) -> str:
    """A word within one typo (two for long words) of a word we know becomes that word."""
    if word in VOCAB_SET or len(word) < 5:
        return word
    if word not in _canon_cache:
        best = word
        for v in VOCAB:
            if v[0] == word[0] and edits(word, v, 1 if len(v) < 8 else 2) <= (1 if len(v) < 8 else 2):
                best = v
                break
        _canon_cache[word] = best
    return _canon_cache[word]


def word_hour(word: str) -> Optional[int]:
    if word.endswith("toista"):                     # yksitoista, kahdeltatoista, yhdentoista ...
        return 11 if word.startswith("y") else 12 if word.startswith("ka") else None
    for stem, hour in HOUR_STEMS:
        if word.startswith(stem):
            return hour
    return None


def day_of(text: str, arrival_day: int) -> Optional[int]:
    if AFTER_TOMORROW.search(text):
        return arrival_day + 2
    if TOMORROW.search(text):
        return arrival_day + 1
    if TODAY.search(text):
        return arrival_day
    for weekday, pattern in enumerate(WEEKDAY_RE):
        if pattern.search(text):
            offset = (weekday - arrival_day) % 7
            return arrival_day + (offset if offset >= 2 else offset + 7)
    return None


def ampm(hour: int, tag: Optional[str]) -> int:
    if tag == "pm" and hour < 12:
        return hour + 12
    if tag == "am" and hour == 12:
        return 0
    return hour


def clocks(clause: str) -> list:
    """(start, minutes of the day, end) for each clock time that is not denied."""
    out = []
    for m in HALF.finditer(clause):
        hour = word_hour(m.group(1))
        if hour:
            out.append((m.start(), hour * 60 - 30, m.end()))
    for m in WORD_CLOCK.finditer(clause):
        word = next((g for g in m.groups() if g), None)
        hour = word_hour(word) if word else None
        if hour and not any(a < m.end() and m.start() < b for a, _, b in out):
            out.append((m.start(), hour * 60, m.end()))
    for m in CLOCK.finditer(clause):
        hour = ampm(int(m.group(1) or m.group(4) or m.group(7)), m.group(3) or m.group(6) or m.group(8))
        minute = int(m.group(2) or m.group(5) or 0)
        if hour > 24 or minute > 59 or any(a < m.end() and m.start() < b for a, _, b in out):
            continue
        out.append((m.start(), hour * 60 + minute, m.end()))
    return sorted(c for c in out if not DENIED.search(clause[:c[0]]))


def normalise(text: str) -> str:
    text = text.lower().replace("kello", "klo").replace("–", "-").replace("—", "-")
    text = re.sub(r"\b\d{5,}\b", " ", text)                                   # reference and phone numbers
    text = re.sub(r"\((?:ei|not|inte|ej)\b[^)]*\)", " ", text)                # a denied day or time in brackets
    text = re.sub(r"(\d)[.](\d{2})(?!\d)", r"\1:\2", text)                     # 13.30 -> 13:30, so a full stop ends a sentence
    text = re.sub(r"\b(klo|kl)\s*(\d{1,2})(\d{2})\b", r"\1 \2:\3", text)       # klo 1400
    text = re.sub(r"(\d{1,2}):st[äa]\s+(\d{1,2}):(?:[äa]+n|t?een)", r"\1-\2", text)      # 10:stä 17:ään
    text = re.sub(r"(\d{1,2}):(?:[äa]+n|t?een|lt[äa])\b", r"\1", text)                       # 16:een asti
    text = ABBREV.sub(r"\1", text)
    text = re.sub(r"\b(ma|mon|mån|man)\s*-\s*(pe|fri|fre)\b", " arkisin ", text)   # Mon-Fri is not a day
    text = re.sub(r"[a-zåäö]{5,}", lambda m: canon(m.group()), text)
    # a bare hour next to a time word: "ennen 18", "12 mennessä", "by 4"
    text = re.sub(r"\b(ennen|viimeistään|viim|senast|före|efter|after|before|by|until|till|from|jälkeen)\s+(\d{1,2})(?![\d:])(?!\s*(?:min|h\b|km|kpl|reng|päiv|pv|dag|day|tun))", r"\1 klo \2", text)
    text = re.sub(r"(?<![\d:])\b(\d{1,2})\s+(mennessä|jälkeen|alkaen|asti|saakka)\b", r"klo \1 \2", text)
    return text


def read(note: Optional[dict], arrived_at: int) -> Facts:
    facts = Facts()
    if not note or not note.get("text"):
        return facts
    text = normalise(note["text"])
    facts.manual = bool(MANUAL.search(text)) and not NOT_MANUAL.search(text)
    facts.plates = bool(PLATES.search(text))
    facts.summer_tyres = bool(TYRES_ON.search(text))
    arrival_day = arrived_at // DAY
    last = None                                   # the last dated fact: ("from" | "deadline", day, minute)
    for sentence in re.split(r"[.!?;/\n]+", text):
        corrected = bool(CORRECTION.search(sentence))
        for clause in sentence.split(","):
            clause = clause.strip()
            if not clause:
                continue
            is_delivery = bool(DELIVERY.search(clause))
            ranges = []
            for m in RANGE.finditer(clause):
                opens = ampm(int(m.group(1)), m.group(3) or (m.group(6) if m.group(6) == "am" else None)) * 60 + int(m.group(2) or 0)
                closes = ampm(int(m.group(4)), m.group(6)) * 60 + int(m.group(5) or 0)
                if 4 * 60 <= opens < closes <= DAY:
                    ranges.append((m.start(), opens, closes, m.end()))
            singles = [c for c in clocks(clause) if not any(a < c[2] and c[0] < b for a, _, _, b in ranges)]
            facts.times += len(ranges) + len(singles)
            if IGNORE.search(clause):
                facts.used += len(ranges) + len(singles)        # a seller's hours at home: no effect on the sites
                continue
            for _, opens, closes, _ in ranges[:1]:
                if is_delivery:
                    facts.delivery_open, facts.delivery_close = opens, closes
                else:
                    facts.pickup_open, facts.pickup_close = opens, closes
                facts.used += 1
            day = day_of(clause, arrival_day)
            if corrected and last and not singles and day is not None and last[0] in ("from", "deadline"):
                role, _, minute = last                          # "Correction: Friday" moves the day and keeps the time
                last = (role, day, minute)
                if role == "from":
                    facts.pickup_from = day * DAY + minute
                else:
                    facts.deadline = day * DAY + minute
                continue
            if not singles:
                continue
            minute = singles[-1][1] if corrected else singles[0][1]
            cue = NOT_BEFORE.search(clause) or FROM.search(clause) or UNTIL.search(clause) or CLOSE.search(clause)
            if corrected and last and not cue:
                role = last[0]                                  # "Correction: 4pm" replaces the time before it
                day = day if day is not None else last[1]
            elif is_delivery:
                role = "delivery_close" if CLOSE.search(clause) else "deadline" if MUST_ARRIVE.search(clause) else "delivery_open" if FROM.search(clause) else None
            elif NOT_BEFORE.search(clause):
                role = "from"
            elif CLOSE.search(clause):
                role = "pickup_close"
            elif FROM.search(clause):
                role = "from"
            elif UNTIL.search(clause):
                role = "pickup_close"
            else:
                role = None
            if role is None:
                continue
            facts.used += len(singles)
            if role in ("from", "deadline"):
                day = day if day is not None else arrival_day
                last = (role, day, minute)
                if role == "from":
                    facts.pickup_from = day * DAY + minute
                else:
                    facts.deadline = day * DAY + minute
            elif role == "delivery_close":
                facts.delivery_close = minute
                last = (role, None, minute)
            elif role == "delivery_open":
                facts.delivery_open = minute
            else:
                facts.pickup_close = minute
                last = (role, None, minute)
    return facts


def score() -> None:
    """Compares the reader with the truth in every revealed week."""
    import json
    from collections import Counter, defaultdict

    from .fit import load_worlds

    right, wrong, examples = Counter(), Counter(), defaultdict(list)
    seen = set()
    for _, _, path in load_worlds():
        d = json.load(open(path))
        requests = {rr["request"]["id"]: rr["request"] for rr in d["reveal"]["requests"]}
        for order in d["reveal"]["orders"]:
            r = requests.get(order["orderId"])
            if not r or not r.get("note"):
                continue
            text = r["note"]["text"]
            f = read(r["note"], r["arrivedAt"])
            for i, t in enumerate(order["legs"]):
                leg = r["legs"][i]
                key = (text, r["arrivedAt"] // DAY % 7, i)
                first = key not in seen
                seen.add(key)

                def check(name: str, ok: bool, detail: str) -> None:
                    (right if ok else wrong)[name] += 1
                    if not ok and first and len(examples[name]) < 6:
                        examples[name].append(f"{text!r} -> {detail}")

                true_from = max(t["readyAt"], t["releasedAt"] or 0)
                later = true_from > leg["pickup"]["window"]["from"]
                if i == 0:
                    if later:
                        check("pickup_from", f.pickup_from == true_from, f"read {f.pickup_from}, true {true_from}, arrived {r['arrivedAt']}")
                    else:
                        check("no pickup_from", f.pickup_from is None or f.pickup_from <= leg["pickup"]["window"]["from"], f"read {f.pickup_from}, window from {leg['pickup']['window']['from']}")
                    ph, th = leg["pickup"]["hours"], t["pickupHours"]
                    if ph and th:
                        opens = max(ph["opens"], f.pickup_open) if f.pickup_open is not None else ph["opens"]
                        closes = min(ph["closes"], f.pickup_close) if f.pickup_close is not None else ph["closes"]
                        name = "pickup hours changed" if (th["opens"], th["closes"]) != (ph["opens"], ph["closes"]) else "pickup hours same"
                        check(name, (opens, closes) == (th["opens"], th["closes"]), f"read {opens}-{closes}, true {th['opens']}-{th['closes']}, stated {ph['opens']}-{ph['closes']}")
                dh, th = leg["delivery"]["hours"], t["deliveryHours"]
                if dh and th and i == len(order["legs"]) - 1:
                    opens = max(dh["opens"], f.delivery_open) if f.delivery_open is not None else dh["opens"]
                    closes = min(dh["closes"], f.delivery_close) if f.delivery_close is not None else dh["closes"]
                    name = "delivery hours changed" if (th["opens"], th["closes"]) != (dh["opens"], dh["closes"]) else "delivery hours same"
                    check(name, (opens, closes) == (th["opens"], th["closes"]), f"read {opens}-{closes}, true {th['opens']}-{th['closes']}, stated {dh['opens']}-{dh['closes']}")
                if t["noteDeadline"] is not None:
                    check("deadline", f.deadline == t["noteDeadline"], f"read {f.deadline}, true {t['noteDeadline']}, arrived {r['arrivedAt']}")
                else:
                    check("no deadline", f.deadline is None, f"read {f.deadline}")
                check("manual" if t["manualGearbox"] else "not manual", f.manual == t["manualGearbox"], f"read {f.manual}")
                check("plates" if t["needsPlates"] else "no plates", f.plates == t["needsPlates"], f"read {f.plates}")
                check("summer tyres" if t["summerTyres"] else "no summer tyres", f.summer_tyres == t["summerTyres"], f"read {f.summer_tyres}")
    for name in sorted(set(right) | set(wrong)):
        n = right[name] + wrong[name]
        print(f"{name:24} {right[name]:6d} / {n:6d}  {right[name] / n:6.1%}")
        for e in examples[name]:
            print("      " + e)


if __name__ == "__main__":
    score()
