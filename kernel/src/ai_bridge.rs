//! AI Bridge abstraction layer (Phase 8 stub v2).
//!
//! Shell commands call into this module instead of talking to a network API.
//! The stub formats helpful offline responses so the shell can stay unchanged
//! when a real backend is wired in during Phase 9.

use alloc::string::String;

/// Current bridge operating mode.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BridgeMode {
    Stub,
}

/// Lightweight status snapshot for `ai status`.
pub struct BridgeStatus {
    pub online: bool,
    pub mode: BridgeMode,
    pub phase: u8,
}

/// Phase 8 stub — no network, no model, no API keys.
pub struct StubAiBridge;

impl StubAiBridge {
    pub const fn new() -> Self {
        Self
    }

    pub fn status(&self) -> BridgeStatus {
        BridgeStatus {
            online: false,
            mode: BridgeMode::Stub,
            phase: 8,
        }
    }

    /// Multi-line response for `ask <question>`.
    pub fn ask(&self, question: &str) -> String {
        let trimmed = question.trim();
        let display = if trimmed.is_empty() { "(empty)" } else { trimmed };

        let mut response = String::from("AI Bridge: offline\nQuestion: ");
        response.push_str(display);
        response.push_str("\nHint: Real AI backend will be connected in Phase 9.");
        response
    }

    /// Lines printed by `ai help`.
    pub fn help_lines(&self) -> [&'static str; 4] {
        [
            "AI commands:",
            "ask <question>",
            "ai status",
            "ai help",
        ]
    }

    /// Short message for the bare `ai` command.
    pub fn offline_notice(&self) -> &'static str {
        "AI Bridge is not connected yet."
    }
}

/// Shared stub instance for the kernel shell.
static BRIDGE: StubAiBridge = StubAiBridge::new();

pub fn bridge() -> &'static StubAiBridge {
    &BRIDGE
}
