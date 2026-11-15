# The other build (v1 to v4)

This is the first of the two desks built for Spread, made in parallel with the ABQuant desk at the repository root. The
ABQuant desk started from a copy of v4 and went further, and it played the final. v4 was kept as the fallback for the
final and was never needed.

## How it prices

It uses the same rule as the ABQuant desk: quote the price that maximises P(win) times the margin after expected
driver cost, late risk and the price of scarce drivers. What differs is how the parts are estimated and how drivers
are bought:

- **Late risk:** a logistic model of the chance a car arrives late. An indicator for the early probe weeks fixed its
  calibration. Refitting it on our own won orders made it worse (selection bias), so v3/v4 keep the earlier model.
- **Booking time:** a time-to-event (hazard) model of how fast a gig books at each fee, with censoring.
- **Fees:** a stepped fee schedule. It opens at 0.9 times the typical fee, raises in steps as the deadline nears, and
  ends with a cheaper rescue. A fee schedule solved by backward induction lost money, because drivers learn to wait
  for raises.
- **Competitor level:** Bayesian online updates with shrinkage by lane, dealer, day and pickup area.
- **Limits:** a hard cap on open cars by driver supply, an on-time gate that tightens when late risk rises, an outage
  detector, and a reader for dealers' notes about later-ready cars.

Every car goes out alone. The ABQuant desk's biggest gains over v4 were sending two cars in one gig and counting
drivers who live beyond 30 km.

## Results

- Practice: about EUR 11,500 a week on the tuning weeks and EUR 10,500 on the held-out weeks, with every week at
  94% on time or better.
- 21:00 ranking round (Saturday): EUR 11,675 a week, 95.6% on time, all five weeks ranked.
- Paired against the ABQuant desk on the same weeks, v4 was EUR 1,900 to 3,100 a week behind. That is why the ABQuant desk played
  the later rounds and the final.

## Layout

- `bot/`: the desk (`desk.py`), runner (`run.py`), models (`fit.py`), map (`geo.py`), note reader (`notes.py`), and
  tools for paired comparison and replay.
- `run_final.sh`: played a frozen release (`releases/v4`, not copied here: each release folder held a `.env`). The code in `bot/` is the latest version.
- `data/`: the fitted late and hazard models and the map.

Running it needs the organisers' `spread` kit (served at `/kit/`, not copied here) and a `.env` file with
`SPREAD_KEY=<team key>`.
