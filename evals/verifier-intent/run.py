"""Capture a new read-only response for each synthetic scenario."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("skill", type=Path)
parser.add_argument("run_dir", type=Path)
args = parser.parse_args()
skill = args.skill.read_bytes()
args.run_dir.mkdir(parents=True, exist_ok=False)
(args.run_dir / "SKILL.md").write_bytes(skill)
scenarios = (ROOT / "scenarios.jsonl").read_bytes()
(args.run_dir / "scenarios.jsonl").write_bytes(scenarios)
with (args.run_dir / "traces.jsonl").open("x") as traces:
    for line in scenarios.splitlines():
        case = json.loads(line)
        task = case["context"] + "\n\n" + case["ask"]
        prompt = "Apply the following skill in a read-only review. Answer from the supplied ticket alone without tool calls.\n\n" + skill.decode() + "\n\nTicket\n" + task
        trace = dict(id=case["id"], family=case["family"], input=task, input_origin="synthetic",
                     revision=hashlib.sha256(skill).hexdigest())
        output = (args.run_dir / (case["id"] + ".md")).resolve()
        with tempfile.TemporaryDirectory() as scratch:
            cmd = ["codex", "exec", "--ignore-user-config", "-m", "gpt-6-astra", "-c", "features.shell_tool=false", "-c", 'web_search="disabled"', "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                   "--json", "-o", str(output), "-"]
            events = args.run_dir / (case["id"] + ".events.jsonl")
            log = args.run_dir / (case["id"] + ".stderr")
            with events.open("x") as stdout, log.open("x") as stderr:
                try:
                    result = subprocess.run(cmd, input=prompt, text=True, cwd=scratch,
                                            stdout=stdout, stderr=stderr, timeout=180)
                    if result.returncode or not output.exists() or not output.read_text().strip():
                        trace["error"] = f"No successful response (exit {result.returncode}). See {log.name}."
                    else:
                        trace["output"] = output.read_text()
                except (OSError, subprocess.TimeoutExpired) as exc:
                    trace["error"] = str(exc)
        traces.write(json.dumps(trace) + "\n")
        traces.flush()
        print(case["id"], "error" if "error" in trace else "captured", flush=True)
