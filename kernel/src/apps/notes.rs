//! Notes application — simple persistent notes stored on TuwaiqFS.

use alloc::string::String;
use alloc::vec::Vec;

use crate::fs;

const NOTES_DIR: &str = ".notes";

fn note_path(name: &str) -> String {
    let mut path = String::from(NOTES_DIR);
    path.push('/');
    path.push_str(name);
    path
}

/// Handle `notes` subcommands.
pub fn handle(sub: &str, args: &str) -> Result<Vec<String>, &'static str> {
    let sub = sub.trim();
    match sub {
        "create" => create(args),
        "list" => list(),
        "show" => show(args),
        "" => Ok(usage_lines()),
        _ => Err("unknown notes command"),
    }
}

fn create(name: &str) -> Result<Vec<String>, &'static str> {
    let name = name.trim();
    if name.is_empty() {
        return Err("usage: notes create <name>");
    }
    fs::write_in_path(&note_path(name), "")?;
    let mut lines = Vec::new();
    lines.push(format_message("Created note: ", name));
    Ok(lines)
}

fn list() -> Result<Vec<String>, &'static str> {
    let mut lines = Vec::new();
    match fs::ls_path(NOTES_DIR) {
        Ok(entries) => {
            if entries.is_empty() {
                lines.push(String::from("(no notes)"));
            } else {
                for entry in entries {
                    lines.push(entry);
                }
            }
        }
        Err(_) => lines.push(String::from("(no notes)")),
    }
    Ok(lines)
}

fn show(name: &str) -> Result<Vec<String>, &'static str> {
    let name = name.trim();
    if name.is_empty() {
        return Err("usage: notes show <name>");
    }
    let content = fs::cat_path(&note_path(name))?;
    let mut lines = Vec::new();
    lines.push(format_message("Note: ", name));
    lines.push(content);
    Ok(lines)
}

fn usage_lines() -> Vec<String> {
    let mut lines = Vec::new();
    lines.push(String::from("Notes commands:"));
    lines.push(String::from("  notes create <name>"));
    lines.push(String::from("  notes list"));
    lines.push(String::from("  notes show <name>"));
    lines
}

fn format_message(prefix: &str, name: &str) -> String {
    let mut message = String::from(prefix);
    message.push_str(name);
    message
}
