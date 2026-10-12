"""6.17 Observability: a structured trace per turn, and a triage that points at the faulty layer.

When an agent run goes wrong, "the model was dumb" is rarely the answer. A trace lets you PROVE which layer
failed: prompt/model, tools, context, or harness. Default mode replays two scripted runs offline (one healthy,
one broken) so you can see the difference; `--live` records a real, budgeted run.
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # make `common` importable
sys.path.insert(0, str(ROOT / "03_agents"))  # reuse the bounded loop from Level 3

from agent import run_agent

from common.budget import Budget
from common.harness import Harness, Policy, Rule
from common.tracing import Tracer, load, summarize, triage
from common.workspace_tools import make_workspace


class ScriptedModel:
    """Stands in for the API so the demo is free and deterministic. Each step: (stop_reason, blocks, tokens)."""

    def __init__(self, steps):
        self.steps, self.messages, self.n = list(steps), self, 0

    def create(self, **kw):
        self.n += 1
        stop, blocks, (inp, out, cache_read) = self.steps[min(self.n - 1, len(self.steps) - 1)]
        usage = NS(input_tokens=inp, output_tokens=out, cache_creation_input_tokens=0, cache_read_input_tokens=cache_read)
        return NS(stop_reason=stop, content=blocks, usage=usage, _request_id=f"req_demo{self.n:03d}")


def use(i, name, **inp):
    return NS(type="tool_use", id=f"t{i}", name=name, input=inp)


def say(text):
    return NS(type="text", text=text)


def healthy_run(tracer: Tracer, handlers: dict, schemas: list) -> None:
    model = ScriptedModel([
        ("tool_use", [use(1, "list_files")], (900, 40, 0)),
        ("tool_use", [use(2, "read_file", path="notes.txt")], (150, 40, 900)),
        ("end_turn", [say("The notes say hello.")], (200, 30, 900)),
    ])
    harness = Harness(handlers, Policy([Rule("*", "allow")]), tracer=tracer)
    run_agent(model, [{"role": "user", "content": "Summarise notes.txt"}], schemas, harness.execute,
              Budget(max_turns=6), tracer=tracer)


def broken_run(tracer: Tracer, handlers: dict, schemas: list) -> None:
    # The model keeps reading a file that does not exist while its context balloons, and a limit stops it.
    model = ScriptedModel([("tool_use", [use(i, "read_file", path=f"missing{i}.txt")], (500 * i * i, 40, 0))
                           for i in range(1, 6)])
    harness = Harness(handlers, Policy([Rule("*", "allow")]), tracer=tracer)
    run_agent(model, [{"role": "user", "content": "Summarise the notes"}], schemas, harness.execute,
              Budget(max_turns=5), tracer=tracer)


def show(label: str, path: Path) -> None:
    records = load(path)
    print(f"\n=== {label} ({path.name}, {len(records)} records)")
    for k, v in summarize(records).items():
        print(f"  {k}: {v}")
    print("  triage:")
    for line in triage(records):
        print(f"    - {line}")


def main() -> None:
    out_dir = ROOT / ".traces"  # git-ignored
    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        (Path(tmp) / "notes.txt").write_text("hello")
        for label, fn, name in [("healthy run", healthy_run, "healthy.jsonl"), ("broken run", broken_run, "broken.jsonl")]:
            path = out_dir / name
            path.unlink(missing_ok=True)  # one fresh file per run
            fn(Tracer(path, run_id=name.split(".")[0]), handlers, schemas)
            show(label, path)


def live() -> None:
    from common.config import make_client

    path = ROOT / ".traces" / "live.jsonl"
    path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        schemas, handlers = make_workspace(tmp)
        tracer = Tracer(path)
        harness = Harness(handlers, Policy([Rule("*", "allow")]), tracer=tracer)
        run_agent(make_client(), [{"role": "user", "content": "Write 'hi' to a.txt, then read it back."}], schemas,
                  harness.execute, Budget(max_turns=6, max_total_tokens=30_000, max_cost_usd=0.20, timeout_s=90), tracer=tracer)
    show("live run", path)


if __name__ == "__main__":
    live() if "--live" in sys.argv else main()
