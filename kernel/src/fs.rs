//! TuwaiqOS filesystem layer.
//!
//! Shell-facing API backed by TuwaiqFS v2 persistent storage.

use alloc::string::String;
use alloc::vec::Vec;

use crate::tuwaiqfs::{self, FsNode};

/// A named entry inside a directory.
enum Entry {
    File { content: String },
    Dir { children: Vec<(String, Entry)> },
}

struct FileSystem {
    root: Entry,
    cwd: Vec<String>,
}

static mut FS: Option<FileSystem> = None;

pub fn init() {
    let mounted = tuwaiqfs::mount().unwrap_or_else(|reason| {
        crate::serial_println!(
            "fs: mount failed ({}), falling back to an empty filesystem",
            reason
        );
        tuwaiqfs::FsNode::Dir {
            children: Vec::new(),
        }
    });

    let root = match mounted {
        FsNode::Dir { children } => {
            let mut entries = Vec::new();
            for (name, node) in children {
                entries.push((name, from_fs_node(node)));
            }
            Entry::Dir { children: entries }
        }
        _ => Entry::Dir {
            children: Vec::new(),
        },
    };

    unsafe {
        FS = Some(FileSystem {
            root,
            cwd: Vec::new(),
        });
    }
}

fn from_fs_node(node: FsNode) -> Entry {
    match node {
        FsNode::File { content } => Entry::File { content },
        FsNode::Dir { children } => {
            let mut entries = Vec::new();
            for (name, child) in children {
                entries.push((name, from_fs_node(child)));
            }
            Entry::Dir { children: entries }
        }
    }
}

fn to_fs_node(entry: &Entry) -> FsNode {
    match entry {
        Entry::File { content } => FsNode::File {
            content: content.clone(),
        },
        Entry::Dir { children } => {
            let mut nodes = Vec::new();
            for (name, child) in children {
                nodes.push((name.clone(), to_fs_node(child)));
            }
            FsNode::Dir { children: nodes }
        }
    }
}

fn with_fs<F, R>(f: F) -> Result<R, &'static str>
where
    F: FnOnce(&mut FileSystem) -> Result<R, &'static str>,
{
    unsafe {
        let slot = core::ptr::addr_of_mut!(FS);
        match (*slot).as_mut() {
            Some(fs) => f(fs),
            None => Err("filesystem not initialized"),
        }
    }
}

impl FileSystem {
    fn pwd(&self) -> String {
        if self.cwd.is_empty() {
            String::from("/")
        } else {
            let mut path = String::from("/");
            path.push_str(&self.cwd.join("/"));
            path
        }
    }

    fn list_dir(&self) -> Result<Vec<String>, &'static str> {
        let children = self.current_children()?;
        let mut names = Vec::new();
        for (name, entry) in children {
            if matches!(entry, Entry::Dir { .. }) {
                let mut line = name.clone();
                line.push('/');
                names.push(line);
            } else {
                names.push(name.clone());
            }
        }
        Ok(names)
    }

    fn list_at_path(&self, path: &str) -> Result<Vec<String>, &'static str> {
        let parts = split_path(path);
        let children = self.children_at(&parts)?;
        let mut names = Vec::new();
        for (name, entry) in children {
            if matches!(entry, Entry::Dir { .. }) {
                let mut line = name.clone();
                line.push('/');
                names.push(line);
            } else {
                names.push(name.clone());
            }
        }
        Ok(names)
    }

    fn touch(&mut self, name: &str) -> Result<(), &'static str> {
        validate_name(name)?;
        let children = self.current_children_mut()?;
        if children.iter().any(|(n, _)| n == name) {
            return Err("file or directory already exists");
        }
        children.push((
            String::from(name),
            Entry::File {
                content: String::new(),
            },
        ));
        self.persist()
    }

    fn mkdir(&mut self, name: &str) -> Result<(), &'static str> {
        validate_name(name)?;
        let children = self.current_children_mut()?;
        if children.iter().any(|(n, _)| n == name) {
            return Err("file or directory already exists");
        }
        children.push((
            String::from(name),
            Entry::Dir {
                children: Vec::new(),
            },
        ));
        self.persist()
    }

    fn read_file(&self, name: &str) -> Result<String, &'static str> {
        validate_name(name)?;
        let children = self.current_children()?;
        for (entry_name, entry) in children {
            if entry_name == name {
                return match entry {
                    Entry::File { content } => Ok(content.clone()),
                    Entry::Dir { .. } => Err("is a directory"),
                };
            }
        }
        Err("file not found")
    }

    fn read_at_path(&self, path: &str) -> Result<String, &'static str> {
        let parts = split_path(path);
        if parts.is_empty() {
            return Err("path required");
        }
        let file_name = parts.last().ok_or("path required")?;
        validate_name(file_name)?;
        let parent = &parts[..parts.len() - 1];
        let children = self.children_at(parent)?;
        for (entry_name, entry) in children {
            if entry_name == file_name {
                return match entry {
                    Entry::File { content } => Ok(content.clone()),
                    Entry::Dir { .. } => Err("is a directory"),
                };
            }
        }
        Err("file not found")
    }

    fn write_file(&mut self, name: &str, text: &str) -> Result<(), &'static str> {
        validate_name(name)?;
        let children = self.current_children_mut()?;
        if let Some((_, entry)) = children.iter_mut().find(|(n, _)| n == name) {
            return match entry {
                Entry::File { content } => {
                    *content = String::from(text);
                    self.persist()
                }
                Entry::Dir { .. } => Err("is a directory"),
            };
        }
        children.push((
            String::from(name),
            Entry::File {
                content: String::from(text),
            },
        ));
        self.persist()
    }

    fn write_at_path(&mut self, path: &str, text: &str) -> Result<(), &'static str> {
        let parts = split_path(path);
        if parts.is_empty() {
            return Err("path required");
        }
        let file_name = parts.last().ok_or("path required")?.clone();
        validate_name(&file_name)?;
        let parent = parts[..parts.len() - 1].to_vec();

        if parent.is_empty() {
            return self.write_file(&file_name, text);
        }

        ensure_dir_chain(&mut self.root, &parent)?;
        let children = self.children_at_mut(&parent)?;
        if let Some((_, entry)) = children.iter_mut().find(|(n, _)| n == &file_name) {
            return match entry {
                Entry::File { content } => {
                    *content = String::from(text);
                    self.persist()
                }
                Entry::Dir { .. } => Err("is a directory"),
            };
        }
        children.push((
            file_name,
            Entry::File {
                content: String::from(text),
            },
        ));
        self.persist()
    }

    fn persist(&self) -> Result<(), &'static str> {
        tuwaiqfs::sync_tree(&to_fs_node(&self.root))
    }

    fn current_children(&self) -> Result<&Vec<(String, Entry)>, &'static str> {
        self.children_at(&self.cwd)
    }

    fn current_children_mut(&mut self) -> Result<&mut Vec<(String, Entry)>, &'static str> {
        let path = self.cwd.clone();
        self.children_at_mut(&path)
    }

    fn children_at(&self, path: &[String]) -> Result<&Vec<(String, Entry)>, &'static str> {
        let mut node = &self.root;
        for part in path {
            node = find_child(node, part)?;
        }
        match node {
            Entry::Dir { children } => Ok(children),
            Entry::File { .. } => Err("not a directory"),
        }
    }

    fn children_at_mut(
        &mut self,
        path: &[String],
    ) -> Result<&mut Vec<(String, Entry)>, &'static str> {
        let mut node = &mut self.root;
        for part in path {
            node = find_child_mut(node, part)?;
        }
        match node {
            Entry::Dir { children } => Ok(children),
            Entry::File { .. } => Err("not a directory"),
        }
    }

    fn all_entry_names(&self) -> Vec<String> {
        let mut names = Vec::new();
        collect_names(&self.root, &mut names);
        names
    }
}

fn collect_names(entry: &Entry, out: &mut Vec<String>) {
    match entry {
        Entry::File { .. } => {}
        Entry::Dir { children } => {
            for (name, child) in children {
                out.push(name.clone());
                collect_names(child, out);
            }
        }
    }
}

fn ensure_dir_chain(root: &mut Entry, path: &[String]) -> Result<(), &'static str> {
    let mut node = root;
    for part in path {
        match node {
            Entry::Dir { children } => {
                if !children.iter().any(|(n, _)| n == part) {
                    children.push((
                        part.clone(),
                        Entry::Dir {
                            children: Vec::new(),
                        },
                    ));
                }
                let index = children.iter().position(|(n, _)| n == part).unwrap();
                node = &mut children[index].1;
            }
            Entry::File { .. } => return Err("path conflict"),
        }
    }
    Ok(())
}

fn split_path(path: &str) -> Vec<String> {
    path.trim()
        .trim_start_matches('/')
        .split('/')
        .filter(|p| !p.is_empty())
        .map(String::from)
        .collect()
}

fn find_child<'a>(node: &'a Entry, name: &str) -> Result<&'a Entry, &'static str> {
    match node {
        Entry::Dir { children } => children
            .iter()
            .find(|(n, _)| n == name)
            .map(|(_, e)| e)
            .ok_or("directory not found"),
        Entry::File { .. } => Err("not a directory"),
    }
}

fn find_child_mut<'a>(node: &'a mut Entry, name: &str) -> Result<&'a mut Entry, &'static str> {
    match node {
        Entry::Dir { children } => children
            .iter_mut()
            .find(|(n, _)| n == name)
            .map(|(_, e)| e)
            .ok_or("directory not found"),
        Entry::File { .. } => Err("not a directory"),
    }
}

fn validate_name(name: &str) -> Result<(), &'static str> {
    if name.is_empty() {
        return Err("name required");
    }
    if name.contains('/') || name.contains('\\') {
        return Err("invalid name");
    }
    Ok(())
}

pub fn sync_to_disk() -> Result<(), &'static str> {
    with_fs(|fs| fs.persist())
}

pub fn pwd() -> Result<String, &'static str> {
    with_fs(|fs| Ok(fs.pwd()))
}

pub fn ls() -> Result<Vec<String>, &'static str> {
    with_fs(|fs| fs.list_dir())
}

pub fn ls_path(path: &str) -> Result<Vec<String>, &'static str> {
    with_fs(|fs| fs.list_at_path(path))
}

pub fn touch(name: &str) -> Result<(), &'static str> {
    with_fs(|fs| fs.touch(name.trim()))
}

pub fn mkdir(name: &str) -> Result<(), &'static str> {
    with_fs(|fs| fs.mkdir(name.trim()))
}

pub fn cat(name: &str) -> Result<String, &'static str> {
    with_fs(|fs| fs.read_file(name.trim()))
}

pub fn cat_path(path: &str) -> Result<String, &'static str> {
    with_fs(|fs| fs.read_at_path(path))
}

pub fn write(name: &str, text: &str) -> Result<(), &'static str> {
    with_fs(|fs| fs.write_file(name.trim(), text))
}

pub fn write_in_path(path: &str, text: &str) -> Result<(), &'static str> {
    with_fs(|fs| fs.write_at_path(path, text))
}

pub fn completion_candidates(prefix: &str) -> Result<Vec<String>, &'static str> {
    with_fs(|fs| {
        let mut matches = Vec::new();
        for name in fs.all_entry_names() {
            if name.starts_with(prefix) {
                matches.push(name);
            }
        }
        Ok(matches)
    })
}

pub fn label() -> &'static str {
    "TuwaiqFS v2"
}
