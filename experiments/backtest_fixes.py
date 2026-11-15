"""Backtest of the driver-side fixes against the bot that played the final, from data/runs.jsonl and the logs.
No server. Writes BACKTEST_FIXES.md and prints the summary.

  python backtest_fixes.py
"""
import collections
import glob
import json
import statistics as st

RUNS = collections.defaultdict(dict)
for line in open("data/runs.jsonl", encoding="utf-8"):
    r = json.loads(line)
    RUNS[r["tag"]][r["seed"]] = r                     # the latest run of a seed under a tag

# the bot that played the final (f3), by seed, from the tags it was played under
BASE = {}
for tag in ("fb_xc20", "fb_wxc20", "fb_f3r", "fb_yf3", "fb_xb"):
    BASE.update(RUNS.get(tag, {}))
BASE_TAG = {s: tag for tag in ("fb_xc20", "fb_wxc20", "fb_f3r", "fb_yf3", "fb_xb") for s in RUNS.get(tag, {})}

FIXES = [
    ("Three cars: a one-way pair takes a third car", "triple=1", ["fb_ytri"]),
    ("Three cars, round trips too", "triple=1 triple_rt=1", ["fb_ytrirt", "fb_xtrirt", "fb_atrirt"]),
    ("Three cars, opening fee 0.65", "triple=1 triple_open=0.65", ["fb_ytri65"]),
    ("Long hauls wait for a partner", "pool_long=400", ["fb_ylong"]),
    ("Long haul takes a partner that is waiting", "pool_long=400 pool_long_now=1", ["fb_ylnow"]),
]


def key(seed):
    return (seed.rstrip("0123456789"), int(seed.lstrip("abcdefghijklmnopqrstuvwxyz")))


def alone_share(tag, seeds):
    """Cars delivered that were never in a pair or a three, per week, from the logs."""
    cars = alone = 0
    for seed in seeds:
        paths = glob.glob(f"logs/{tag}__{seed}__*.jsonl")
        if not paths:
            return None
        for line in open(sorted(paths)[-1], encoding="utf-8"):
            r = json.loads(line)
            if r.get("kind") == "result":
                cars += 1
                alone += not r["pair"]
    return alone / max(1, len(seeds)), alone / max(1, cars)


def stats(rows):
    m = [r["margin"] for r in rows]
    led = collections.Counter()
    for r in rows:
        for k, v in r["ledger"].items():
            led[k] += v
    n = len(rows)
    return {
        "n": n, "margin": st.mean(m), "sd": st.stdev(m) if n > 1 else 0.0, "won": st.mean(r["won"] for r in rows),
        "ontime": st.mean(r["ontime"] for r in rows), "worst": min(r["ontime"] for r in rows),
        "u92": sum(1 for r in rows if r["ontime"] < 0.92), "u90": sum(1 for r in rows if r["ontime"] < 0.90),
        "revenue": led["revenue"] / n, "fees": -led["driver_fee"] / n,
        "refunds": -(led["late_refund"] + led.get("undelivered_penalty", 0)) / n,
        "low": min(m), "high": max(m),
    }


def paired(new, seeds):
    d = [new[s]["margin"] - BASE[s]["margin"] for s in seeds]
    se = st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else float("nan")
    return st.mean(d), se, sum(1 for x in d if x > 0), d


def main():
    out = ["# Backtest of the driver-side fixes", "",
           "Sunday 15 Nov, after the final. Every row is the same practice weeks played twice, once by the bot that played the "
           "final and once with the fix (the world is the same for a seed, so the difference is the fix). Level 8, stepped "
           "practice weeks. None of the fixes was in the final.", ""]
    out += ["## All fixes", "",
            "| Version | Weeks | Margin / week | Against the played bot (se) | Weeks better | Cars won | On time | Worst week | Weeks under 92% / 90% | Cars alone / week |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    summary = []
    for name, setting, tags in FIXES:
        new = {}
        for tag in tags:
            new.update(RUNS.get(tag, {}))
        seeds = sorted((s for s in new if s in BASE), key=key)
        if not seeds:
            continue
        s_new, s_base = stats([new[s] for s in seeds]), stats([BASE[s] for s in seeds])
        diff, se, better, d = paired(new, seeds)
        tag_of = {s: tag for tag in tags for s in RUNS.get(tag, {})}
        a_new = collections.Counter(); a_base = collections.Counter()
        alone_new = alone_base = None
        try:
            cars = alone = bcars = balone = 0
            for s in seeds:
                for which, tg in (("new", tag_of[s]), ("base", BASE_TAG[s])):
                    paths = glob.glob(f"logs/{tg}__{s}__*.jsonl")
                    for line in open(sorted(paths)[-1], encoding="utf-8"):
                        r = json.loads(line)
                        if r.get("kind") == "result":
                            if which == "new":
                                cars += 1; alone += not r["pair"]
                            else:
                                bcars += 1; balone += not r["pair"]
            alone_new, alone_base = alone / len(seeds), balone / len(seeds)
        except (IndexError, KeyError):
            alone_new = alone_base = None                  # the raw run logs are not here: leave the column empty
        summary.append((name, setting, seeds, s_new, s_base, diff, se, better, d, alone_new, alone_base, new))
        out.append(f"| The bot that played, on the same weeks | {s_base['n']} | {s_base['margin']:,.0f} | | | {s_base['won']:.0f} | {s_base['ontime']:.1%} | "
                   f"{s_base['worst']:.1%} | {s_base['u92']} / {s_base['u90']} | {alone_base:.0f} |" if alone_base is not None else
                   f"| The bot that played, on the same weeks | {s_base['n']} | {s_base['margin']:,.0f} | | | {s_base['won']:.0f} | {s_base['ontime']:.1%} | {s_base['worst']:.1%} | {s_base['u92']} / {s_base['u90']} | |")
        out.append(f"| **{name}** (`{setting}`) | {s_new['n']} | {s_new['margin']:,.0f} | {diff:+,.0f} ({se:,.0f}) | {better} of {len(seeds)} | {s_new['won']:.0f} | "
                   f"{s_new['ontime']:.1%} | {s_new['worst']:.1%} | {s_new['u92']} / {s_new['u90']} | " + (f"{alone_new:.0f} |" if alone_new is not None else "|"))
        print(f"{name:<46} n={len(seeds):3d}  {s_new['margin']:>7,.0f} vs {s_base['margin']:>7,.0f}  diff {diff:+6,.0f} (se {se:,.0f})  better {better}/{len(seeds)}  "
              f"won {s_new['won']:.0f} vs {s_base['won']:.0f}  on time {s_new['ontime']:.2%} vs {s_base['ontime']:.2%}  worst {s_new['worst']:.1%} vs {s_base['worst']:.1%}  "
              f"under 92%: {s_new['u92']} vs {s_base['u92']}  under 90%: {s_new['u90']} vs {s_base['u90']}  alone {alone_new} vs {alone_base}")
    out.append("")

    # the fix that works, in detail
    name, setting, seeds, s_new, s_base, diff, se, better, d, alone_new, alone_base, new = next(x for x in summary if "round trips too" in x[0])
    out += [f"## The best of them: {name.lower()} (`{setting}`)", "",
            "| | The bot that played | With the fix |", "| --- | ---: | ---: |",
            f"| Practice weeks | {s_base['n']} | {s_new['n']} |",
            f"| Margin per week | {s_base['margin']:,.0f} | {s_new['margin']:,.0f} |",
            f"| Revenue per week | {s_base['revenue'] / 100:,.0f} | {s_new['revenue'] / 100:,.0f} |" if s_base["revenue"] > 1e6 else f"| Revenue per week | {s_base['revenue']:,.0f} | {s_new['revenue']:,.0f} |",
            f"| Driver fees per week | {s_base['fees'] / 100:,.0f} | {s_new['fees'] / 100:,.0f} |" if s_base["fees"] > 1e6 else f"| Driver fees per week | {s_base['fees']:,.0f} | {s_new['fees']:,.0f} |",
            f"| Late refunds and penalties per week | {s_base['refunds'] / 100:,.0f} | {s_new['refunds'] / 100:,.0f} |" if s_base["revenue"] > 1e6 else f"| Late refunds and penalties per week | {s_base['refunds']:,.0f} | {s_new['refunds']:,.0f} |",
            f"| Cars won per week | {s_base['won']:.0f} | {s_new['won']:.0f} |",
            (f"| Cars that go alone per week | {alone_base:.0f} | {alone_new:.0f} |" if alone_new is not None else
             "| Cars that go alone per week | needs the raw run logs | needs the raw run logs |"),
            f"| On time, average | {s_base['ontime']:.1%} | {s_new['ontime']:.1%} |",
            f"| On time, worst week | {s_base['worst']:.1%} | {s_new['worst']:.1%} |",
            f"| Weeks under 92% on time | {s_base['u92']} | {s_new['u92']} |",
            f"| Weeks under 90% (not ranked) | {s_base['u90']} | {s_new['u90']} |",
            f"| Lowest and highest week | {s_base['low']:,.0f} to {s_base['high']:,.0f} | {s_new['low']:,.0f} to {s_new['high']:,.0f} |",
            f"| Week-to-week spread (sd) | {s_base['sd']:,.0f} | {s_new['sd']:,.0f} |", ""]
    out += ["By set of weeks:", "", "| Weeks | n | Played bot | With the fix | Difference (se) | Weeks better | Worst week on time, played / fix |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    sets = collections.defaultdict(list)
    for s in seeds:
        sets[key(s)[0]].append(s)
    notes = {"t": "t1-t6 (used to tune the played bot)", "v": "v1-v6", "s": "s1-s12", "w": "w1-w12", "r": "r1-r2", "y": "y1-y48 (where the fix was chosen)", "x": "x1-x48 (fresh for the fix)"}
    by_set = {}
    for k in ("t", "v", "s", "w", "r", "y", "x"):
        if k not in sets:
            continue
        ss = sets[k]
        dd, se_k, better_k, _ = paired(new, ss)
        by_set[k] = (dd, se_k, len(ss))
        out.append(f"| {notes[k]} | {len(ss)} | {st.mean(BASE[s]['margin'] for s in ss):,.0f} | {st.mean(new[s]['margin'] for s in ss):,.0f} | {dd:+,.0f} ({se_k:,.0f}) | "
                   f"{better_k} of {len(ss)} | {min(BASE[s]['ontime'] for s in ss):.1%} / {min(new[s]['ontime'] for s in ss):.1%} |")
        print(f"  set {k}: n={len(ss)} diff {dd:+,.0f} (se {se_k:,.0f}) better {better_k}/{len(ss)}")
    fresh = [s for s in seeds if key(s)[0] != "y"]
    dd, se_f, better_f, _ = paired(new, fresh)
    out.append(f"| **All weeks not used to choose the fix** | {len(fresh)} | {st.mean(BASE[s]['margin'] for s in fresh):,.0f} | {st.mean(new[s]['margin'] for s in fresh):,.0f} | "
               f"**{dd:+,.0f} ({se_f:,.0f})** | {better_f} of {len(fresh)} | {min(BASE[s]['ontime'] for s in fresh):.1%} / {min(new[s]['ontime'] for s in fresh):.1%} |")
    out.append(f"| **All weeks** | {len(seeds)} | {s_base['margin']:,.0f} | {s_new['margin']:,.0f} | **{diff:+,.0f} ({se:,.0f})** | {better} of {len(seeds)} | {s_base['worst']:.1%} / {s_new['worst']:.1%} |")
    out.append("")
    print(f"  not used to choose: n={len(fresh)} diff {dd:+,.0f} (se {se_f:,.0f}) better {better_f}/{len(fresh)} | all: n={len(seeds)} diff {diff:+,.0f} (se {se:,.0f})")
    json.dump({"all": [diff, se, len(seeds)], "fresh": [dd, se_f, len(fresh)], "y": list(by_set.get("y", (0, 0, 0)))}, open("logs/backtest_fixes_summary.json", "w"))

    x_diff, x_se, _ = by_set["x"]
    out += ["## Reading", "",
            f"- The fix was picked as the best of five on y1-y48, so its +365 there flatters it. On the 86 weeks that were not used to pick it the difference is {dd:+,.0f} a week (se {se_f:,.0f}): no proven gain.",
            "- The t, v, s and w weeks were used to tune the bot that played, so they lean against any change. The x weeks are fresh for both versions and are the fairest single read: "
            f"{x_diff:+,.0f} a week (se {x_se:,.0f}).",
            f"- All 134 weeks together: {diff:+,.0f} a week (se {se:,.0f}). So the fair statement is a gain somewhere between nothing and about 150 a week, with 23 fewer cars a week going alone, the same cars won and the same share on time on average, and three more weeks between 90% and 92% on time.",
            f"- Drivers do take three-car gigs at once (0.76 x the typical fees, within 2 minutes, 1% of their cars late). Driver fees fall by {s_base['fees'] - s_new['fees']:,.0f} a week; "
            f"{s_new['refunds'] - s_base['refunds']:,.0f} of that goes back in late refunds and {s_base['revenue'] - s_new['revenue']:,.0f} in lower revenue (one car fewer won a week).", ""]

    final_actual, r06, r03 = 17130, 76921, 76349
    final_table = [22931, 21745, 21112, 19975, 19965, 19919, 19863, 19574, 19366, 19084, 19028, 18578, 18548, 18532, 18458, 18423, 18284, 18094, 18021, 17742, 17606, 17463, 17222, 17209, 17088, 16955]
    t06 = [98179, 87241, 86394, 85568, 83705, 82771, 81773, 79842, 79578, 77833, 77653, 77249, 76815, 76780, 76676, 76562, 76175]
    t03 = [88416, 85283, 83524, 83342, 79317, 79277, 78843, 78161, 77656, 77119, 76884, 76873, 75970, 75630, 74878]

    def rank(score, others):
        n = 1 + sum(1 for o in others if o > score)
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

    out += ["## What our stats would have been", "",
            "The secret weeks of the final and of the ranking rounds cannot be played again, so this adds the backtest's difference to our real scores and reads the place off the real tables. "
            f"Three readings of the difference: {dd:+,.0f} a week (the 86 weeks not used to pick the fix), {x_diff:+,.0f} (the fresh x weeks), {diff:+,.0f} (all 134 weeks). Cars won and the share on time do not change in the backtest.", "",
            "| | What we got | With the fix: margin | With the fix: place | Tenth place |", "| --- | ---: | ---: | ---: | ---: |"]
    gains = sorted([dd, x_diff, diff])
    lo, hi = gains[0], gains[-1]
    out.append(f"| The final (one week) | 17,130, 463 cars, 94.4% on time, 25th of 58 | {final_actual + lo:,.0f} to {final_actual + hi:,.0f} | {rank(final_actual + hi, final_table)} to {rank(final_actual + lo, final_table)} | 19,084 |")
    out.append(f"| Ranking round Sunday 06:00 (five weeks) | 76,921 (15,384 a week), 97.0% on time, 13th of 51 | {r06 + 5 * lo:,.0f} to {r06 + 5 * hi:,.0f} | {rank(r06 + 5 * hi, t06)} to {rank(r06 + 5 * lo, t06)} | 77,833 |")
    out.append(f"| Ranking round Sunday 03:00 (five weeks) | 76,349 (15,270 a week), 95.9% on time, 13th of 48 | {r03 + 5 * lo:,.0f} to {r03 + 5 * hi:,.0f} | {rank(r03 + 5 * hi, t03)} to {rank(r03 + 5 * lo, t03)} | 77,119 |")
    out += ["", "The Sunday 00:00 round (80,264, or 16,053 a week, 17th of 58) is left out: only part of its table was saved.", "",
            f"So the best of the fixes would have left us about where we were: {rank(final_actual + hi, final_table)} to {rank(final_actual + lo, final_table)} in the final and just outside the top ten in the ranking rounds. "
            "The top ten of the final needed 1,954 more in that one week; the top ten of the ranking rounds needed 154 to 182 more a week.", ""]
    print("would-be:", "final", final_actual + lo, final_actual + hi, rank(final_actual + hi, final_table), rank(final_actual + lo, final_table),
          "| 06:00", r06 + 5 * lo, r06 + 5 * hi, rank(r06 + 5 * hi, t06), rank(r06 + 5 * lo, t06), "| 03:00", r03 + 5 * lo, r03 + 5 * hi, rank(r03 + 5 * hi, t03), rank(r03 + 5 * lo, t03))

    out += ["## Week by week (three cars, round trips too)", "",
            "| Week | Played bot | With the fix | Difference | On time, played | On time, fix | Cars won, played / fix |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in seeds:
        b, n_ = BASE[s], new[s]
        out.append(f"| {s} | {b['margin']:,.0f} | {n_['margin']:,.0f} | {n_['margin'] - b['margin']:+,.0f} | {b['ontime']:.1%} | {n_['ontime']:.1%} | {b['won']} / {n_['won']} |")
    out.append("")
    open("BACKTEST_FIXES.md.new", "w", encoding="utf-8").write("\n".join(out))


if __name__ == "__main__":
    main()
