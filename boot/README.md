# Boot

TuwaiqOS uses the [bootloader](https://github.com/rust-osdev/bootloader) crate (v0.11) without unstable Cargo `bindeps`.

## Flow

1. BIOS loads the first stage from `boot-bios-tuwaiqos.img`.
2. Bootloader loads the kernel ELF into memory.
3. Kernel entry: `kernel_main` in `kernel/src/main.rs`.
4. Output: `target/debug/boot-bios-tuwaiqos.img`.

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full boot sequence.
