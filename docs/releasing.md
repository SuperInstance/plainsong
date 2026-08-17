# Releasing

A release is a pushed tag. Everything after that is automatic.

## Cutting one

```bash
# 1. Agree the version. It lives in two places and they must match.
#    plainsong/version.py   __version__ = "1.1.0"
#    pyproject.toml         version = "1.1.0"

# 2. Move the Unreleased section of CHANGELOG.md under the new number, and set
#    the date to the day you actually tag. A version that has not shipped has no
#    date worth trusting.

# 3. Prove it before tagging.
python3 -m unittest discover -s tests
python3 -m plainsong spec
python3 -m plainsong check docs examples plainsong/songbook README.md

# 4. Tag and push.
git tag -a v1.1.0 -m "1.1.0"
git push origin v1.1.0
```

## What the workflow then does

`.github/workflows/release.yml` triggers on any tag matching `v*`:

1. **test** — checks the tag against `plainsong/version.py`, then runs the suite,
   the specs and `check` over every source. Nothing downstream runs if any of it
   fails, so a tag on a broken tree publishes nothing. The tag check is there
   because the tag is the only thing that says which version a release is, and
   nothing in the tree knows about it: a `v1.1.0` tag on a tree still saying
   1.0.0 would publish 1.0.0 under a release page claiming otherwise, and PyPI
   will not accept that filename a second time to let you correct it.
2. **build** — `python -m build`, producing a wheel and an sdist.
3. **publish** — uploads to PyPI using
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/). There is no
   API token in the repository and there should never be one: the job authenticates
   with a short-lived OIDC identity, which is why it declares `id-token: write`.
4. **release** — creates the GitHub Release with the artifacts attached and
   generated notes. This needs `contents: write`; without it the step fails at the
   very end, after a successful publish, which is the worst place to find out.

## Before the first release

Trusted Publishing has to be configured once, on PyPI, before the publish job can
work. On the project's PyPI page add a publisher with:

- owner `SuperInstance`, repository `plainsong`
- workflow `release.yml`
- environment: leave empty unless you add one to the workflow

Until that exists the publish step fails with an authentication error, and the
fix is on PyPI rather than in this repository.

## What ships in the wheel

The package carries data files it needs at runtime, listed in
`[tool.setuptools.package-data]`:

| | |
|---|---|
| `llm/catalog.json` | the provider catalogue |
| `agent/prompts/*.md` | the composer and builder prompts |
| `interfaces/web/*.html` | the web interface |
| `spec_files/*.toml` | the specs `plainsong spec` runs |

Anything the code reads at runtime must be **inside** `plainsong/`, because a
wheel carries only what is under the package. The specs used to live in a
top-level `specs/` directory and were therefore absent from every install —
`plainsong spec` reported "no specs found" to everybody who had not cloned the
repository. If you add a new kind of data file, add it here and then verify it
the way below.

## Verifying a build by hand

Do not trust the wheel because it built. Install it somewhere clean, outside the
source tree, so nothing resolves out of the working directory by accident:

```bash
python3 -m build
python3 -m venv /tmp/relcheck
/tmp/relcheck/bin/pip install dist/*.whl

cd /tmp                      # leave the repo behind
/tmp/relcheck/bin/plainsong --version
/tmp/relcheck/bin/plainsong new "Smoke Test" -o smoke.song
/tmp/relcheck/bin/plainsong compile smoke.song -o smoke.mid
/tmp/relcheck/bin/plainsong spec
```

`spec` is the one that catches packaging mistakes, because it exercises the data
files. If it reports "no specs found", or fails a check that passes in the
repository, the wheel is wrong rather than the code.

One trap worth knowing: a spec that shells out must use `{python}`, which
substitutes the interpreter actually running, not `python3`. Hardcoding `python3`
works in a checkout and fails in every virtualenv and pipx install, reporting
"No module named plainsong" about a package that installed perfectly well.
