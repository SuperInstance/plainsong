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

# 4. Tag the commit that carries the bump -- not whatever master happened to be
#    when you started. Merge the version bump FIRST, then pull, then tag.
git pull
grep __version__ plainsong/version.py    # must be the version you are tagging
git tag -a v1.1.0 -m "1.1.0"
git push origin v1.1.0
```

**Tag the right commit.** `v1.2.0` was once created on the commit before the
version bump merged. The tree there still said 1.1.0, so the workflow's tag
check refused it -- correctly, and that is the guard doing its job -- and a
local `python -m build` in the same clone quietly produced `1.1.0` artifacts
that PyPI then rejected as duplicates. The one-line `grep` above is what catches
it. If you have already pushed a tag to the wrong commit:

```bash
git tag -d v1.2.0
git push origin :refs/tags/v1.2.0     # delete it from the remote
git pull                              # get the real bump
git tag -a v1.2.0 -m "1.2.0"
git push origin v1.2.0
```

Do not use a shallow (`--depth 1`) clone for that: deleting and re-pushing a tag
needs the real history.

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
   It passes `skip-existing`, so a version already on PyPI is skipped rather than
   failing the job. That matters more than it sounds: without it, a release whose
   files reached PyPI some other way -- a manual `twine upload`, or an attempt
   that uploaded and then failed later -- can never be re-run, because the upload
   aborts on "file already exists" and the **release** step below never gets to
   run. That is exactly how 1.0.1, 1.1.0 and 1.2.0 ended up as tags with no
   GitHub Release.
4. **release** — creates the GitHub Release with the artifacts attached and
   generated notes. This needs `contents: write`; without it the step fails at the
   very end, after a successful publish, which is the worst place to find out.

## Before the first release

Nothing has ever been published. `plainsong` is unclaimed on PyPI, and so is
`plainsong-mcp`. Two things must happen once, in this order, and neither can be
done from inside this repository.

### 1. Claim the name with Trusted Publishing

Trusted Publishing is how the workflow authenticates. There is no API token in
this repository and there should never be one — the job proves its identity with
a short-lived OIDC credential, which is why it declares `id-token: write`.

Because `plainsong` does not exist on PyPI yet, this is a **pending publisher**,
created at <https://pypi.org/manage/account/publishing/> rather than on a project
page that does not exist. Fill in:

| field | value |
|---|---|
| PyPI project name | `plainsong` |
| Owner | `SuperInstance` |
| Repository name | `plainsong` |
| Workflow name | `release.yml` |
| Environment name | *leave empty* |

The repository field is `plainsong`, not `plainsong-studio` — the GitHub
repository was renamed. A publisher configured against the old name authenticates
nothing.

### 2. Check the version and the changelog, then tag

```bash
# The version lives in two places and a test fails if they disagree.
grep version pyproject.toml plainsong/version.py

# CHANGELOG.md must have the release under its number and today's date,
# with no `## Unreleased` section left above it.

git tag -a v1.0.0 -m "1.0.0"
git push origin v1.0.0
```

The workflow does the rest. Watch it: the publish step runs after a successful
build, so an authentication failure there means the artefacts were built and
thrown away, and you fix it on PyPI and re-tag rather than in this repository.

### What to do if the tag was wrong

Delete the tag locally and remotely, fix the tree, tag again. A version number
that reached PyPI cannot be reused — PyPI refuses a filename it has already
seen, even after a delete — so if a bad `1.0.0` publishes, the next release is
`1.0.1` and `1.0.0` stays broken forever. That is why the workflow refuses a tag
that disagrees with `plainsong/version.py` before it builds anything.

### Then the sibling

`plainsong-mcp` depends on this package by git URL while this one is unpublished:

```toml
plainsong @ git+https://github.com/SuperInstance/plainsong@master
```

Once `plainsong` is on PyPI, change that to a version specifier
(`plainsong>=1.0`) and publish `plainsong-mcp` the same way — its own pending
publisher, owner `SuperInstance`, repository `plainsong-mcp`, workflow
`release.yml`. It is the only line in that repository that has to change.

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
