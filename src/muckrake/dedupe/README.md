One of the most important features of muckrake is the ability to deduplicate unique legal entities. For example, if we have a record for "BP" from one source and "British Petroleum" from another source, we want to display information about both records on the same page.

Muckrake largely relies on the [`nomenklatura`](https://github.com/opensanctions/nomenklatura) library to generate resolver suggestions for pairs of records that may represent the same entity. We run `uv run muckrake xref` to generate these suggestions, which are stored in the `resolver` table in the database. By default, `nomenklatura` comes with a TUI for reviewing these suggestions, with options to approve, reject, or skip each suggestion.

We have additionally [implemented](./review.py) a web-based review interface replicating the functionality of the TUI, allowing for this to be done outside of the terminal. One major benefit to this is the deduplication is now available to multiple users at the same time.

## Clusters

One of the major limitations of the default `nomenklatura` review model is that it is pairwise. This means that if we have three records A, B, and C, and the resolver generates suggestions for A-B and B-C, but not A-C, we would have to approve both A-B and B-C to get all three records into the same cluster. This can be tedious for large clusters.

We have [implemented](./cluster.py) a basic cluster review system that allows reviewers to review whole clusters of records at once. Ultimately, we want to replace the pairwise review system.

The current MVP does not implement a full clustering algorithm. Instead, it:

1. takes the next unresolved resolver pair
2. looks at the current unresolved suggestion rows returned by `resolver.get_candidates(...)`
3. builds a small local connected group around that seed pair
4. limits the number of members in the displayed batch
5. locks all unresolved pairs inside that displayed batch

When the user submits the form:

- checked records are merged by repeatedly calling `resolver.decide(..., Judgement.POSITIVE, ...)`
- unchecked records are ignored
- if fewer than two records are selected, no merge happens

Unlike the pairwise review, only positive merge decisions are made.

Users can also skip clusters. There is a small locking mechanism that hides skipped clusters for a TTL period, but there is no way to explicitly reject a cluster for now. The skip list is per-user, not global. `resolver_lock` is still used for concurrency control.

### Dedupe-style review

Beyond the current implementation, there are a few other approaches that could work.

[Dedupe](https://docs.dedupe.io/en/latest/index.html) is a popular Python library for deduplication, I've used it for a few projects in the past. It also generates pairwise suggestions. They used to have a web review UI that is no longer available, but [recordings of it still exist](https://youtu.be/9wEA90Fz-lU?si=y4UHS4Ky7yVygJWg&t=689). In these recordings, users are able to review clusters and check which records belong together. [According to their docs](https://docs.dedupe.io/en/latest/how-it-works/Grouping-duplicates.html), they found that **hierarchical clustering with centroid linkage** gave the best results. [The relevant code is here](https://github.com/dedupeio/dedupe/blob/main/dedupe/clustering.py).

We should explore this approach in the future.

### Next steps

The next improvement I would make is better cluster construction before adding more actions.

Good next options:

- score thresholding before expansion
- schema-aware grouping
- canonical-seed grouping instead of plain graph expansion
- limiting low-confidence bridge edges

We also want to add explicit pair rejection inside clustered review. We need to think of a good way to do this, for example, we could have all unchecked records be automatically rejected against the cluster.