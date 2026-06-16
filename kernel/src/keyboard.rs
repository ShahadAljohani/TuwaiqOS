//! PS/2 keyboard input (polling mode).
//!
//! Supports printable keys, Shift modifiers, arrow keys, and Tab.

/// A decoded keyboard event for the shell.
pub enum KeyEvent {
    Char(u8),
    Enter,
    Backspace,
    ArrowUp,
    ArrowDown,
    Tab,
    None,
}

static mut LEFT_SHIFT: bool = false;
static mut RIGHT_SHIFT: bool = false;

fn shift_active() -> bool {
    unsafe { LEFT_SHIFT || RIGHT_SHIFT }
}

/// Poll the keyboard once. Returns immediately if no key is waiting.
pub fn poll_key() -> KeyEvent {
    unsafe {
        if inb(STATUS_PORT) & 0x01 == 0 {
            return KeyEvent::None;
        }

        let scancode = inb(DATA_PORT);

        // Extended scancodes (arrow keys) are prefixed with 0xE0.
        if scancode == 0xE0 {
            if inb(STATUS_PORT) & 0x01 == 0 {
                return KeyEvent::None;
            }
            let extended = inb(DATA_PORT);
            return translate_extended(extended);
        }

        translate_scancode(scancode)
    }
}

const DATA_PORT: u16 = 0x60;
const STATUS_PORT: u16 = 0x64;

fn translate_extended(scancode: u8) -> KeyEvent {
    if scancode & 0x80 != 0 {
        return KeyEvent::None;
    }
    match scancode {
        0x48 => KeyEvent::ArrowUp,
        0x50 => KeyEvent::ArrowDown,
        _ => KeyEvent::None,
    }
}

fn translate_scancode(scancode: u8) -> KeyEvent {
    if scancode & 0x80 != 0 {
        match scancode {
            0xAA => unsafe { LEFT_SHIFT = false },
            0xB6 => unsafe { RIGHT_SHIFT = false },
            _ => {}
        }
        return KeyEvent::None;
    }

    match scancode {
        0x2A => {
            unsafe { LEFT_SHIFT = true };
            KeyEvent::None
        }
        0x36 => {
            unsafe { RIGHT_SHIFT = true };
            KeyEvent::None
        }
        0x1C => KeyEvent::Enter,
        0x0E => KeyEvent::Backspace,
        0x0F => KeyEvent::Tab,
        0x39 => KeyEvent::Char(b' '),
        0x02 => emit_pair(b'1', b'!'),
        0x03 => emit_pair(b'2', b'@'),
        0x04 => emit_pair(b'3', b'#'),
        0x05 => emit_pair(b'4', b'$'),
        0x06 => emit_pair(b'5', b'%'),
        0x07 => emit_pair(b'6', b'^'),
        0x08 => emit_pair(b'7', b'&'),
        0x09 => emit_pair(b'8', b'*'),
        0x0A => emit_pair(b'9', b'('),
        0x0B => emit_pair(b'0', b')'),
        0x0C => emit_pair(b'-', b'_'),
        0x0D => emit_pair(b'=', b'+'),
        0x29 => emit_pair(b'`', b'~'),
        0x1A => emit_pair(b'[', b'{'),
        0x1B => emit_pair(b']', b'}'),
        0x2B => emit_pair(b'\\', b'|'),
        0x27 => emit_pair(b';', b':'),
        0x28 => emit_pair(b'\'', b'"'),
        0x33 => emit_pair(b',', b'<'),
        0x34 => emit_pair(b'.', b'>'),
        0x35 => emit_pair(b'/', b'?'),
        0x10 => emit_letter(b'q'),
        0x11 => emit_letter(b'w'),
        0x12 => emit_letter(b'e'),
        0x13 => emit_letter(b'r'),
        0x14 => emit_letter(b't'),
        0x15 => emit_letter(b'y'),
        0x16 => emit_letter(b'u'),
        0x17 => emit_letter(b'i'),
        0x18 => emit_letter(b'o'),
        0x19 => emit_letter(b'p'),
        0x1E => emit_letter(b'a'),
        0x1F => emit_letter(b's'),
        0x20 => emit_letter(b'd'),
        0x21 => emit_letter(b'f'),
        0x22 => emit_letter(b'g'),
        0x23 => emit_letter(b'h'),
        0x24 => emit_letter(b'j'),
        0x25 => emit_letter(b'k'),
        0x26 => emit_letter(b'l'),
        0x2C => emit_letter(b'z'),
        0x2D => emit_letter(b'x'),
        0x2E => emit_letter(b'c'),
        0x2F => emit_letter(b'v'),
        0x30 => emit_letter(b'b'),
        0x31 => emit_letter(b'n'),
        0x32 => emit_letter(b'm'),
        _ => KeyEvent::None,
    }
}

fn emit_pair(normal: u8, shifted: u8) -> KeyEvent {
    if shift_active() {
        KeyEvent::Char(shifted)
    } else {
        KeyEvent::Char(normal)
    }
}

fn emit_letter(lower: u8) -> KeyEvent {
    if shift_active() {
        KeyEvent::Char(lower - b'a' + b'A')
    } else {
        KeyEvent::Char(lower)
    }
}

#[inline(always)]
unsafe fn inb(port: u16) -> u8 {
    let value: u8;
    core::arch::asm!(
        "in al, dx",
        out("al") value,
        in("dx") port,
        options(nomem, nostack, preserves_flags)
    );
    value
}
