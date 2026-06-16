//! Program loader — built-in application registry.
//!
//! Separates user-facing programs from the shell. A future ELF loader can
//! replace the registry without changing shell command parsing.

use alloc::string::String;
use alloc::vec::Vec;

use crate::programs;

/// Run a built-in program by name and return output lines.
pub fn run(name: &str, args: &str) -> Result<Vec<String>, &'static str> {
    programs::dispatch(name.trim(), args.trim())
}

/// Names available for tab completion.
pub fn program_names() -> &'static [&'static str] {
    programs::names()
}
