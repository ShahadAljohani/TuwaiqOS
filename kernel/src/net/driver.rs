//! Network driver trait.
//!
//! Hardware drivers (loopback today, real NICs later) implement this interface
//! so the rest of the kernel can send and receive packets without knowing the
//! underlying device.

/// Result of sending a packet through a driver.
pub enum SendResult {
    Delivered,
    Dropped,
}

/// Abstract network device.
pub trait NetDriver {
    fn name(&self) -> &'static str;
    fn is_up(&self) -> bool;
    fn send(&mut self, payload: &[u8]) -> SendResult;
    fn receive(&mut self, buffer: &mut [u8]) -> Option<usize>;
}
