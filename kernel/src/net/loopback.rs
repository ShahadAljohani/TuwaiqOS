//! Loopback network driver.
//!
//! Packets sent to `127.0.0.1` never leave the machine. They are copied into
//! an internal buffer and read back by `ping localhost`, which is enough to
//! test the networking stack before a real NIC driver exists.

use super::driver::{NetDriver, SendResult};

const BUFFER_SIZE: usize = 512;

pub struct LoopbackDriver {
    buffer: [u8; BUFFER_SIZE],
    length: usize,
    up: bool,
}

impl LoopbackDriver {
    pub const fn new() -> Self {
        Self {
            buffer: [0; BUFFER_SIZE],
            length: 0,
            up: false,
        }
    }

    pub fn init(&mut self) {
        self.up = true;
        self.length = 0;
    }
}

impl NetDriver for LoopbackDriver {
    fn name(&self) -> &'static str {
        "loopback"
    }

    fn is_up(&self) -> bool {
        self.up
    }

    fn send(&mut self, payload: &[u8]) -> SendResult {
        if !self.up {
            return SendResult::Dropped;
        }
        let len = payload.len().min(BUFFER_SIZE);
        self.buffer[..len].copy_from_slice(&payload[..len]);
        self.length = len;
        SendResult::Delivered
    }

    fn receive(&mut self, buffer: &mut [u8]) -> Option<usize> {
        if self.length == 0 {
            return None;
        }
        let len = self.length.min(buffer.len());
        buffer[..len].copy_from_slice(&self.buffer[..len]);
        Some(len)
    }
}
