"""6.8 Run model-written Python with basic limits: temp directory, timeout, no secrets, bounded output.

THIS IS NOT A SECURITY BOUNDARY. It limits accidents and runaway code (infinite loops, huge output, leaked
env vars). It does NOT block the network, read access to the rest of your disk, or a determined attacker.
For untrusted code use a container or microVM (Docker with no network and a read-only root, gVisor,
Firecracker) or a hosted sandbox such as the code execution server tool (2.6).

Usage: python 06_harness/sandbox/runner.py   (runs three demo snippets, no API calls)
"""
import os
import resource
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}  # an allowlist: nothing from our environment leaks in


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool
    truncated: bool


def _limits(cpu_s: int, max_file_bytes: int):
    def apply():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))  # kernel kills a CPU hog
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))  # caps how much it can write
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def run_python(code: str, timeout_s: float = 5.0, max_output: int = 2_000, cpu_s: int = 5,
               max_file_bytes: int = 1_000_000) -> SandboxResult:
    with tempfile.TemporaryDirectory() as work:  # code starts in an empty throwaway directory
        work_dir = Path(work)
        out_path, err_path = work_dir / ".stdout", work_dir / ".stderr"
        timed_out = False
        # Output goes to files, not pipes: a runaway printer fills a capped file instead of our memory.
        with out_path.open("wb") as fo, err_path.open("wb") as fe:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", code],  # -I: isolated mode, ignores PYTHON* env vars and user site
                cwd=work, env=CLEAN_ENV, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                start_new_session=True,  # own process group, so the kill below also reaches child processes
                preexec_fn=_limits(cpu_s, max_file_bytes),
            )
            try:
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()

        def read(path: Path) -> tuple[str, bool]:
            with path.open("rb") as f:
                data = f.read(max_output + 1)
            return data[:max_output].decode(errors="replace"), len(data) > max_output

        stdout, cut_out = read(out_path)
        stderr, cut_err = read(err_path)
        if cut_out:
            stdout += f"\n[output truncated at {max_output} bytes]"  # never cut silently
        return SandboxResult(stdout, stderr, None if timed_out else proc.returncode, timed_out, cut_out or cut_err)


def main() -> None:
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-demo-not-a-real-key"  # prove it does not reach the child
    demos = {
        "normal": "print(sum(range(10)))",
        "env scrubbed": "import os; print('ANTHROPIC_API_KEY' in os.environ, sorted(os.environ))",
        "infinite loop": "while True: pass",
        "huge output": "print('x' * 10_000_000)",
    }
    for name, code in demos.items():
        r = run_python(code, timeout_s=2, cpu_s=2, max_output=200)
        print(f"{name:>13}: rc={r.returncode} timed_out={r.timed_out} truncated={r.truncated} out={r.stdout[:70]!r}")


if __name__ == "__main__":
    main()
