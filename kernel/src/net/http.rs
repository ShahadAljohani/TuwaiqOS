//! HTTP client abstraction (Phase 11 stub).
//!
//! Provides the API surface future AI Bridge networking will use. No DNS, TLS,
//! or real sockets yet — calls return a descriptive offline message.

use alloc::string::String;

/// Minimal HTTP response container.
pub struct HttpResponse {
    pub status: u16,
    pub body: String,
}

/// Stub HTTP client for future outbound requests.
pub struct HttpClient;

impl HttpClient {
    pub const fn new() -> Self {
        Self
    }

    /// Perform a GET request (stub — no real network I/O yet).
    pub fn get(&self, url: &str) -> HttpResponse {
        HttpResponse {
            status: 503,
            body: format_stub_message(url),
        }
    }
}

fn format_stub_message(url: &str) -> String {
    let mut message = String::from("HTTP client stub: network stack not connected to ");
    message.push_str(url);
    message
}
