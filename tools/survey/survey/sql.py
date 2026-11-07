"""noise sql DEPLOYMENT [QUERY]: a built deployment's tables, in DuckDB, to query with SQL.

    noise sql 2026-11-05                       a prompt: each statement ends with ;
    noise sql 2026-11-05 "SELECT type, count(*) FROM identity GROUP BY type ORDER BY 2 DESC"
    noise sql 2026-11-05 --csv "SELECT * FROM event_matches" > matches.csv

Every common table is a view over the build's Parquet files (schema.connect), in a database held in
memory: a table made here goes when it ends, and the build's files are only read, unless a
statement writes files itself (COPY ... TO). Times are UTC. At the prompt, .tables lists the tables
and their columns, and .quit (or Ctrl-D) leaves.
"""

from __future__ import annotations

import contextlib
import csv
import sys

import duckdb

from . import manifest, schema

MAX_ROWS = 40  # Rows shown at the prompt; --csv gives them all


def add_arguments(parser):
    parser.add_argument("deployment", metavar="DEPLOYMENT", help="a deployment's name or a manifest's path")
    parser.add_argument("query", nargs="?", help="a SQL statement; without one, a prompt")
    parser.add_argument("--csv", action="store_true", help="print the query's whole result as CSV")


def describe():
    """The tables and their columns, with their types, as .tables shows them."""
    return "\n".join(f"{name}{' (by day)' if name in schema.PARTITIONED else ''}: "
                     + ", ".join(f"{col} {schema.SQL_TYPES[kind].lower()}" for col, kind in columns.items())
                     for name, columns in schema.TABLES.items())


def show(db, statement, as_csv=False, out=None):
    """Run one statement, and print its result: a table, or with as_csv every row as CSV."""
    out = out or sys.stdout
    cursor = db.execute(statement)  # Run once; the rows are then fetched from it
    columns = [d[0] for d in cursor.description]
    if columns == ["Success"]:  # DuckDB's answer to a statement that returns nothing, such as SET
        return
    if as_csv:
        w = csv.writer(out)
        w.writerow(columns)
        while batch := cursor.fetchmany(10_000):
            w.writerows(batch)
        return
    rows = cursor.fetchmany(MAX_ROWS + 1)
    print(table(columns, rows[:MAX_ROWS]), file=out)
    if len(rows) > MAX_ROWS:
        print(f"(more than {MAX_ROWS} rows; the first {MAX_ROWS} shown, --csv for all)", file=out)
    else:
        print(f"({len(rows)} row{'' if len(rows) == 1 else 's'})", file=out)


def table(columns, rows):
    """Rows as an aligned text table: numbers to the right, NULL as empty."""
    cells = [["" if v is None else str(v) for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    right = [bool(rows) and all(isinstance(r[i], (int, float)) and not isinstance(r[i], bool)
                                for r in rows if r[i] is not None) for i in range(len(columns))]

    def line(values):
        return "  ".join(v.rjust(w) if r else v.ljust(w) for v, w, r in zip(values, widths, right)).rstrip()

    return "\n".join([line(columns), line(["-" * w for w in widths])] + [line(r) for r in cells])


def prompt(db, name):
    try:
        import readline  # noqa: F401  (line editing and history at the prompt, where there is one)
    except ImportError:
        pass
    print(f"{name}: the common tables, in DuckDB. End each statement with ;. .tables lists them, .quit leaves.")
    pending = ""
    while True:
        try:
            line = input("... " if pending else "sql> ")
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            pending = ""
            continue
        text = line.strip()
        if not pending and text in (".quit", ".exit", "quit", "exit"):
            return
        if not pending and text == ".tables":
            print(describe())
            continue
        pending = f"{pending}\n{line}" if pending else line
        if not text.endswith(";"):  # A statement ends with ;, as in any SQL shell
            if not pending.strip():
                pending = ""
            continue
        statement, pending = pending, ""
        try:
            show(db, statement)
        except duckdb.Error as error:
            print(error)


def main(args):
    m = manifest.load(manifest.find(args.deployment))
    try:
        folder = schema.built_tables(m)
    except schema.NotBuilt as error:
        print(f"noise sql: {error}", file=sys.stderr)
        return 2
    with contextlib.closing(schema.connect(folder)) as db:
        if args.query:
            try:
                show(db, args.query, args.csv)
            except duckdb.Error as error:
                print(f"noise sql: {error}", file=sys.stderr)
                return 1
            return 0
        prompt(db, m["deployment"])
    return 0
