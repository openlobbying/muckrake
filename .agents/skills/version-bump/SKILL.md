---
name: version-bump
description: Version bump, release, tag, gh, PyPI, pyproject.toml. Use when asked to cut a new muckrake release, bump the package version, push a release tag, publish to PyPI, or create a GitHub release from this repo.
---

# Version Bump

Use this skill when the user wants a `muckrake` package version bump and GitHub release.

## Goal

Produce a clean release from the current branch by:

- choosing the correct next version
- updating package metadata
- validating the repo
- creating a release commit
- creating and pushing the version tag
- creating the GitHub release with `gh`
- verifying the publish workflow

## Safety Rules

- Inspect the repo before changing anything. Do not assume the current version is correct.
- Check for mismatches between `pyproject.toml`, local git tags, and GitHub releases.
- If the next version is ambiguous, ask the user for the exact target version instead of guessing.
- If the worktree is dirty, do not revert unrelated changes.
- Stage only the intended release files. Avoid sweeping unrelated edits into the release unless the user clearly wants the full worktree released.
- Keep the plain version in `pyproject.toml`, for example `0.2.0`, and reserve the `v` prefix for the git tag and GitHub release.
- Use an annotated version tag in the form `vX.Y.Z`.
- Use `uv` for Python commands. Do not use `python`, `python3`, or `pip` directly.
- If `gh` is unavailable or not authenticated, stop and tell the user exactly what blocked release creation.

## Release Checklist

1. Inspect state.

Run:

```bash
git status --short --branch
git log --oneline -10
git remote -v
git tag --sort=-creatordate
gh --version
gh auth status
gh release list --limit 20
```

Check:

- current branch and remote tracking branch
- dirty files
- recent commit style
- whether `gh` is installed and authenticated
- existing tags and releases

2. Resolve version ancestry.

Run the equivalent of:

```bash
git describe --tags --abbrev=0
git log --graph --decorate --oneline --all -20
gh release view <existing-tag>
```

Look for cases where:

- `pyproject.toml` says one version but GitHub already has a newer release
- the latest release tag exists on a different branch line
- the latest reachable local tag is not the latest GitHub release

If there is any mismatch, ask the user which version to release before proceeding.

3. Bump version files.

Update at minimum:

- `pyproject.toml`

Do not edit `uv.lock` unless the package version is recorded there or a validation command updates it intentionally.

4. Validate before release.

Run:

```bash
uv sync --all-groups
uv run pytest
uv build
```

Do not create the release commit until these pass, unless the user explicitly wants a release despite failures.

5. Inspect the final diff.

Before committing, review:

```bash
git status --short
git diff --stat
git diff -- <intended files>
git log --oneline -10
```

Make sure the release commit contains only the intended changes.

6. Commit the release.

Use a concise commit message matching repo style. For this repo, `release: vX.Y.Z` is acceptable.

Example:

```bash
git add pyproject.toml
git commit -m "release: v0.2.0"
```

7. Tag and push.

Use an annotated tag:

```bash
git tag -a v0.2.0 -m "v0.2.0"
git push origin <branch>
git push origin v0.2.0
```

8. Create the GitHub release.

The PyPI publish workflow is tag-driven via `.github/workflows/publish.yml`. Create the GitHub release object explicitly with `gh` after pushing the tag:

```bash
gh release create "v0.2.0" --verify-tag --title "v0.2.0" --generate-notes --latest
```

9. Verify the publish workflow.

Check recent workflow runs and release details:

```bash
gh run list --limit 10 --json databaseId,displayTitle,event,headBranch,headSha,status,conclusion,workflowName
gh run view <run-id> --json status,conclusion,url,workflowName,jobs
gh run watch <run-id> --interval 5
gh release view v0.2.0 --json url,tagName,isLatest
```

Confirm:

- the GitHub release exists
- the `Publish` workflow started for the tag
- the workflow completed successfully or any failure has been reported clearly
- the package appears on PyPI after the workflow succeeds

## What To Report Back

When done, report:

- the released version
- the release commit SHA
- the tag name
- the GitHub release URL
- whether the PyPI publish workflow passed
- any warnings that did not block release
