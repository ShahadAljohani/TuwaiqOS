//! Built-in hello program.

use alloc::string::String;
use alloc::vec::Vec;

/// Output lines for the hello program (shell prints them).
pub fn run(_args: &str) -> Result<Vec<String>, &'static str> {
    let mut lines = Vec::new();
    lines.push(String::from("Hello from TuwaiqOS!"));
    lines.push(String::from("Program: hello (built-in)"));
    Ok(lines)
}
