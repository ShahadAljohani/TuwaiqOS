//! TuwaiqOS kernel entry point.

#![no_std]
#![no_main]

extern crate alloc;

mod ai_bridge;
mod apps;
mod allocator;
mod ata;
mod font8x8;
mod framebuffer_console;
mod fs;
mod keyboard;
mod loader;
mod memory;
mod net;
mod programs;
mod reboot;
mod shell;
mod task;
mod tuwaiqfs;
mod vga_buffer;

use bootloader_api::{entry_point, BootInfo};

use shell::ConsoleMode;

entry_point!(kernel_main);

fn kernel_main(boot_info: &'static mut BootInfo) -> ! {
    memory::init_heap(boot_info);
    ata::init();
    fs::init();
    task::init();
    net::init();

    if let Some(framebuffer) = boot_info.framebuffer.as_mut() {
        framebuffer_console::init(framebuffer);
        framebuffer_console::clear_screen();

        if font8x8::DIAGNOSTIC_AT_BOOT {
            for line in font8x8::DIAGNOSTIC_LINES {
                framebuffer_console::println(line);
            }
            framebuffer_console::println("");
        }

        framebuffer_console::println("TuwaiqOS v0.5");
        framebuffer_console::println("AI-Native Experimental Operating System");
        framebuffer_console::println("");

        shell::run(boot_info, ConsoleMode::Framebuffer);
    } else {
        vga_buffer::clear_screen();
        vga_buffer::println("TuwaiqOS v0.5");
        vga_buffer::println("AI-Native Experimental Operating System");
        vga_buffer::println("");

        shell::run(boot_info, ConsoleMode::Vga);
    }
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    framebuffer_console::println("");
    framebuffer_console::println("KERNEL PANIC");
    vga_buffer::println("");
    vga_buffer::println("KERNEL PANIC");
    loop {}
}
