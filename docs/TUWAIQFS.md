# TuwaiqFS v2 — Disk Layout

TuwaiqFS is the persistent filesystem for TuwaiqOS. It stores the **full directory tree** on the boot disk so files, directories, and metadata survive reboot.

## Sector map (512 bytes per sector)

| LBA range   | Size        | Purpose |
|-------------|-------------|---------|
| 0–8191      | ~4 MiB      | Bootloader + kernel (do not modify) |
| 8192        | 512 B       | Superblock |
| 8193–8464   | Reserved    | Legacy v1 data slots |
| 8465–8712   | 124 KiB     | Metadata tree blob |

## Superblock (LBA 8192)

| Offset | Size | Field |
|--------|------|-------|
| 0      | 8    | Magic: `TQFSv2\0\0` |
| 8      | 4    | Version (2) |
| 12     | 4    | Metadata region LBA |
| 16     | 4    | Metadata sector count |
| 20     | 4    | Metadata length in bytes (see note below) |

## Metadata format

The metadata blob begins with `TREE` followed by records:

| Field | Size | Description |
|-------|------|-------------|
| kind  | 1    | 1 = file, 2 = directory |
| path_len | 1 | Length of path string |
| path  | variable | e.g. `hello.txt` or `docs/notes.txt` |
| content_len | 2 | File size (files only) |
| content | variable | UTF-8 file body |

### Metadata length is stored explicitly, not inferred

Earlier builds inferred where the metadata blob ended by scanning sector 0
for a zero byte followed by nothing but zero padding. That heuristic was
wrong: `content_len` is a little-endian `u16`, so any file under 256 bytes
produces a zero byte (the length's high byte) immediately followed by real,
non-zero content -- indistinguishable from "data ends here" under the old
scan. The reader then treated the entire sector as data, the deserializer
choked on trailing zero bytes it misread as more records, and the mount
silently fell back to an empty filesystem. In practice this meant **every
reboot silently discarded the filesystem** for any file small enough to hit
this case -- which is effectively all of them, including the project's own
`write hello.txt hello` validation example. The superblock's metadata
length field (offset 20) replaces the heuristic: the writer records the
real byte count, and the reader reads back exactly that many bytes. No
scan, no guessing.

## Limits

- Max metadata size: 124 KiB
- Max file size: 2048 bytes per file
- UTF-8 text files
- Nested directories supported

## Boot sequence

1. ATA driver reads superblock at LBA 8192
2. If magic is wrong, format the TuwaiqFS region
3. Deserialize metadata blob into an in-memory tree
4. Shell commands operate on the tree; every mutation syncs back to disk

## Historical note

TuwaiqFS v1 (formerly AbdullahFS) used a flat root directory only. v2 replaces that with full-tree persistence.
