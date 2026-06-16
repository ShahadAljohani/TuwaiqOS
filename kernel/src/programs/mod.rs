//! Built-in user programs shipped with TuwaiqOS.

pub mod demo;
pub mod hello;

use alloc::string::String;
use alloc::vec::Vec;

/// Dispatch `run <name>` to the correct built-in program.
pub fn dispatch(name: &str, args: &str) -> Result<Vec<String>, &'static str> {
    match name {
        "hello" => hello::run(args),
        "demo" => demo::run(args),
        _ => Err("program not found"),
    }
}

pub fn names() -> &'static [&'static str] {
    &["hello", "demo"]
}
