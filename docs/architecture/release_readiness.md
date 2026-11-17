# Release readiness

This note is the only new file for the current release surface. It publishes the versioned interface constants. `INTERFACE_SCHEMA` is `complaint-generator/module-interface@1` and `INTERFACE_VERSION` is `1.0.0`.

Historical plan and backlog documents are not the current module contract.

## Root build keepers

These root build files stay at the root. They are keepers.

- `Makefile`
- `package.json`
- `playwright.config.js`
- `MANIFEST.in`
- `pyproject.toml`
- `setup.py`
- `requirements.txt`
- `pytest.ini`

## Packaged asset trees

`templates` and `static` are packages included by the setuptools find lists.

## Paths that are not product source

The three logs `logs/UNCAUGHT_EXCEPTION.log`, `logs/app.log`, and `logs/test.log` are not product source. The `datasets/CCINDEX_WARC_CACHE_DIR` range cache is not product source.

`patches/` remains tracked autopatch scratch and is not a product package.

## Example set

The example set is 26 scripts in `docs/EXAMPLES.md`.

## Linked release and architecture maps

This note links the existing release and architecture maps and does not copy their tables.

- [Root release](docs/architecture/root_release.md)
- [Release build](docs/RELEASE.md)
- [Current layout](docs/architecture/current_layout.md)
- [Owner currency](docs/architecture/owner_currency.md)
- [Cohesive moves](docs/architecture/cohesive_moves.md)
- [Consolidation modules](docs/architecture/consolidation_modules.md)
- [Module boundaries](docs/architecture/module_boundaries.md)
- [Module seams](docs/architecture/module_seams.md)
