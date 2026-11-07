# Progress

Where the survey's tools stand, what's waiting on a decision, and what's next. Read this first when picking the work up again. The design is in [tools/survey/ARCHITECTURE.md](tools/survey/ARCHITECTURE.md), and how to use everything is in [README.md](README.md).

*Last updated: 7 November 2026, after `match`.*

## Waiting on a decision

- **Push `main`.** The restructure was merged into the local `main` (a fast-forward) on 7 November 2026, and `match` is on the branch `survey-match`. Neither is pushed. Merge `survey-match` too, then push, or open PRs.

## Done: match (7 November 2026)

- `survey/match.py` matches each noise event at a receptor to the pass that made it. The predicted sound arrival comes from each pass's 3-D closest point, using its highest-ranked track not at an edge of its data.
- It first finds each day's clock offset from where LAmax-minus-arrival pairs pile up, and centres the window on it.
- An event goes to the loudest predicted pass within 3 km and ±20 s, and each pass gets at most one event. Other passes within 10 dB are named.
- The rules are in [ARCHITECTURE.md](tools/survey/ARCHITECTURE.md#match-noise-events-to-passes).
- The results go in two new tables, `event_matches` and `event_candidates`. `build.json`'s `matches` gives the counts, each day's clock offset, and the median offset over clean arrivals and clean departures, kept apart.
- The app's passes table, detail and timeline use the build's matches instead of the page's own guess.
- On 5 November 2026, each of the 22 NMT6 events WebTrak classed as aircraft went to the only pass within 1 km that fitted in time. All 22 were departures. The clock offset was 0.4 s, and the median offset over the departures 0.3 s.
- A Global Express at −7.8 s is unexplained: it isn't the departure effect, since every pass that day was a departure.
- A critical review the same day led to the 3 km limit, the clock offset, the separate medians and the candidates table. Not done: comparing the predicted level with the measured one, to catch an event that isn't the pass's even within 3 km. That needs the Fusion's levels.

## Done: the restructure (7 November 2026)

What was done, in three commits on `restructure-data-and-project`:

1. **`51651a1` Data: one folder outside the tools, raw apart from derived.**
   - Every tool writes into `data/` at the top of the repository, or wherever `NOISE_DATA` says.
   - `raw/` holds what's collected or downloaded. `derived/` holds what's worked out from it, which can be deleted and rebuilt.
   - WebTrak takes separate `--raw` and `--out` folders.
2. **`de2f4c5` Survey: one build from raw data, analysing only what changed.**
   - `noise build` runs `adsb analyse` itself, on each deployment's window, only when what it reads has changed by content.
   - Manifests moved to `tools/survey/deployments/`, and name raw files relative to `data/`.
   - The app's Rebuild runs in the background, and the page shows its progress.
3. **`13af46e` One project: pyproject, a Makefile and the noise command, on Python 3.12.**
   - There's one `.venv`, pinned by `requirements.lock`, one root `Makefile` and one `noise` command.
   - Fusion became a package.
   - `make opensky` won't overwrite raw data without `REPLACE=1`.

Why each choice was made: the critical review that led to it is summarised in the commit messages and the survey README's [Where the data lives](tools/survey/README.md#where-the-data-lives).

## Deferred, on purpose

- **Common tables to Parquet and DuckDB**, instead of CSV. Do it **before the 37-day survey**: tens of millions of 1 s rows will make CSV slow. At today's size CSV is fine.
- **Folding the WebTrak app and the offline `viewer.html` pages into the survey app.** Only when needed. Keep a way to export a day or a match as one page that opens offline.
- **Backups of `data/raw/`:** decided against, on 7 November 2026.

## Known caveats

- `make dev-log` writes to `data/derived/adsb/dev-logs` even when `NOISE_DATA` is set: the logger takes its folder only from `tools/adsb/site.dev.json`.
- The tools only work from the editable install (`make setup`), and `noise` refuses to run otherwise.
- The data-folder rule is written out in each tool, to keep them independent. `tools/noise/tests` checks that they agree.
- The WebTrak tests print a `ResourceWarning` about an unclosed lock file. It predates the restructure; the tests pass.
- Python 3.12 was installed with Homebrew for the environment. The Pi needs only Python 3.9 or later.
- The approach noise model page at the top of the repository (`index.html`, `js/`) is separate from the tools. It may belong in its own repository.

## Next: the survey itself (Phase 0)

The survey README's [Status](tools/survey/README.md#status) says what's built. Still to do, from the architecture:

1. **`checks`:** clock offsets (`match` already finds each day's; `checks` reports them per day and source pair, and the jumps), coverage, heights, identity conflicts, unmatched flights and events.
2. **The rest of `resolve`:** per-pass manual overrides, airport records, and lookups within a budget.
3. **The garden's real data:** the Pi's logs once it's at the garden (`make pi-collect`). Until then, OpenSky stands in for it.
4. **The Fusion adapter**, once its export format is decoded ([notes](Documents/Fusion_Data_Format_Reverse_Engineering.md)).
5. **The match check page** (Phase 1, with the Fusion): a page per matched event, for checking matches by eye.
