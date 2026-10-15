muckrake is a reusable pipeline framework that turns source data into FollowTheMoney entities. It ships no crawlers of its own (apart from the example in `examples/hello_dataset/`); crawlers live in consuming repositories. The source data is often semi-structured government publications with inconsistencies and data-entry errors, so crawlers interpret it strictly.

### Repo layout

* `src/muckrake` contains an ETL framework for crawlers.
    * Documentation for the entity structure (available schemata and properties in `followthemoney`) is available here: https://followthemoney.tech/explorer/schemata/ (sub paths eg. https://followthemoney.tech/explorer/schemata/Person/). Property types are documented here: https://followthemoney.tech/explorer/types/ (and eg. https://followthemoney.tech/explorer/types/name/).
    * Data cleaning functions from `rigour` are documented at: https://rigour.followthemoney.tech/
* Application-owned crawler repositories such as `../openlobbying` contain `datasets/` trees. Each crawler is defined using a `config.yml` file, and a `crawler.py` code file.
    * To run a crawler, work from the consuming app repo or set `MUCKRAKE_DATASET_PATHS` so `muckrake` can discover external datasets.
    * When a crawler encounters uncertainty in any of the data it is parsing, it should crash or produce an error instead of emitting ambiguous data.
    * After running a crawler, output data is written to `data/datasets/<dataset_name>/`.

## Coding hints

* All new crawlers should be written using typed Python. Suggest adding types to existing ones.
* Always use `uv` to run `muckrake` commands, eg. `uv run muckrake crawl <dataset_name>`.
* Be conservative in bringing in new dependencies. Libraries are listed in `pyproject.toml`.
