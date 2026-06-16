//! Cooperative task scheduler (Phase 10).
//!
//! TuwaiqOS runs a minimal task table. The shell is the only actively
//! running task today; `idle` represents the CPU when nothing else is ready.
//! This is cooperative scheduling — tasks yield by returning to the shell loop.

use alloc::string::String;
use alloc::vec::Vec;

/// Lifecycle state of a kernel task.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum TaskState {
    Running,
    Ready,
    Sleeping,
}

impl TaskState {
    fn label(self) -> &'static str {
        match self {
            TaskState::Running => "Running",
            TaskState::Ready => "Ready",
            TaskState::Sleeping => "Sleeping",
        }
    }
}

/// One entry in the global task table.
#[derive(Clone)]
pub struct Task {
    pub id: u32,
    pub name: String,
    pub state: TaskState,
}

static mut TASKS: Option<Vec<Task>> = None;

/// Create built-in tasks before the shell starts.
pub fn init() {
    let mut tasks = Vec::new();
    tasks.push(Task {
        id: 1,
        name: String::from("shell"),
        state: TaskState::Running,
    });
    tasks.push(Task {
        id: 2,
        name: String::from("idle"),
        state: TaskState::Ready,
    });

    unsafe {
        TASKS = Some(tasks);
    }
}

fn with_tasks<F, R>(f: F) -> Result<R, &'static str>
where
    F: FnOnce(&mut Vec<Task>) -> Result<R, &'static str>,
{
    unsafe {
        let slot = core::ptr::addr_of_mut!(TASKS);
        match (*slot).as_mut() {
            Some(tasks) => f(tasks),
            None => Err("task table not initialized"),
        }
    }
}

/// List all tasks for the `ps` command.
pub fn list() -> Result<Vec<Task>, &'static str> {
    with_tasks(|tasks| Ok(tasks.clone()))
}

/// Detailed information about one task.
pub fn info(id: u32) -> Result<Task, &'static str> {
    with_tasks(|tasks| {
        tasks
            .iter()
            .find(|task| task.id == id)
            .cloned()
            .ok_or("task not found")
    })
}

/// Mark a task as terminated (cooperative kill).
pub fn kill(id: u32) -> Result<(), &'static str> {
    if id == 1 {
        return Err("cannot kill shell task");
    }

    with_tasks(|tasks| {
        if let Some(task) = tasks.iter_mut().find(|task| task.id == id) {
            task.state = TaskState::Sleeping;
            Ok(())
        } else {
            Err("task not found")
        }
    })
}

/// Yield one timeslice — placeholder for future preemption.
pub fn schedule_tick() {
    let _ = with_tasks(|tasks| {
        for task in tasks.iter_mut() {
            if task.id == 2 && task.state == TaskState::Ready {
                task.state = TaskState::Sleeping;
            }
        }
        Ok(())
    });
}

pub fn state_label(state: TaskState) -> &'static str {
    state.label()
}
