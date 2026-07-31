# Auralis CC0 Stock Audio

This directory contains a small, redistributable starter library for common
audio-drama ambience and Foley. Every included file is sourced from an asset
page that declares the work under Creative Commons Zero 1.0 (CC0).

The library intentionally excludes tracks that are non-commercial, require
attribution, or prohibit redistribution as standalone files. Source links and
authors are recorded in `catalog.json` and `LICENSES.md` even though CC0 does
not require attribution.

## Contents

- `rubberduck-sfx100-v2/`: 23 selected effects from the 100 CC0 SFX #2 pack.
- `supplemental/`: 9 ambience and Foley files from individually verified CC0
  OpenGameArt submissions.
- `catalog.json`: categories, source records, tags, and relative file paths.
- `SHA256SUMS`: integrity hashes for all audio files.

The Auralis media-library UI reads this catalog at runtime. Built-in assets are
read-only; binding one to a line copies it into the project so later project
editing does not mutate this source library.
