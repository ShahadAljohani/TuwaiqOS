# TuwaiqOS Roadmap

## v0.5 (current)

- [x] Bootloader + kernel + framebuffer/VGA console
- [x] PS/2 keyboard with Shift and punctuation
- [x] Shell with history, tab completion, `tuwaiq@os:~$` prompt
- [x] Heap allocator
- [x] TuwaiqFS v2 persistent tree filesystem
- [x] Cooperative task scheduler (`ps`, `taskinfo`, `kill`)
- [x] Loopback networking foundation
- [x] AI Bridge stub (`ask`, `ai status`)
- [x] Program loader (`run hello`, `run demo`)
- [x] Built-in apps: `notes`, `editor`, `monitor`

## v0.6 — in progress

- [x] Real interrupt architecture: GDT/TSS, IDT with exception handlers,
      PIC remap, PIT timer tick, interrupt-driven keyboard, real `uptime`
- [x] Physical frame allocator + paging: real physical memory access,
      `OffsetPageTable`, a heap backed by mapped pages instead of a static
      array, memory diagnostics in `sysinfo`/`monitor`
- [x] Preemptive scheduler: real per-task stacks and a hand-written
      context switch, timer-driven preemption (50ms slices), `spawn`/
      `yield_now`/`sleep_ticks`/`exit`; `ps`/`taskinfo`/`kill` act on real
      scheduler state. Demonstrated with 3 concurrently-scheduled tasks
      (shell, idle, a heartbeat task) verified live in QEMU.
- [ ] Per-process address spaces / user-mode memory isolation (frame
      allocator, mapper, and a real scheduler all exist now; nothing uses
      them together for process isolation yet -- that's Phase 4)
- [ ] ELF program loader
- [ ] Real NIC driver (e1000 / virtio-net)
- [ ] AI Bridge HTTP client wired to gateway
- [ ] `cd` command and path-aware completion

## v0.7 — planned

- [ ] User mode and syscalls
- [ ] FAT32 read-only partition support
- [ ] VirtualBox/VMware optimized drivers
- [ ] Package manager for built-in apps

## v1.0 — vision

- [ ] Multi-user sessions
- [ ] TLS + DNS for AI Bridge
- [ ] Self-hosting toolchain on TuwaiqOS
- [ ] Public SDK for TuwaiqOS applications

## Historical note

This project began as AbdullahOS (learning OS). It was renamed to TuwaiqOS at v0.5 for public release.
