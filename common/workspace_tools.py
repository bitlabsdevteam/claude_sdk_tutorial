"""A tiny file workspace (list/read/write/delete) confined to one directory, for the Level 6 harness demos."""
from pathlib import Path

from common.demo_tools import ToolError

MAX_READ = 4_000


def make_workspace(root: Path | str):
    """Returns (tool_schemas, handlers). Every path is resolved and must stay inside `root`."""
    root = Path(root).resolve()

    def safe(path: str) -> Path:
        p = (root / path).resolve()  # resolve() collapses '..' and symlinks BEFORE the containment check
        if not p.is_relative_to(root):
            raise ToolError(f"'{path}' is outside the workspace. Use relative paths like 'notes.txt'.")
        return p

    def list_files() -> str:
        return "\n".join(sorted(p.name for p in root.iterdir())) or "(empty)"

    def read_file(path: str) -> str:
        p = safe(path)
        if not p.is_file():
            raise ToolError(f"No file '{path}'. Call list_files to see what exists.")
        text = p.read_text()
        return text[:MAX_READ] + (f"\n[truncated: {len(text) - MAX_READ} more chars]" if len(text) > MAX_READ else "")

    def write_file(path: str, content: str) -> str:
        safe(path).write_text(content)
        return f"Wrote {len(content)} chars to {path}."

    def delete_file(path: str) -> str:
        p = safe(path)
        if not p.is_file():
            raise ToolError(f"No file '{path}'.")
        p.unlink()
        return f"Deleted {path}."

    def tool(name: str, desc: str, props: dict) -> dict:
        return {"name": name, "description": desc, "strict": True, "input_schema": {
            "type": "object", "properties": props, "required": list(props), "additionalProperties": False}}

    path = {"path": {"type": "string", "description": "Relative file name, e.g. 'notes.txt'."}}
    schemas = [
        tool("list_files", "List files in the workspace.", {}),
        tool("read_file", "Read a text file from the workspace.", path),
        tool("write_file", "Create or overwrite a text file.", {**path, "content": {"type": "string"}}),
        tool("delete_file", "Permanently delete a file. Irreversible.", path),
    ]
    handlers = {"list_files": list_files, "read_file": read_file, "write_file": write_file, "delete_file": delete_file}
    return schemas, handlers
