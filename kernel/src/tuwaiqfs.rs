//! TuwaiqFS v2 — persistent filesystem on the boot disk.
//!
//! ## Disk layout (512-byte sectors)
//!
//! ```text
//! LBA 0–8191     Bootloader / kernel area (do not modify)
//! LBA 8192       Superblock
//! LBA 8193–8464  Legacy data slots (reserved)
//! LBA 8465–8712  Metadata blob (tree serialization, 248 sectors)
//! ```
//!
//! v2 stores the **entire directory tree** (nested paths included) in the
//! metadata region so files, directories, and metadata survive reboot.

use alloc::string::String;
use alloc::vec::Vec;

use crate::ata;

pub const SUPERBLOCK_LBA: u32 = 8192;
pub const METADATA_LBA: u32 = 8465;
pub const METADATA_SECTORS: u32 = 248;
pub const MAX_METADATA_BYTES: usize = (METADATA_SECTORS * 512) as usize;
pub const MAX_FILE_SIZE: usize = 2048;
pub const VERSION: u32 = 2;

const MAGIC: [u8; 8] = *b"TQFSv2\0\0";
const TREE_MAGIC: [u8; 4] = *b"TREE";

/// Serialized node loaded from or written to disk.
pub enum FsNode {
    File { content: String },
    Dir { children: Vec<(String, FsNode)> },
}

/// Load TuwaiqFS from disk, formatting if needed.
pub fn mount() -> Result<FsNode, &'static str> {
    let mut superblock = [0u8; 512];
    ata::read_sector(SUPERBLOCK_LBA, &mut superblock)?;

    if superblock[..8] != MAGIC {
        format_region()?;
    }

    load_tree()
}

fn format_region() -> Result<(), &'static str> {
    let mut superblock = [0u8; 512];
    superblock[..8].copy_from_slice(&MAGIC);
    superblock[8..12].copy_from_slice(&VERSION.to_le_bytes());
    superblock[12..16].copy_from_slice(&METADATA_LBA.to_le_bytes());
    superblock[16..20].copy_from_slice(&METADATA_SECTORS.to_le_bytes());
    ata::write_sector(SUPERBLOCK_LBA, &superblock)?;

    let empty = [0u8; 512];
    for sector in METADATA_LBA..METADATA_LBA + METADATA_SECTORS {
        ata::write_sector(sector, &empty)?;
    }
    Ok(())
}

/// Persist the full filesystem tree to disk.
pub fn sync_tree(root: &FsNode) -> Result<(), &'static str> {
    let blob = serialize_tree(root)?;
    if blob.len() > MAX_METADATA_BYTES {
        return Err("filesystem metadata too large");
    }
    write_metadata(&blob)
}

fn load_tree() -> Result<FsNode, &'static str> {
    let blob = read_metadata()?;
    if blob.len() < 8 {
        return Ok(empty_root());
    }
    if &blob[..4] != TREE_MAGIC {
        return Ok(empty_root());
    }
    deserialize_tree(&blob[4..])
}

fn empty_root() -> FsNode {
    FsNode::Dir {
        children: Vec::new(),
    }
}

fn serialize_tree(root: &FsNode) -> Result<Vec<u8>, &'static str> {
    let mut blob = Vec::new();
    blob.extend_from_slice(&TREE_MAGIC);
    flatten_tree("", root, &mut blob)?;
    Ok(blob)
}

fn flatten_tree(path: &str, node: &FsNode, out: &mut Vec<u8>) -> Result<(), &'static str> {
    match node {
        FsNode::File { content } => {
            write_record(out, 1, path, Some(content))?;
        }
        FsNode::Dir { children } => {
            if !path.is_empty() {
                write_record(out, 2, path, None)?;
            }
            for (name, child) in children {
                let child_path = join_path(path, name);
                flatten_tree(&child_path, child, out)?;
            }
        }
    }
    Ok(())
}

fn join_path(base: &str, name: &str) -> String {
    if base.is_empty() {
        String::from(name)
    } else {
        let mut path = String::from(base);
        path.push('/');
        path.push_str(name);
        path
    }
}

fn write_record(
    out: &mut Vec<u8>,
    kind: u8,
    path: &str,
    content: Option<&String>,
) -> Result<(), &'static str> {
    let path_bytes = path.as_bytes();
    if path_bytes.is_empty() || path_bytes.len() > 120 {
        return Err("invalid path");
    }
    out.push(kind);
    out.push(path_bytes.len() as u8);
    out.extend_from_slice(path_bytes);
    if kind == 1 {
        let text = content.ok_or("missing file content")?;
        let bytes = text.as_bytes();
        if bytes.len() > MAX_FILE_SIZE {
            return Err("file too large");
        }
        let len = bytes.len() as u16;
        out.extend_from_slice(&len.to_le_bytes());
        out.extend_from_slice(bytes);
    }
    Ok(())
}

fn deserialize_tree(data: &[u8]) -> Result<FsNode, &'static str> {
    let mut root = empty_root();
    let mut offset = 0;

    while offset < data.len() {
        if offset + 2 > data.len() {
            break;
        }
        let kind = data[offset];
        let path_len = data[offset + 1] as usize;
        offset += 2;

        if offset + path_len > data.len() {
            break;
        }
        let path = core::str::from_utf8(&data[offset..offset + path_len])
            .map_err(|_| "invalid path in metadata")?;
        offset += path_len;

        let node = if kind == 1 {
            if offset + 2 > data.len() {
                return Err("truncated file record");
            }
            let content_len = u16::from_le_bytes([data[offset], data[offset + 1]]) as usize;
            offset += 2;
            if offset + content_len > data.len() {
                return Err("truncated file content");
            }
            let content = core::str::from_utf8(&data[offset..offset + content_len])
                .map_err(|_| "invalid utf-8 in file")?;
            offset += content_len;
            FsNode::File {
                content: String::from(content),
            }
        } else if kind == 2 {
            FsNode::Dir {
                children: Vec::new(),
            }
        } else {
            return Err("unknown record kind");
        };

        insert_at_path(&mut root, path, node)?;
    }

    Ok(root)
}

fn insert_at_path(root: &mut FsNode, path: &str, node: FsNode) -> Result<(), &'static str> {
    let parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        return Ok(());
    }

    let mut current = root;
    for (index, part) in parts.iter().enumerate() {
        let is_last = index + 1 == parts.len();
        match current {
            FsNode::Dir { children } => {
                if is_last {
                    if let Some(pos) = children.iter().position(|(n, _)| n == part) {
                        children[pos].1 = node;
                    } else {
                        children.push((String::from(*part), node));
                    }
                    return Ok(());
                }

                if !children.iter().any(|(n, _)| n == part) {
                    children.push((String::from(*part), FsNode::Dir {
                        children: Vec::new(),
                    }));
                }
                let pos = children.iter().position(|(n, _)| n == part).unwrap();
                current = &mut children[pos].1;
            }
            FsNode::File { .. } => return Err("path conflict"),
        }
    }
    Ok(())
}

fn read_metadata() -> Result<Vec<u8>, &'static str> {
    let mut blob = Vec::new();
    let mut sector_buf = [0u8; 512];

    for sector in METADATA_LBA..METADATA_LBA + METADATA_SECTORS {
        ata::read_sector(sector, &mut sector_buf)?;
        if blob.len() + 512 > MAX_METADATA_BYTES {
            break;
        }
        let end = find_metadata_end(&sector_buf);
        blob.extend_from_slice(&sector_buf[..end]);
        if end < 512 {
            break;
        }
    }

    Ok(blob)
}

fn find_metadata_end(sector: &[u8; 512]) -> usize {
    if sector.iter().all(|&b| b == 0) {
        return 0;
    }
    if let Some(pos) = sector.iter().position(|&b| b == 0) {
        if sector[pos..].iter().all(|&b| b == 0) {
            return pos;
        }
    }
    512
}

fn write_metadata(blob: &[u8]) -> Result<(), &'static str> {
    let mut sector_buf = [0u8; 512];
    let mut offset = 0;

    for sector_index in 0..METADATA_SECTORS {
        sector_buf.fill(0);
        let remaining = blob.len().saturating_sub(offset);
        let copy_len = remaining.min(512);
        if copy_len > 0 {
            sector_buf[..copy_len].copy_from_slice(&blob[offset..offset + copy_len]);
            offset += copy_len;
        }
        ata::write_sector(METADATA_LBA + sector_index, &sector_buf)?;
    }
    Ok(())
}
