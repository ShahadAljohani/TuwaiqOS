//! Kernel heap allocator.
//!
//! A `no_std` kernel cannot use the Rust standard library's allocator. The
//! `alloc` crate provides types like `Box`, `Vec`, and `String`, but only after
//! we register a global allocator with `#[global_allocator]`.
//!
//! This module wraps a simple linked-list allocator backed by a contiguous
//! region of physical RAM described by the bootloader memory map.

use core::sync::atomic::{AtomicBool, Ordering};

use linked_list_allocator::LockedHeap;

/// Global heap instance used by `Box`, `Vec`, `String`, and friends.
#[global_allocator]
static HEAP: LockedHeap = LockedHeap::empty();

static INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Initialize the heap over `[start, start + size)`.
///
/// Must be called once before any heap allocation.
pub fn init(start: usize, size: usize) {
    unsafe {
        HEAP.lock().init(start as *mut u8, size);
    }
    INITIALIZED.store(true, Ordering::SeqCst);
}

/// Report whether the heap has been initialized.
pub fn is_initialized() -> bool {
    INITIALIZED.load(Ordering::SeqCst)
}

/// Bytes currently allocated out of the heap.
pub fn used() -> usize {
    HEAP.lock().used()
}

/// Bytes still available in the heap.
pub fn free() -> usize {
    HEAP.lock().free()
}
