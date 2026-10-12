"""3.3 A useful first agent: read-only file research with 4 tools, confined to one directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the bounded loop from 3.2

from agent import run_agent

from common.budget import Budget
from common.config import make_client

ROOT = Path(__file__).resolve().parents[1]  # least privilege: the agent can only see this tree
MAX_READ = 8_000  # chars per read; larger files are paged with `offset`, never silently cut
SKIP = {".venv", ".git", "__pycache__", ".env"}


def _safe(path: str) -> Path:
    # The model controls `path`, so treat it as untrusted: resolve() collapses '..' and symlinks first,
    # then we require the result to stay inside ROOT and avoid secrets (.env) and the venv.
    p = (ROOT / path).resolve()
    if not p.is_relative_to(ROOT) or any(part in SKIP for part in p.relative_to(ROOT).parts):
        raise PermissionError(f"'{path}' is outside the allowed directory.")
    return p


def list_files(path: str = ".") -> str:
    p = _safe(path)
    items = sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir() if c.name not in SKIP)
    return "\n".join(items) or "(empty)"


def read_file(path: str, offset: int = 0) -> str:
    text = _safe(path).read_text(errors="replace")
    chunk = text[offset:offset + MAX_READ]
    more = len(text) - (offset + MAX_READ)
    note = f"\n[truncated: {more} more chars; call again with offset={offset + MAX_READ}]" if more > 0 else ""
    return chunk + note


def search_text(query: str) -> str:
    hits = []
    for f in ROOT.rglob("*"):
        if f.is_file() and f.suffix in {".py", ".md"} and not set(f.relative_to(ROOT).parts) & SKIP:
            for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if query.lower() in line.lower():
                    hits.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    return "\n".join(hits[:30]) + ("\n[showing first 30 matches; refine the query]" if len(hits) > 30 else "") or "No matches."


NOTES: list[str] = []  # scratchpad: lives for this run only (persistence is 3.4)


def save_note(note: str) -> str:
    NOTES.append(note)
    return f"Saved note #{len(NOTES)}."


HANDLERS = {"list_files": list_files, "read_file": read_file, "search_text": search_text, "save_note": save_note}


def _tool(name: str, desc: str, props: dict, required: list) -> dict:
    return {"name": name, "description": desc, "strict": True, "input_schema": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}


TOOLS = [
    _tool("list_files", "List a directory inside the project (relative path).",
          {"path": {"type": "string", "description": "e.g. '.' or '02_tools'."}}, ["path"]),
    _tool("read_file", "Read a text file (paged). If the result says truncated, call again with the given offset.",
          {"path": {"type": "string"}, "offset": {"type": "integer", "description": "Start char, 0 for the beginning."}},
          ["path", "offset"]),
    _tool("search_text", "Case-insensitive search in .py/.md files. Returns file:line: text.",
          {"query": {"type": "string"}}, ["query"]),
    _tool("save_note", "Save a short finding to the scratchpad for the final answer.",
          {"note": {"type": "string"}}, ["note"]),
]


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    # Expected failures become is_error results with a next step, so the model can recover.
    try:
        return HANDLERS[name](**tool_input), False
    except KeyError:
        return f"Unknown tool '{name}'. Available: {', '.join(HANDLERS)}.", True
    except (PermissionError, FileNotFoundError, NotADirectoryError, IsADirectoryError) as e:
        return f"{e}. Use list_files to see what exists.", True


SYSTEM = "You are a research assistant for a code repo. Use the tools, cite file paths, and answer concisely."


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "Which scripts in 02_tools are about parallel tool calls, and why?"
    budget = Budget(max_turns=10, max_total_tokens=80_000, max_cost_usd=0.40, timeout_s=120)
    result = run_agent(make_client(), [{"role": "user", "content": question}], TOOLS, execute, budget, SYSTEM)
    print(f"[stop] {result.stop} | turns={budget.turns} cost~${budget.cost_usd:.4f}")
    print(result.text)


if __name__ == "__main__":
    main()
