"""6.15 Long-horizon work across sessions: a progress file, one feature at a time, and a clean-state handoff.

A model's memory ends with its context window, so a big job is split into sessions. Each new session starts
knowing NOTHING except what is on disk. The harness makes that safe:
  - a progress file is the single source of truth (what is done, what is next),
  - the harness (not the model) VERIFIES a feature before marking it done,
  - every session starts by checking the baseline still passes, and ends in a clean, verified state.

Offline demo with a scripted model (free): `python 06_harness/long_horizon.py`; `--live` runs it for real (paid).
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3
sys.path.insert(0, str(Path(__file__).resolve().parent / "sandbox"))  # reuse the 6.8 sandbox

from agent import run_agent
from runner import run_python

from common.budget import Budget
from common.demo_tools import ToolError
from common.harness import Harness, Policy, Rule
from common.scripted import RuleModel, text, tool_use

FEATURES = [
    {"id": "f1", "file": "hello.py", "description": "hello.py defines greet(name) returning 'Hello, <name>!'",
     "check": "assert greet('Ada') == 'Hello, Ada!'"},
    {"id": "f2", "file": "mathx.py", "description": "mathx.py defines add(a, b) returning the sum",
     "check": "assert add(2, 3) == 5"},
]


class Progress:
    """The handoff file. Plain JSON so any session (or a human) can read it."""

    def __init__(self, workdir: Path):
        self.path = workdir / "progress.json"
        if not self.path.exists():
            self.save({"features": [{**f, "status": "todo"} for f in FEATURES], "log": []})

    def load(self) -> dict:
        return json.loads(self.path.read_text())

    def save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def mark_done(self, feature_id: str) -> None:
        data = self.load()
        for f in data["features"]:
            if f["id"] == feature_id:
                f["status"] = "done"
        data["log"].append(f"{feature_id} verified and done")
        self.save(data)


def verify(workdir: Path, feature: dict) -> tuple[bool, str]:
    """Run the feature's check in the sandbox. The file's source and the check are joined into one script,
    so the sandbox (an empty temp directory) never needs access to our files."""
    path = workdir / feature["file"]
    if not path.exists():
        return False, f"{feature['file']} does not exist yet"
    result = run_python(path.read_text() + "\n" + feature["check"], timeout_s=5)
    return result.returncode == 0, (result.stderr or result.stdout).strip()[-400:]


def baseline_report(workdir: Path, progress: Progress) -> str:
    """Start-of-session check: has anything marked done been broken? Fix that BEFORE new work."""
    broken = [f["id"] for f in progress.load()["features"] if f["status"] == "done" and not verify(workdir, f)[0]]
    return f"BASELINE BROKEN for {broken}: fix these first." if broken else "baseline ok: all finished features pass."


def briefing(workdir: Path, progress: Progress) -> str:
    feats = progress.load()["features"]
    lines = [f"- [{f['status']}] {f['id']}: {f['description']}" for f in feats]
    nxt = next((f["id"] for f in feats if f["status"] == "todo"), None)
    return ("You are continuing a multi-session project. Progress file says:\n" + "\n".join(lines) +
            f"\n{baseline_report(workdir, progress)}\nWork on ONE feature only: {nxt or 'none left'}. "
            "Write the file, then call finish_feature. Stop after that one feature.")


def end_of_session_check(workdir: Path, progress: Progress) -> list[str]:
    """Clean state = every feature marked done really passes. Returns problems (empty means clean)."""
    return [f"{f['id']} marked done but fails" for f in progress.load()["features"]
            if f["status"] == "done" and not verify(workdir, f)[0]]


def make_tools(workdir: Path, progress: Progress):
    allowed = {f["file"] for f in FEATURES}

    def write_file(path: str, content: str) -> str:
        if path not in allowed:  # least privilege: only the project's own files
            raise ToolError(f"Can only write: {', '.join(sorted(allowed))}.")
        (workdir / path).write_text(content)
        return f"Wrote {path}."

    def finish_feature(id: str) -> str:
        feature = next((f for f in progress.load()["features"] if f["id"] == id), None)
        if feature is None:
            raise ToolError(f"Unknown feature '{id}'.")
        ok, output = verify(workdir, feature)
        if not ok:  # the MODEL cannot mark itself done: the harness decides
            raise ToolError(f"Verification FAILED for {id}: {output}. Fix the code and call finish_feature again.")
        progress.mark_done(id)
        return f"{id} verified and marked done."

    handlers = {"get_progress": lambda: json.dumps(progress.load()["features"]), "write_file": write_file,
                "finish_feature": finish_feature}
    obj = lambda props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    schemas = [
        {"name": "get_progress", "description": "Show the feature list and status.", "strict": True, "input_schema": obj({})},
        {"name": "write_file", "description": "Write a project file.", "strict": True,
         "input_schema": obj({"path": {"type": "string"}, "content": {"type": "string"}})},
        {"name": "finish_feature", "description": "Ask the harness to verify a feature and mark it done.",
         "strict": True, "input_schema": obj({"id": {"type": "string"}})},
    ]
    return schemas, handlers


# Scripted sessions. Session 1 first writes a BUG, is told verification failed, fixes it, then stops.
SESSION_1 = [
    [tool_use("1", "get_progress")],
    [tool_use("2", "write_file", path="hello.py", content="def greet(name):\n    return 'Hi, ' + name\n")],
    [tool_use("3", "finish_feature", id="f1")],
    [tool_use("4", "write_file", path="hello.py", content="def greet(name):\n    return f'Hello, {name}!'\n")],
    [tool_use("5", "finish_feature", id="f1")],
    [text("f1 is finished and verified. Stopping here as instructed.")],
]
SESSION_2 = [
    [tool_use("1", "write_file", path="mathx.py", content="def add(a, b):\n    return a + b\n")],
    [tool_use("2", "finish_feature", id="f2")],
    [text("f2 is finished and verified.")],
]


def run_session(n: int, workdir: Path, model) -> None:
    progress = Progress(workdir)
    schemas, handlers = make_tools(workdir, progress)
    harness = Harness(handlers, Policy([Rule("*", "allow")]))
    # A FRESH message list: the previous session's conversation is gone. Only the progress file carries over.
    prompt = briefing(workdir, progress)
    print(f"\n--- session {n} starts. Briefing:\n{prompt}")
    result = run_agent(model, [{"role": "user", "content": prompt}], schemas, harness.execute,
                       Budget(max_turns=10, max_total_tokens=60_000, max_cost_usd=0.40, timeout_s=120))
    problems = end_of_session_check(workdir, progress)
    print(f"--- session {n} ended: {result.stop} | clean state: {'YES' if not problems else problems}")
    print(f"    progress log: {progress.load()['log']}")


def main() -> None:
    live = "--live" in sys.argv
    if live:
        from common.config import make_client
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for n, script in [(1, SESSION_1), (2, SESSION_2)]:
            run_session(n, workdir, make_client() if live else RuleModel(script))
        print("\nfinal files:", sorted(p.name for p in workdir.iterdir()))


if __name__ == "__main__":
    main()
