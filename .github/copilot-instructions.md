This project contains crawlers that import source data, such as lobbyists lists and data about politicans, into the FollowTheMoney entities. It puts an emphasis on data cleaning. Much of the input data is semi-structured information published by government bodies - often rife with inconsistencies, manual data entry errors, etc. Our goal is to bring strict interpretation to these source datasets.

### Repo layout

* `src/muckrake` contains an ETL framework for crawlers.
    * Documentation for the entity structure (available schemata and properties in `followthemoney`) is available here: https://followthemoney.tech/explorer/schemata/ (sub paths eg. https://followthemoney.tech/explorer/schemata/Person/). Property types are documented here: https://followthemoney.tech/explorer/types/ (and eg. https://followthemoney.tech/explorer/types/name/).
    * Data cleaning functions from `rigour` are documented at: https://rigour.followthemoney.tech/
* `datasets` contains crawlers. Each crawler is defined using a `config.yml` file, and a `crawler.py` code file.
    * To run a crawler: `muckrake crawl <dataset_name>` in the project root.
    * When a crawler encounters uncertainty in any of the data it is parsing, it should crash or produce an error instead of emitting ambiguous data.
    * After running a crawler, output data is written to `data/datasets/<dataset_name>/`.
* `src/muckrake/api` contains a FastAPI server.
* `openlobbying` contains a Svelte app that displays the data served by the API.

## Coding hints

* All new crawlers should be written using typed Python. Suggest adding types to existing ones.
* Always use `uv` to run `muckrake` commands, eg. `uv muckrake crawl <dataset_name>`.
* Be extremely conservative in bringing in new dependencies. Libraries are listed in `pyproject.toml`.