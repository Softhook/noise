# Progress

Where the survey's tools stand, what's waiting on a decision, and what's next. Read this first when picking the work up again. The design is in [tools/survey/ARCHITECTURE.md](tools/survey/ARCHITECTURE.md), and how to use everything is in [README.md](README.md).

*Last updated: 7 November 2026.*

## Waiting on a decision

- **Merge the restructure.** The branch `restructure-data-and-project` has three commits on top of `main`, and isn't merged or pushed. Each commit passes its tests, and the last passes all 343 (`make test`). Rebuilding both deployments gives the same results as before. Merge it into `main`, or push it and open a PR.

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

1. **`match`:** noise events to passes, for the garden and NMT6, and the match check page.
2. **`checks`:** clock offsets, coverage, heights, identity conflicts, unmatched flights and events.
3. **The rest of `resolve`:** per-pass manual overrides, airport records, and lookups within a budget.
4. **The garden's real data:** the Pi's logs once it's at the garden (`make pi-collect`). Until then, OpenSky stands in for it.
5. **The Fusion adapter**, once its export format is decoded ([notes](Documents/Fusion_Data_Format_Reverse_Engineering.md)).
