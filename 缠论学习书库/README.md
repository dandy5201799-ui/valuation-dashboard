# Chan Theory Books

[中文 README](./README.zh-CN.md)

Three books for learning Chan theory from visual structure to strict rules and automated marking.

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <a href="./book1-chan-foundation/">
        <img src="./book1-chan-foundation/assets/cover.svg" alt="Chan Structure Foundations" width="240">
      </a>
      <br>
      <strong>Book 1: Structure Foundations</strong>
      <br>
      <a href="./book1-chan-foundation/index.md">Read draft</a>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="./book2-chan-practice/">
        <img src="./book2-chan-practice/assets/cover.svg" alt="Practice: Zones, Confirmation, Failure" width="240">
      </a>
      <br>
      <strong>Book 2: Practice</strong>
      <br>
      <a href="./book2-chan-practice/index.md">Read draft</a>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="./book3-auto-marker/">
        <img src="./book3-auto-marker/assets/cover.svg" alt="Automatic Marker Tool" width="240">
      </a>
      <br>
      <strong>Book 3: Auto Marker</strong>
      <br>
      <a href="./book3-auto-marker/index.md">Read draft</a>
    </td>
  </tr>
</table>

This repository is organized in the same spirit as `harness-books`: each book has its own `book.json`, `README.md`, `index.md`, `SUMMARY.md`, chapters, appendices, diagrams, assets, and styles. The root README only gives the map.

## Local books

- [Book 1 — Chan Structure Foundations](./book1-chan-foundation/index.md)
- [Book 2 — Observation Zones, Confirmation Points, and Failure Lines](./book2-chan-practice/index.md)
- [Book 3 — Chan Automatic Marker Tool](./book3-auto-marker/index.md)

## Build

This is a draft book workspace. If Honkit is available, each book can be built from its own directory:

```bash
npx honkit build book1-chan-foundation
npx honkit build book2-chan-practice
npx honkit build book3-auto-marker
```

The lightweight helper script can also build any installed Honkit project:

```bash
python3 tools/book-kit/build_honkit.py book1-chan-foundation
```

## Reliability note

The diagrams included here are curated from later corrected materials. Early diagrams that were unclear or challenged during study are not treated as canonical examples.
