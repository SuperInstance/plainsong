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
   run. It is not, however, why the early tags have no GitHub Release -- that was
   the publisher, below.
4. **release** — creates the GitHub Release with the artifacts attached and
   generated notes. This needs `contents: write`; without it the step fails at the
   very end, after a successful publish, which is the worst place to find out.

## Trusted Publishing

The workflow authenticates to PyPI with a short-lived OIDC credential, which is
why the publish job declares `id-token: write`. There is no API token in this
repository and there should never be one.

The publisher is configured **on PyPI, not here**, and getting it wrong is not
loud: the build succeeds, the artifacts are produced, and the publish step dies
at the end with `invalid-publisher: valid token, but no corresponding
publisher`. Because **release** needs **publish**, no GitHub Release is created
either. That is how `v1.0.1`, `v1.1.0`, `v1.2.0` and `v1.3.0` came to be four
tags with no releases while all four versions sat on PyPI, uploaded by hand.

| field | value |
|---|---|
| Owner | `SuperInstance` |
| Repository | `plainsong` |
| Workflow | `release.yml` |
| Environment | *leave empty* |

**Which page you use depends on whether the project exists.** PyPI has two, and
the account-level one refuses a name that is already taken rather than
redirecting you:

- The project exists → its own settings,
  <https://pypi.org/manage/project/plainsong/settings/publishing/>.
- The name is unclaimed → a *pending* publisher at
  <https://pypi.org/manage/account/publishing/>. This is the only case where the
  "PyPI project name" box is yours to fill in.

The repository field is `plainsong`, not `plainsong-studio` or
`tapscript-studio` — the GitHub repository has been renamed twice, and a
publisher configured against an old name authenticates nothing. If a run fails,
read the claims the error prints: `repository`, `workflow_ref` and `environment`
are exactly what the publisher has to match, and `environment: MISSING` means
leave that field empty rather than guessing at a name.

### Re-running a failed release

Once the publisher is fixed, "Re-run failed jobs" on the run will publish and
create the release — **but only if that tag's workflow carries `skip-existing`.**
A re-run uses the workflow file as it was at the tag, not as it is on master. At
`v1.0.1`, `v1.1.0` and `v1.2.0` it does not, so those re-runs authenticate and
then abort on "file already exists" for files that are already on PyPI. Those
three cannot be backfilled by re-running; the changelog is their record. From
`v1.3.0` on, the flag is in the tree and a re-run completes.

## The sibling

`plainsong-mcp` is a separate repository and a separate release. It depends on
this package by version specifier (`plainsong>=1.1.0`), so this one ships first
and the floor is raised there afterwards, never the reverse.

It needs its own pending publisher — owner `SuperInstance`, repository
`plainsong-mcp`, workflow `release.yml`, environment empty — created at the
account-level page above, because the name is still unclaimed on PyPI.

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
