//! Serial (COM1 / UART 16550) debug output.
//!
//! Independent of the VGA/framebuffer console: this channel works with
//! `-display none` and exists specifically so boot progress and fault
//! diagnostics are observable headlessly (automated QEMU smoke tests,
//! panic messages) without needing a graphical window.

use lazy_static::lazy_static;
use spin::Mutex;
use uart_16550::SerialPort;

lazy_static! {
    static ref SERIAL1: Mutex<SerialPort> = {
        // Safety: 0x3F8 is the standard fixed COM1 I/O base on the PC
        // platform QEMU emulates; constructing more than one SerialPort
        // over the same port would race the hardware, so access is only
        // ever made through this single locked instance.
        let mut port = unsafe { SerialPort::new(0x3F8) };
        port.init();
        Mutex::new(port)
    };
}

#[doc(hidden)]
pub fn _print(args: core::fmt::Arguments) {
    use core::fmt::Write;
    // An interrupt handler that logged to serial while the interrupted
    // code already held this lock would deadlock the spinlock forever,
    // so interrupts stay masked for the duration of the write.
    x86_64::instructions::interrupts::without_interrupts(|| {
        SERIAL1
            .lock()
            .write_fmt(args)
            .expect("serial port write failed");
    });
}

#[macro_export]
macro_rules! serial_print {
    ($($arg:tt)*) => {
        $crate::serial::_print(format_args!($($arg)*))
    };
}

#[macro_export]
macro_rules! serial_println {
    () => ($crate::serial_print!("\n"));
    ($fmt:expr) => ($crate::serial_print!(concat!($fmt, "\n")));
    ($fmt:expr, $($arg:tt)*) => ($crate::serial_print!(concat!($fmt, "\n"), $($arg)*));
}
