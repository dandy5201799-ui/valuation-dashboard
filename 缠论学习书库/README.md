# Chan Theory Books

[中文 README](./README.zh-CN.md)

Books for learning Chan theory through one merged chart-reading tutorial and a chart-marking tool companion. The Chinese README is the authoritative entry for the current draft.

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <a href="./book2-chan-practice/">
        <img src="./book2-chan-practice/assets/cover.svg" alt="Chan Chart Reading Tutorial" width="240">
      </a>
      <br>
      <strong>Chan Chart Reading Tutorial</strong>
      <br>
      <a href="./book2-chan-practice/index.md">Read draft</a>
    </td>
    <td align="center" valign="top" width="50%">
      <a href="./book3-auto-marker/">
        <img src="./book3-auto-marker/assets/cover.svg" alt="Chan Marking Tool" width="240">
      </a>
      <br>
      <strong>Chan Marking Tool</strong>
      <br>
      <a href="./book3-auto-marker/index.md">Read draft</a>
    </td>
  </tr>
</table>

This repository is organized in the same spirit as `harness-books`: each book has its own `book.json`, `README.md`, `index.md`, `SUMMARY.md`, chapters, appendices, diagrams, assets, and styles. The root README only gives the map.

## Local books

- [Chan Chart Reading Tutorial](./book2-chan-practice/index.md)
- [Chan Marking Tool](./book3-auto-marker/index.md)

## Project map

- [Project spec](./SPEC.md): active folders, archive rules, build outputs, and commit boundaries.
- [Project status](./PROJECT_STATUS.md): current progress and next review points.
- [`book2-chan-practice/`](./book2-chan-practice/): main book source.
- [`book3-auto-marker/`](./book3-auto-marker/): companion tool book source.
- [`tools/`](./tools/): site build scripts.
- [`_archive/`](./_archive/): old drafts, early diagrams, and conversation notes.

## Build

Build the unified online library:

```bash
python3 tools/build_chan_site.py
```

If Honkit is available, each book can also be built from its own directory:

```bash
npx honkit build book2-chan-practice
npx honkit build book3-auto-marker
```

The lightweight helper script can also build any installed Honkit project:

```bash
python3 tools/book-kit/build_honkit.py book2-chan-practice
```

## Reliability note

The diagrams included here are curated from later corrected materials. Early diagrams that were unclear or challenged during study are not treated as canonical examples.
