"""Tool schemas supplied to Qwen for structured tool calling (Phase 3).

Each entry describes exactly one registered tool:
- name: must match an entry in protocol.KNOWN_TOOLS
- description: natural-language description for the model
- parameters: JSON-Schema object (draft-07 compatible)

The model is expected to emit a JSON object matching:
  {"tool": "<name>", "arguments": { ... }}

No schema here allows a "command" string, shell string, or arbitrary
subprocess invocation.  The only way to interact with the OS is through
the typed argument sets below.
"""

from __future__ import annotations

from typing import Any

# Closed set of tool definitions supplied to the model.  The list is
# intentionally narrow: adding a new tool here is a deliberate act and
# requires a matching entry in protocol.KNOWN_TOOLS and a Rust broker handler.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_system_info",
        "description": (
            "Return basic OS identification: hostname, OS name, OS version, "
            "kernel version, and uptime in seconds."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cpu_info",
        "description": "Return current CPU usage percentage and the number of logical cores.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_memory_info",
        "description": (
            "Return RAM usage: total, used, available bytes, used percentage, "
            "and the top memory-consuming processes."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_disk_info",
        "description": (
            "Return disk usage for each mounted volume: mount point, total, "
            "used and free bytes, and used percentage."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_processes",
        "description": (
            "Return a list of running processes sorted by CPU usage, including "
            "pid, name, cpu_percent, and memory_percent."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_network_status",
        "description": (
            "Return current network status: active interfaces, IP addresses, "
            "bytes sent/received, and connectivity state."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "launch_application",
        "description": (
            "Launch one of the approved desktop applications by its application ID. "
            "Allowed IDs: firefox, vscode, terminal, file_manager."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "Application identifier.",
                    "enum": ["firefox", "vscode", "terminal", "file_manager"],
                }
            },
            "required": ["app_id"],
            "additionalProperties": False,
        },
    },
]

# Quick lookup by name.
TOOL_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {s["name"]: s for s in TOOL_SCHEMAS}
