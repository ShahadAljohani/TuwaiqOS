# Release Notes — TuwaiqOS v0.5

**Version:** TuwaiqOS v0.5  
**Date:** June 2026  
**Tagline:** Experimental AI-Native Operating System written in Rust

## Highlights

### Project rename

- AbdullahOS → **TuwaiqOS**
- AbdullahFS → **TuwaiqFS v2**
- Disk image: `boot-bios-tuwaiqos.img`
- Boot banner: `TuwaiqOS v0.5`
- Shell prompt: `tuwaiq@os:~$`

### Milestone 1 — Program loader

- `kernel/src/loader.rs` and `kernel/src/programs/`
- Commands: `run hello`, `run demo`
- Registry architecture ready for future ELF loading

### Milestone 2 — TuwaiqFS v2

- Full directory tree persists across reboot
- Nested paths supported (e.g. `.notes/todo`)
- Metadata blob at LBA 8465+

### Milestone 3 — Terminal experience

- Command history (16 entries)
- Arrow Up/Down recall
- Tab completion for commands, programs, and files
- Improved `clear` / `cls`
- Dynamic prompt with `~` for home directory

### Milestone 4 — System applications

- `notes create/list/show`
- `editor <file>` — view and edit instructions
- `monitor` — RAM, tasks, filesystem, network snapshot

### Milestone 5 — Public release preparation

- README, ROADMAP, ARCHITECTURE, CONTRIBUTING, LICENSE
- QEMU and VirtualBox setup instructions
- Architecture diagrams

## Validation commands

```text
help
ls
touch hello.txt
write hello.txt hello
cat hello.txt
reboot
cat hello.txt
ps
sysinfo
notes create todo
notes list
monitor
run hello
```

## Known limitations

- Cooperative scheduler only (no preemption)
- Loopback networking only (no real NIC)
- AI Bridge remains offline stub
- Max file size 2048 bytes
- No `cd` command yet (always operate from mounted tree root context)

## Upgrade from AbdullahOS

Disk images from AbdullahFS v1 will be reformatted on first boot (new `TQFSv2` magic). Re-create files after upgrading.

## Historical note

TuwaiqOS v0.5 is the public rebranding of the AbdullahOS learning project.
