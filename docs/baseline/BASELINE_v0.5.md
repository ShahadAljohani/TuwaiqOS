# TuwaiqOS v0.5 — Verified Baseline (Phase 0)

Recorded 2026-08-05, before any Phase 1+ changes, as the point-in-time reference
that all later work must not regress. This is not a plan — every item below was
actually executed and observed.

## Build verification

```
$env:RUSTUP_TOOLCHAIN = "nightly-2026-06-01"
cargo build --package kernel --target x86_64-unknown-none   # OK, 10 warnings, 0 errors
cargo build --package tuwaiqos                                # OK, produces target/debug/boot-bios-tuwaiqos.img
```

Image produced: `target/debug/boot-bios-tuwaiqos.img` (6,784,000 bytes).

Toolchain confirmed: `nightly-2026-06-01-x86_64-pc-windows-msvc` (matches
`rust-toolchain.toml`), `cargo 1.98.0-nightly`.

Pre-existing warnings at baseline (all non-fatal, none introduced by this audit):
`NetDriver` trait methods unused, `HttpResponse`/`HttpClient` unused,
`schedule_tick` unused, `vga_buffer::print_prompt` unused, and one
`static_mut_refs` lint in `net/mod.rs`. These are tracked, not silently
carried forward — see `ROADMAP.md` Phase 1+ work removing `static mut`.

## Boot verification

QEMU was not on `PATH` but is installed at `C:\Program Files\qemu\`. Boot was
verified **headless** (`-display none`) using the QEMU human monitor over TCP
to issue `screendump`, since the kernel has no serial output yet (this gap is
closed in Phase 1 — see `kernel/src/serial.rs`).

```
qemu-system-x86_64.exe -drive format=raw,file=target\debug\boot-bios-tuwaiqos.img `
  -m 128M -display none -monitor tcp:127.0.0.1:<port>,server,nowait -no-reboot
```

Result: **confirmed boot to interactive shell**, screenshot saved at
`docs/baseline/v0.5-boot-shell.png`, showing:

```
TuwaiqOS v0.5
AI-Native Experimental Operating System

tuwaiq@os:~$
```

Timing note: full boot (BIOS → bootloader → kernel → mounted FS → shell
prompt) took approximately 15-20 seconds in this environment under QEMU/TCG,
dominated by the 248 sequential polled-PIO sector reads TuwaiqFS performs at
mount (each with its own busy-wait loop). This is expected given the current
polling-only ATA driver and is not a regression.

## Regression checklist (manual, re-run after every phase)

This supersedes `scripts/validate-phases.ps1` as the authoritative list —
same content, now with expected results recorded so a re-run has a clear
pass/fail bar, not just "did it print *something*".

| Command | Expected result at v0.5 baseline |
|---|---|
| `help` | Lists all ~29 commands |
| `ls` | `(empty)` on fresh disk |
| `touch hello.txt` | `Created file: hello.txt` |
| `write hello.txt hello` | `Wrote to: hello.txt` |
| `cat hello.txt` | `hello` |
| `reboot` | Machine resets via 8042 pulse, reboots to same shell |
| `cat hello.txt` (after reboot) | `hello` — proves TuwaiqFS persistence |
| `ps` | `PID NAME` table: `1 shell`, `2 idle` |
| `sysinfo` | OS/arch/RAM/heap/fs/tasks/network/framebuffer lines |
| `notes create todo` | `Created note: todo` |
| `notes list` | `todo` |
| `monitor` | RAM/Tasks/Filesystem/Network snapshot |
| `run hello` | `Hello from TuwaiqOS!` / `Program: hello (built-in)` |

Any future change that alters the output of these commands must be a
**deliberate, documented improvement** (e.g. real `ps` output once the
scheduler is real), never an accidental regression.

## Verified QEMU screenshot workflow (used for all future visual validation)

Since the kernel had no serial output at baseline, visual QEMU verification
was done by scripting the QEMU human monitor:

1. Launch QEMU with `-display none -monitor tcp:127.0.0.1:<port>,server,nowait -no-reboot`.
2. Wait for boot to settle (~20s empirically).
3. Connect to the monitor port and send `screendump <path>.ppm`.
4. Convert with `ffmpeg -y -i <path>.ppm -update 1 <path>.png` and view.

Phase 1 adds serial output specifically so this heavyweight process is no
longer required for headless validation going forward.
