# Contributing

Thanks for contributing.

## Development setup

1. Clone repository.
2. Install dependencies:

```shell
pip install -r requirements.txt
```

3. Run CLI:

```shell
py .\process.py
```

4. Run web app:

```shell
py .\local_web.py
```

## Pull request guidelines

- Keep changes focused and small.
- Add or update docs when behavior changes.
- Do not commit large generated files in `output/`.
- Preserve backward compatibility for existing CLI and web entrypoints.

## Commit style

Prefer clear, action-oriented commit messages, for example:

- feat(web): add queue retry controls
- fix(convert): initialize COM in worker thread
- docs: split webapp and configuration guides
