//! Built-in demo program.

use alloc::string::String;
use alloc::vec::Vec;

/// Output lines for the demo program.
pub fn run(_args: &str) -> Result<Vec<String>, &'static str> {
    let mut lines = Vec::new();
    lines.push(String::from("TuwaiqOS demo program"));
    lines.push(String::from("Future ELF binaries will load here."));
    Ok(lines)
}
