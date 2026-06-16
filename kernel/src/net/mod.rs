//! Networking foundation (Phase 11).
//!
//! Provides driver abstraction, loopback mode, ping, and an HTTP client stub
//! for future AI Bridge integration.

pub mod driver;
pub mod http;
pub mod loopback;

use alloc::string::String;

use driver::NetDriver;
use loopback::LoopbackDriver;

static mut LOOPBACK: LoopbackDriver = LoopbackDriver::new();
static mut INITIALIZED: bool = false;

/// Bring up the loopback driver.
pub fn init() {
    unsafe {
        LOOPBACK.init();
        INITIALIZED = true;
    }
}

fn loopback_mut() -> Result<&'static mut LoopbackDriver, &'static str> {
    unsafe {
        if !INITIALIZED {
            return Err("network not initialized");
        }
        Ok(&mut *core::ptr::addr_of_mut!(LOOPBACK))
    }
}

/// High-level status for `net status`.
pub fn status_lines() -> [&'static str; 2] {
    ["Network: initialized", "Loopback: active"]
}

/// Send a test packet to localhost and report the result.
pub fn ping(host: &str) -> Result<String, &'static str> {
    let host = host.trim();
    if host != "localhost" && host != "127.0.0.1" {
        return Err("only localhost is supported");
    }

    let driver = loopback_mut()?;
    let payload = b"tuwaiqos-ping";
    match driver.send(payload) {
        driver::SendResult::Delivered => {}
        driver::SendResult::Dropped => return Err("loopback dropped packet"),
    }

    let mut buffer = [0u8; 64];
    let received = driver.receive(&mut buffer).ok_or("no loopback reply")?;
    if received != payload.len() {
        return Err("unexpected reply size");
    }

    Ok(String::from("Reply from localhost: ok"))
}

/// Access the HTTP client stub.
pub fn http_client() -> http::HttpClient {
    http::HttpClient::new()
}

pub fn is_initialized() -> bool {
    unsafe { INITIALIZED }
}
