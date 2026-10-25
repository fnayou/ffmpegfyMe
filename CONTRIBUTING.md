# Contributing to ffmpegfyMe

Thanks for your interest in contributing to ffmpegfyMe.

## How to contribute

- Fork the repository.
- Create a feature branch.
- Open a pull request against the protected `main` branch.

## Commit messages

Use Conventional Commits:

```text
<type>: <short description>
```

Common types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
`perf`, `ci`, `build`, `revert`.

## Pull requests

- All changes to the protected `main` branch go through pull request review.
- Rebase is the only allowed merge method.
- Keep pull requests small and focused.

## Tests and CI

Use an isolated virtual environment to run tests with branch coverage:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m coverage run -m unittest discover -v
.venv/bin/python -m coverage report --show-missing
```

The reported `ffmpegfyMe.py` percentage combines deterministic policy and
integration code. It is a module-level baseline, not core-policy-only
coverage. Issue #32 defines the target scope.

- The Python test suite runs on PRs and pushes to main.
- Watch the required CI checks on the pull request and run the current CI
  checks before requesting review.

## Getting help

- See [SUPPORT.md](SUPPORT.md) for how to ask questions and get help.
- See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
- See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

Thank you for helping improve ffmpegfyMe.
