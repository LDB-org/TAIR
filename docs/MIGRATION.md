# Standalone repository migration

The engine/tool-call work was copied from the development OpenJev checkout into
this repository. The source checkout remains intact. The imported experiment
archive is not a rewritten or selectively successful subset.

## Included

- 2,973 original code, fixture, test, documentation and experiment files.
- 2,853 original experimental files, preserved byte for byte.
- All 2,828 entries in original checksum manifests, including failed runs.
- OpenJev source helpers and their tests, with the original MIT notice and namespace.
- New English/Chinese READMEs, architecture, reproduction guide, experiment index,
  CPU example, standalone package metadata and verification workflow.

The manifest lists the original imported hashes. Maintained runners were changed
only to replace private deployment defaults with `ENGINE_TOOLCALL_HOST` and
`PI_PACKAGE_ROOT`. This does not alter frozen requests, responses or source
snapshots. The original OpenJev website, browser demo, unrelated phase-1 evaluation
records, model weights, virtual environment and caches were not imported.

## Validation in the standalone environment

- Editable installation of `engine-toolcall` with its test dependencies.
- **149 tests passed**, no skips. The four upstream browser-demo tests are outside
  the standalone project; historical reports mentioning 153 tests remain intact.
- `benchmarks/verify_archive.py`: 2,853 original experimental files and 2,828
  original checksum entries passed.
- The combined experiment summary recomputed exactly to the frozen summary.
- All ten combined engine traces passed the sampler/KV verifier.
- Maintained Python sources compile; primary documentation links resolve.
- The deterministic example updates the workers default from 10 to 6.
- Initial private-key, GitHub-token and literal-Bearer pattern scan found no matches
  in imported files. This is a bounded pattern scan, not a security certification.

No GPU benchmark or remote deployment was run during migration. At the migration
snapshot, the GitHub workflow had been prepared but had not run remotely; the
repository was left uncommitted for review before initial publication.

Current project name: **TAIR — Typed Action Inference Runtime**. The installation
name is now `tair`; the migration snapshot above retains its original naming.
See [naming and compatibility](NAMING.md).

## Initial publication validation

Before the initial TAIR publication, the standalone environment passed all 162
tests. Archive verification passed for 2,853 imported experiment files and 3,046
checksum entries across the retained archive. The compact-edit example ran
successfully. These checks validate the repository and its evidence integrity;
remote CI status is reported separately by GitHub Actions.
