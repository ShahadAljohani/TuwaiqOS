//! Physical memory discovery and heap setup.
//!
//! ## Stack vs heap
//!
//! - **Stack** — automatic storage for local variables and function call frames.
//!   Size is known at compile time and reclaimed when a function returns.
//! - **Heap** — dynamic storage requested at runtime through an **allocator**.
//!   A `Box`, `Vec`, or `String` lives on the heap until it is dropped.
//!
//! ## Why `no_std` needs `alloc`
//!
//! `#![no_std]` removes the standard library, including its OS-backed allocator.
//! The separate `alloc` crate still provides heap types, but **we** must supply
//! memory and implement [`GlobalAlloc`](core::alloc::GlobalAlloc) — see
//! [`crate::allocator`].
//!
//! The heap lives in a static kernel buffer so we never treat raw physical
//! addresses from the memory map as virtual pointers (which would corrupt RAM
//! when the bootloader does not map all physical memory).

use alloc::boxed::Box;
use alloc::string::String;
use alloc::vec::Vec;

use bootloader_api::BootInfo;

use crate::allocator;

/// One mebibyte of kernel heap — enough for early MVP features.
pub const HEAP_SIZE: usize = 1024 * 1024;

/// Backing storage for the linked-list allocator (in kernel virtual memory).
#[repr(align(4096))]
struct HeapStorage([u8; HEAP_SIZE]);

static mut HEAP_STORAGE: HeapStorage = HeapStorage([0; HEAP_SIZE]);

/// Set up the kernel heap before the shell or any `Box`/`Vec`/`String` is used.
pub fn init_heap(_boot_info: &BootInfo) {
    let start = unsafe { core::ptr::addr_of_mut!(HEAP_STORAGE.0) as *mut u8 as usize };
    allocator::init(start, HEAP_SIZE);
}

/// Run a small allocation smoke test using `Box`, `Vec`, and `String`.
pub fn memtest() -> Result<(), &'static str> {
    if !allocator::is_initialized() {
        return Err("heap not initialized");
    }

    // Box — single value on the heap.
    let value = Box::new(42u64);
    if *value != 42 {
        return Err("Box value mismatch");
    }
    drop(value);

    // Vec — growable heap buffer.
    let mut numbers = Vec::new();
    for index in 0..128 {
        numbers.push(index);
    }
    if numbers.len() != 128 || numbers[64] != 64 {
        return Err("Vec push/read failed");
    }
    drop(numbers);

    // String — UTF-8 text on the heap.
    let mut label = String::from("TuwaiqOS");
    label.push(' ');
    label.push_str("heap");
    if label != "TuwaiqOS heap" {
        return Err("String content mismatch");
    }

    Ok(())
}
