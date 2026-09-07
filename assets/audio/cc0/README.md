# Auralis CC0 Stock Audio

This directory contains a curated, redistributable library for common
audio-drama ambience and Foley. Every included file is sourced from an asset
page that declares the work under Creative Commons Zero 1.0 (CC0).

The library intentionally excludes tracks that are non-commercial, require
attribution, or prohibit redistribution as standalone files. Source links and
authors are recorded in `catalog.json` and `LICENSES.md` even though CC0 does
not require attribution.

## Contents

- `rubberduck-sfx100-v2/`: 63 selected effects from the 100 CC0 SFX #2 pack.
- `supplemental/`: 9 ambience and Foley files from individually verified CC0
  OpenGameArt submissions.
- `catalog.json`: categories, source records, tags, and relative file paths.
- `SHA256SUMS`: integrity hashes for all audio files.

The Auralis media-library UI reads this catalog at runtime. Built-in assets are
read-only; binding one to a line copies it into the project so later project
editing does not mutate this source library.

## Tag retrieval and curation (2026-09-07)

79 assets are listed by default: 29 additional external sounds and 2 existing original Demo effects were added, while 24 similar numbered variants were archived from search. No byte-identical pairs were found. Archived files retain their IDs and remain resolvable for old projects. See `curation-20260907.json`.

Each file has source-specific Chinese tags. Script adaptation produces `soundTags`; matching uses these tags locally without an LLM request. New user imports can be tagged manually.
