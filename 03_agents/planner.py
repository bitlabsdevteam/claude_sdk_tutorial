"""3.8 Planning and self-verification: a todo-list tool plus a run-tests-then-fix loop.

The agent fixes a buggy function in a temp directory; the harness (not the model) decides "done" by running the tests.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `common` importable
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reuse the bounded loop from 3.2

from agent import run_agent

from common.budget import Budget
from common.config import make_client

BUGGY = "def average(xs):\n    return sum(xs) / len(xs) + 1\n"
TESTS = (
    "from calc import average\n\n"
    "def test_average():\n    assert average([2, 4, 6]) == 4\n\n"
    "def test_single():\n    assert average([5]) == 5\n"
)


def make_tools(workdir: Path):
    todos: list[dict] = []

    def execute(name: str, inp: dict) -> tuple[str, bool]:
        if name == "update_todos":
            todos[:] = inp["todos"]  # model rewrites the whole plan each time: simple and idempotent
            return "\n".join(f"[{t['status']}] {t['task']}" for t in todos), False
        if name == "read_calc":
            return (workdir / "calc.py").read_text(), False
        if name == "write_calc":
            (workdir / "calc.py").write_text(inp["content"])  # fixed filename: no path from the model
            return "Written.", False
        if name == "run_tests":
            # Fixed command, no model-supplied arguments, run in a temp dir with a timeout: least privilege.
            p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=workdir,
                               capture_output=True, text=True, timeout=30)
            # Keep the END of the output: pytest puts the failure summary last. Cap size to protect context.
            return (p.stdout + p.stderr)[-3000:], p.returncode != 0
        return f"Unknown tool '{name}'.", True

    def obj(props: dict, req: list) -> dict:
        return {"type": "object", "properties": props, "required": req, "additionalProperties": False}

    tools = [
        {"name": "update_todos", "description": "Create or update your plan. Send the full list every time.",
         "strict": True, "input_schema": obj({"todos": {"type": "array", "items": obj(
             {"task": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
             ["task", "status"])}}, ["todos"])},
        {"name": "read_calc", "description": "Read calc.py.", "strict": True, "input_schema": obj({}, [])},
        {"name": "write_calc", "description": "Replace the whole content of calc.py.", "strict": True,
         "input_schema": obj({"content": {"type": "string"}}, ["content"])},
        {"name": "run_tests", "description": "Run the test suite. A failing run returns is_error with the output.",
         "strict": True, "input_schema": obj({}, [])},
    ]
    return tools, execute


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        workdir = Path(d)
        (workdir / "calc.py").write_text(BUGGY)
        (workdir / "test_calc.py").write_text(TESTS)
        tools, execute = make_tools(workdir)
        budget = Budget(max_turns=12, max_total_tokens=60_000, max_cost_usd=0.40, timeout_s=120)
        task = "Tests in test_calc.py fail. Make a todo plan, fix calc.py, and run the tests until they pass."
        result = run_agent(make_client(), [{"role": "user", "content": task}], tools, execute, budget)
        # Verify independently: never trust the model's "all tests pass" claim.
        _, failed = execute("run_tests", {})
        print(f"[stop] {result.stop} | tests {'FAIL' if failed else 'PASS'} (verified by harness)")
        print(result.text)


if __name__ == "__main__":
    main()
