# Deduplication

Deduplication decides which records from different sources describe the same
entity, for example "BP" in one dataset and "British Petroleum" in another, so
that an application can show them together.

muckrake uses the [`nomenklatura`](https://github.com/opensanctions/nomenklatura)
resolver. `uv run muckrake xref` generates suggestions for pairs of records that
may be the same entity and stores them in the `resolver` table in the working
database. `uv run muckrake dedupe` opens nomenklatura's terminal UI for reviewing
them (match, no match, unsure or skip). `xref`, the `dedupe` TUI and
`dedupe-edges` build a LevelDB store first, so they need `plyvel` (see the main
README's installation notes). Set `MUCKRAKE_PROFILE_URL` to show a link to each
entity in the TUI.

## Web review backend

[`review.py`](./review.py) provides the functions behind a web review UI with the
same decisions as the TUI. Several reviewers can work at once: each candidate is
locked to one reviewer for 30 minutes (the `resolver_lock` table). muckrake
provides the functions (`get_next_dedupe_candidate`, `record_dedupe_judgement`
and their cluster equivalents); the consuming application provides the web UI
and user accounts, and can pass `user_prefix=` to namespace its reviewers' IDs in
the resolver's `user` column.

## Cluster review

Pairwise review is slow for groups of records: if the resolver suggests A-B and
B-C but not A-C, a reviewer has to judge both pairs to put all three in one
cluster. [`cluster.py`](./cluster.py) lets a reviewer judge a group of records at
once. `get_next_dedupe_cluster` does not run a full clustering algorithm. It:

1. takes the next unresolved resolver pair
2. looks at the current unresolved suggestions returned by `resolver.get_candidates(...)`
3. builds a small connected group around that seed pair
4. limits the group to `max_members` records (default 8)
5. locks every unresolved pair whose endpoints are both in the group

The application then calls one of:

- `record_dedupe_cluster_judgement(..., judgement_value, ...)` with `positive`,
  `negative` or `unsure`. The judgement is recorded only on locked pairs whose
  endpoints are both among the selected records; unselected records stay
  unresolved.
- `skip_dedupe_cluster(...)`, which hides the cluster from that reviewer for two
  hours (`SKIP_TTL`). Skips are per reviewer, not global.

## Alternatives considered

[Dedupe](https://docs.dedupe.io/en/latest/index.html) is a Python deduplication
library that also generates pairwise suggestions. Its former web review UI let
users review clusters and check which records belong together
([recording](https://youtu.be/9wEA90Fz-lU?si=y4UHS4Ky7yVygJWg&t=689)).
[According to its docs](https://docs.dedupe.io/en/latest/how-it-works/Grouping-duplicates.html),
hierarchical clustering with centroid linkage gave the best results
([code](https://github.com/dedupeio/dedupe/blob/main/dedupe/clustering.py)).

Possible improvements to cluster construction: score thresholds before
expanding a group, schema-aware grouping, grouping around a canonical seed
instead of plain graph expansion, and limiting low-confidence bridge edges.
