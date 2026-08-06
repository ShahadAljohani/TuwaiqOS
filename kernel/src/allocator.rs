//! Kernel heap allocator.
//!
//! A `no_std` kernel cannot use the Rust standard library's allocator. The
//! `alloc` crate provides types like `Box`, `Vec`, and `String`, but only after
//! we register a global allocator with `#[global_allocator]`.
//!
//! This module wraps a simple linked-list allocator backed by a contiguous
//! region of physical RAM (see `memory.rs`/`paging.rs`).
//!
//! ## Interrupt safety (load-bearing, not incidental)
//!
//! `linked_list_allocator::LockedHeap` -- which every `Box`/`Vec`/`String`
//! allocation and deallocation goes through via `#[global_allocator]` --
//! wraps a plain `spinning_top::Spinlock` with no interrupt awareness at
//! all. That is dangerous on a preemptive kernel: if a task is preempted
//! by the timer *while it holds that lock* (entirely possible -- ordinary
//! allocation doesn't disable interrupts anywhere in this codebase), and
//! the task switched to also tries to allocate, the second task spins
//! forever on a lock the first task can never come back to release, since
//! it isn't running. If that second allocation happens inside a scheduler
//! critical section that has *already* disabled interrupts (`task::with_scheduler`),
//! the deadlock is permanent: no timer tick can ever fire to preempt the
//! spinning task and give the lock's true owner a chance to resume.
//!
//! The fix is the standard one for exactly this class of problem (Linux
//! calls it `spin_lock_irqsave`): every acquisition of the heap's
//! underlying lock -- allocation, deallocation, `init`, `used`, `free` --
//! disables interrupts for its *entire* duration. Since this kernel is
//! single-core, "interrupts disabled" is equivalent to "cannot be
//! preempted", so a task can now never be switched away from while
//! holding this lock, full stop. That makes it safe for scheduler code to
//! allocate while `SCHEDULER` is locked (see `task::with_scheduler`): no
//! other task can ever be caught mid-allocation to deadlock against.

use core::alloc::{GlobalAlloc, Layout};
use core::sync::atomic::{AtomicBool, Ordering};

use linked_list_allocator::LockedHeap;

/// Wraps `LockedHeap` so every lock acquisition happens with interrupts
/// disabled -- see the module docs for why this is load-bearing, not
/// just a style preference.
struct InterruptSafeHeap {
    inner: LockedHeap,
}

impl InterruptSafeHeap {
    const fn new() -> Self {
        Self {
            inner: LockedHeap::empty(),
        }
    }
}

// Safety: delegates entirely to `LockedHeap`'s own `GlobalAlloc` impl,
// which is sound; the only change is disabling interrupts around each
// call, which affects timing/reentrancy, not memory safety.
unsafe impl GlobalAlloc for InterruptSafeHeap {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        x86_64::instructions::interrupts::without_interrupts(|| unsafe { self.inner.alloc(layout) })
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        x86_64::instructions::interrupts::without_interrupts(|| unsafe {
            self.inner.dealloc(ptr, layout)
        });
    }
}

/// Global heap instance used by `Box`, `Vec`, `String`, and friends.
#[global_allocator]
static HEAP: InterruptSafeHeap = InterruptSafeHeap::new();

static INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Initialize the heap over `[start, start + size)`.
///
/// Must be called once before any heap allocation.
pub fn init(start: usize, size: usize) {
    x86_64::instructions::interrupts::without_interrupts(|| unsafe {
        HEAP.inner.lock().init(start as *mut u8, size);
    });
    INITIALIZED.store(true, Ordering::SeqCst);
}

/// Report whether the heap has been initialized.
pub fn is_initialized() -> bool {
    INITIALIZED.load(Ordering::SeqCst)
}

/// Bytes currently allocated out of the heap.
pub fn used() -> usize {
    x86_64::instructions::interrupts::without_interrupts(|| HEAP.inner.lock().used())
}

/// Bytes still available in the heap.
pub fn free() -> usize {
    x86_64::instructions::interrupts::without_interrupts(|| HEAP.inner.lock().free())
}
