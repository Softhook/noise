"""Aircraft near NMT6 from the OpenSky Network's research database (Trino).

Modules:
- common:   NMT6, paths, times and numbers
- geometry: distances from NMT6, closest approach, the query box
- trino:    the state vector query, kept within OpenSky's guidelines
- passes:   state vectors into one closest approach per aircraft pass
- webtrak:  WebTrak's saved radar tracks and NMT6 events, to compare against
- compare:  the `compare` command: OpenSky against WebTrak, and the CSV

Only trino.py needs pyopensky, and it imports it only when a query is made, so everything else
(and the tests) runs on the standard library.
"""
