import logging
import sys
from pathlib import Path

import click
from nomenklatura.matching import DefaultAlgorithm
from muckrake.logging import configure_logging
from muckrake.dataset import find_datasets, load_config, clear_dataset, list_datasets
from muckrake.crawl import run_crawl
from muckrake.dedupe import (
    run_xref,
    run_dedupe,
    run_dedupe_explode,
    run_merge,
    run_prune,
    run_dedupe_edges,
)
from muckrake.extract.ner import run_ner_extract, run_ner_review
from muckrake.extract.ner.engines import list_extractors
from muckrake.release import list_releases, run_release_build, run_release_publish

log = logging.getLogger("muckrake")


class MuckrakeGroup(click.Group):
    COMMAND_GROUPS = [
        ("List all available datasets", ["list"]),
        ("Crawl and extract", ["crawl"]),
        ("Named-entity recognition", ["ner-extract", "ner-review"]),
        (
            "Deduplicate",
            [
                "xref",
                "xref-prune",
                "dedupe",
                "dedupe-manual",
                "dedupe-explode",
                "dedupe-edges",
            ],
        ),
        ("Build releases", ["release-build", "release-list", "release-publish"]),
        ("Export", ["export"]),
        ("Start server", ["server"]),
    ]

    def list_commands(self, ctx):
        ordered = []
        seen = set()
        for _, commands in self.COMMAND_GROUPS:
            for command in commands:
                if command in self.commands and command not in seen:
                    ordered.append(command)
                    seen.add(command)

        for command in sorted(self.commands):
            if command not in seen:
                ordered.append(command)

        return ordered

    def format_commands(self, ctx, formatter):
        seen = set()
        for heading, commands in self.COMMAND_GROUPS:
            rows = []
            for command in commands:
                cmd = self.get_command(ctx, command)
                if cmd is None or cmd.hidden:
                    continue
                rows.append((command, cmd.get_short_help_str(formatter.width)))
                seen.add(command)

            if rows:
                with formatter.section(heading):
                    formatter.write_dl(rows)

        other_rows = []
        for command in sorted(self.commands):
            if command in seen:
                continue
            cmd = self.get_command(ctx, command)
            if cmd is None or cmd.hidden:
                continue
            other_rows.append((command, cmd.get_short_help_str(formatter.width)))

        if other_rows:
            with formatter.section("Other commands"):
                formatter.write_dl(other_rows)


@click.group(cls=MuckrakeGroup)
def cli():
    """Muckrake: A minimal FtM data processing framework."""
    configure_logging()


@cli.command()
@click.argument("dataset_name", required=False)
@click.option("--output", "-o", type=click.Path(), help="Override output path")
@click.option(
    "--clear",
    "-c",
    is_flag=True,
    default=False,
    help="Clear dataset data before crawling",
)
def crawl(dataset_name, output, clear):
    """Crawl one or all datasets.

    DATASET_NAME should be the dataset name from config.yml (e.g., gb_political_finance).
    If not provided, crawls all datasets.
    """
    configs = find_datasets(dataset_name)

    if dataset_name and not configs:
        click.echo(f"Error: Dataset '{dataset_name}' not found", err=True)
        click.echo("\nAvailable datasets:", err=True)
        for ds in list_datasets():
            click.echo(f"  - {ds.name}", err=True)
        sys.exit(1)

    for config in configs:
        ds = load_config(config)
        if clear:
            clear_dataset(ds.name)
        run_crawl(config, output)


@cli.command("list")
def list_cmd():
    """List all available datasets."""
    datasets = list_datasets()
    if not datasets:
        click.echo("No datasets found")
        return

    click.echo("Available datasets:")
    for ds in datasets:
        title = ds.to_dict().get("title", "")
        click.echo(f"  {ds.name:<30} {title}")


@cli.command()
@click.option(
    "--output", "-o", type=click.Path(), required=True, help="Output file path"
)
@click.option("--dataset", "-d", help="Filter by dataset")
def export(output, dataset):
    """Export entities to FtM JSON."""
    try:
        from muckrake.export import run_export_ftm

        run_export_ftm(Path(output), dataset)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command()
@click.option("--limit", "-l", type=int, default=50000, help="Candidate limit")
@click.option("--threshold", "-t", type=float, help="Auto-merge threshold")
@click.option("--algorithm", "-a", default=DefaultAlgorithm.NAME, help="Algorithm")
@click.option("--schema", "-s", help="Filter by schema")
@click.option("--focus-dataset", "-f", "focus_dataset", help="Focus on a dataset")
def xref(limit, threshold, algorithm, schema, focus_dataset):
    """Generate deduplication candidates."""
    try:
        run_xref(
            limit=limit,
            threshold=threshold,
            algorithm=algorithm,
            schema=schema,
            focus_dataset=focus_dataset,
        )
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command()
def dedupe():
    """Interactively judge candidates."""
    try:
        run_dedupe()
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("dedupe-manual")
@click.argument("entity_ids", nargs=-1, required=True)
@click.option("--force", "-f", is_flag=True, default=False, help="Force merge")
def dedupe_manual(entity_ids, force):
    """Manually merge entities as duplicates."""
    try:
        run_merge(entity_ids, force=force)
    except ValueError as ve:
        click.echo(f"Error: {ve}", err=True)
        sys.exit(1)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("dedupe-explode")
@click.argument("entity_id", required=True)
def dedupe_explode(entity_id):
    """Undo deduplication by exploding a merged cluster."""
    try:
        run_dedupe_explode(entity_id)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("xref-prune")
def xref_prune():
    """Remove dedupe candidates from the resolver."""
    try:
        run_prune()
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("dedupe-edges")
@click.argument("dataset_name", required=False)
@click.option(
    "--max-gap-days",
    type=int,
    default=1,
    show_default=True,
    help="Maximum allowed gap days between adjacent edges",
)
@click.option("--dry-run", is_flag=True, default=False, help="Show changes only")
def dedupe_edges(dataset_name, max_gap_days, dry_run):
    """Deduplicate Representation edges across datasets in resolver."""
    try:
        run_dedupe_edges(
            dataset_name=dataset_name,
            max_gap_days=max_gap_days,
            dry_run=dry_run,
        )
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("ner-extract")
@click.argument("dataset_name", required=False)
@click.option("--limit", "limit", type=int, default=None, help="Max candidate rows")
@click.option("--entity-id", "entity_id", help="Extract only for one entity ID")
@click.option(
    "--extractor",
    "extractor_name",
    type=click.Choice(list_extractors()),
    default="llm",
    show_default=True,
    help="Extraction strategy",
)
def ner_extract(dataset_name, limit, entity_id, extractor_name):
    """Extract named entities from statement text fields."""
    try:
        run_ner_extract(
            dataset_name=dataset_name,
            limit=limit,
            entity_id=entity_id,
            extractor_name=extractor_name,
        )
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("ner-review")
@click.argument("dataset_name", required=False)
@click.option("--limit", "limit", type=int, default=None, help="Max pending candidates")
def ner_review(dataset_name, limit):
    """Review pending NER extraction candidates."""
    try:
        run_ner_review(dataset_name=dataset_name, limit=limit)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command()
@click.option("--port", "-p", type=int, default=8000, help="Port")
@click.option("--host", "-h", default="127.0.0.1", help="Host")
@click.option("--reload", "-r", is_flag=True, default=False, help="Reload")
def server(port, host, reload):
    """Start the API server."""
    import uvicorn

    uvicorn.run("muckrake.api.server:app", host=host, port=port, reload=reload)


@cli.command("release-build")
@click.argument("dataset_name", nargs=-1, required=False)
@click.option("--notes", help="Optional release notes")
def release_build(dataset_name, notes):
    """Build an immutable release artifact from dataset runs."""
    try:
        release_id = run_release_build(dataset_name or None, notes=notes)
        click.echo(f"Built release {release_id}")
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("release-publish")
@click.argument("release_id", type=int)
def release_publish(release_id):
    """Publish a built release into the read-only serving database."""
    try:
        run_release_publish(release_id)
    except Exception as e:
        log.exception(e)
        sys.exit(1)


@cli.command("release-list")
@click.option("--limit", type=int, default=20, show_default=True, help="Max releases")
def release_list(limit):
    """List recent releases and their statuses."""
    try:
        releases = list_releases(limit=limit)
        if not releases:
            click.echo("No releases found")
            return
        for release in releases:
            click.echo(
                f"{release.id}\t{release.status}\tcreated={release.created_at}\tpublished={release.published_at or '-'}"
            )
    except Exception as e:
        log.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    cli()
