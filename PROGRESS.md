# Progress

Where the survey's tools stand, what's waiting on a decision, and what's next. Read this first when picking the work up again. The design is in [tools/survey/ARCHITECTURE.md](tools/survey/ARCHITECTURE.md), and how to use everything is in [README.md](README.md).

*Last updated: 7 November 2026, after moving the common tables to Parquet and DuckDB.*

## Waiting on a decision

Nothing. The restructure, `match`, the core refactor and the move to Parquet and DuckDB were merged into `main` and pushed on 7 November 2026.

## Done: the common tables in Parquet and DuckDB (7 November 2026)

- Each common table is a Parquet file, and `positions` and `levels` a file per day (`positions/2026-11-05.parquet`). Each column has a type in `schema.TABLES`: text, a number, a flag, or a UTC timestamp to the millisecond. A missing value is NULL. Every read goes through DuckDB (`schema.connect`, a view per table).
- `noise sql <deployment> [query]` queries a build: one query, `--csv` for all its rows, or a prompt. The views are held in memory, so nothing done there changes the build.
- `schema.FORMAT` is 2, so a CSV build is shown as needing a rebuild.
- The core holds rows as before, with flags as bools instead of `"1"` or `""`. `schema.read_rows` gives back what was written.
- Checked: both deployments rebuilt, and everything the app serves, and every table, compared with the CSV build. The only difference was the build time, once a number in a string counts as equal to the same number.
- On 37 made-up days, 160k positions and 172,800 1 s levels a day:
  - a day is 2.4 MB, against 16.9 MB as CSV;
  - the app reads a day about twice as fast;
  - a query over all 6.4 million levels takes 0.05 s.
- Why files and not a DuckDB database file: a build replaces the tables folder while the app may be reading it, and files need no lock between the two.
- A critical review the same day found that a read broken off by a build's swap failed instead of being tried again. That race predated the change, and it's fixed.
- New dependencies: `duckdb` and `pyarrow`. The Pi's logger still needs only the standard library.
- Still CSV, on purpose: `registry/fleet.csv`, which is kept in git and edited by hand, and `adsb analyse`'s output, which the Pi's standard-library code writes.

## Done: the core refactor (7 November 2026)

The same results, with simpler code: a rebuild of both deployments gave byte-identical tables, and `build.json` differs only in its time and its new `format`.

- `survey/paths.py` is the one place that says where things are. The WebTrak adapter's `tool` option and `sys.path` hack, and the ADS-B adapter's `PYTHONPATH`, are gone: the editable install finds both packages.
- The order of sources moved from `link.py` to `common.py`, since `match`, `resolve`, the app and the page all use it.
- `link.members()` groups each pass's flights once, and `explain`, `resolve` and `match` take that, instead of each regrouping the passes rows.
- Each step summarises its own table (`explain.summary`, `resolve.summary`, `match.summary`, `match.clock_warnings`), and `build.summarise` only assembles them.
- The manifest works out each receptor's `mic_amsl_m` once. Before, the approaches gave no slant without a ground elevation, while `match` silently took the ground as sea level. Now both take it as sea level, and the build warns. Both real receptors have an elevation, so nothing changed for them.
- `match._match_group` is split into its steps: `_sounds`, `_near`, `_clocks`, `_assign`.
- `build.json` records `schema.FORMAT`. The app treats a build of another format as needing a rebuild, so the shims for older builds came out of the app and the page. That includes the page's copy of `resolve`'s type rule.
- The app keeps one `Deployment` per name, which re-reads its own manifest when the file changes, instead of a cache keyed on the file's time and a separate table of locks.
- A critical review the same day found three problems, all fixed:
  - A build test's fleet table was kept off `registry/fleet.csv` only by a patch, so it now names its own path again.
  - Nothing made anyone raise `FORMAT` when a table changed. A test now pins it to a digest of the tables' columns.
  - A non-numeric ground elevation or mic height crashed the build, rather than being refused as a bad manifest.
- Still open, and older than the refactor: `event_matches` joins `noise_events` on source, receptor and LAmax time. That's unique in today's data, but nothing guarantees it. Give events an id of their own when the Fusion adapter is written.

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

- **The build's memory.** The build holds every position and level in Python while it runs: about 220 MB per million positions. 37 days of the garden's logger and adsb.lol, about 12 million positions, plus 6.4 million levels, would need about 2–4 GB. A laptop can do that. If it's too much, build a day at a time, or work out the closest approaches in DuckDB.
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
