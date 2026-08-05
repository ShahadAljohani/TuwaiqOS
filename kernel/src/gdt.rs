//! Global Descriptor Table and Task State Segment.
//!
//! x86_64 mostly ignores segmentation, but a GDT is still required to load
//! `CS` at the correct privilege level, and the TSS's Interrupt Stack Table
//! (IST) is how the double-fault handler is guaranteed a known-good stack
//! even when the fault was *caused by* kernel stack overflow -- running the
//! handler on the already-overflowed stack would just triple-fault.

use lazy_static::lazy_static;
use x86_64::structures::gdt::{Descriptor, GlobalDescriptorTable, SegmentSelector};
use x86_64::structures::tss::TaskStateSegment;
use x86_64::VirtAddr;

pub const DOUBLE_FAULT_IST_INDEX: u16 = 0;
/// Dedicated stack for the timer and keyboard IRQs. These are the only two
/// hardware interrupts enabled in Phase 1 and are never nested inside each
/// other (the CPU masks IF for the duration of an ISR), so sharing one IST
/// slot between them is safe. Diagnosed during Phase 1 bring-up: routing
/// them through whatever stack happened to be current at the interrupt
/// site (e.g. deep inside `ata::wait_not_busy`'s polling loop) produced a
/// double fault on the first hardware-triggered tick; a dedicated,
/// always-valid stack removes that dependency entirely.
pub const IRQ_IST_INDEX: u16 = 1;

const STACK_SIZE: usize = 4096 * 5;

fn new_stack() -> VirtAddr {
    // Safety: each call site below defines its own `STACK` at a distinct
    // location; the returned address is only ever installed into the TSS
    // once, before interrupts are enabled, and never read or written
    // through any other path.
    macro_rules! stack_top {
        () => {{
            static mut STACK: [u8; STACK_SIZE] = [0; STACK_SIZE];
            let start = VirtAddr::from_ptr(core::ptr::addr_of!(STACK));
            start + STACK_SIZE as u64
        }};
    }
    stack_top!()
}

lazy_static! {
    static ref TSS: TaskStateSegment = {
        let mut tss = TaskStateSegment::new();
        tss.interrupt_stack_table[DOUBLE_FAULT_IST_INDEX as usize] = new_stack();
        tss.interrupt_stack_table[IRQ_IST_INDEX as usize] = new_stack();
        tss
    };
}

struct Selectors {
    code_selector: SegmentSelector,
    tss_selector: SegmentSelector,
}

lazy_static! {
    static ref GDT: (GlobalDescriptorTable, Selectors) = {
        let mut gdt = GlobalDescriptorTable::new();
        let code_selector = gdt.add_entry(Descriptor::kernel_code_segment());
        let tss_selector = gdt.add_entry(Descriptor::tss_segment(&TSS));
        (
            gdt,
            Selectors {
                code_selector,
                tss_selector,
            },
        )
    };
}

/// Load the kernel GDT and TSS. Must run before `interrupts::init` loads
/// the IDT, since the double-fault entry references `DOUBLE_FAULT_IST_INDEX`.
pub fn init() {
    use x86_64::instructions::segmentation::{Segment, CS, DS, ES, FS, GS, SS};
    use x86_64::instructions::tables::load_tss;
    use x86_64::structures::gdt::SegmentSelector;

    GDT.0.load();
    // Safety: code_selector/tss_selector come from entries this same
    // function just appended to GDT, so both indices are valid and the
    // GDT is already loaded above.
    //
    // The bootloader hands off with its own GDT/TSS already active and its
    // own (non-zero) selector values sitting in SS/DS/ES/FS/GS. Loading a
    // new GDT reloads the *table* those selectors index into, but not the
    // registers themselves -- so a stale selector value that was valid
    // under the bootloader's GDT can silently point at a *different*
    // (possibly invalid, e.g. our TSS descriptor) entry in the new one.
    // CS is fixed up below via the far-return `set_reg` needs; the other
    // segment registers are barely used in 64-bit long mode, so they are
    // reloaded to the null selector rather than left stale. Skipping this
    // was the root cause of a GPF (error_code pointing at the TSS
    // selector) on every single interrupt return during Phase 1 bring-up:
    // IRETQ validates the SS value on the stack against the *current*
    // GDT, and the bootloader's stale SS selector aliased our TSS entry.
    unsafe {
        CS::set_reg(GDT.1.code_selector);
        SS::set_reg(SegmentSelector::NULL);
        DS::set_reg(SegmentSelector::NULL);
        ES::set_reg(SegmentSelector::NULL);
        FS::set_reg(SegmentSelector::NULL);
        GS::set_reg(SegmentSelector::NULL);
        load_tss(GDT.1.tss_selector);
    }
}
