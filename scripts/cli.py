#!/usr/bin/env python3
"""understando: one entry point for every verb. `understando` with no verb prints the menu.

    understando <verb> [--repo DIR] [--pr N] [--run DIR] [--json] [verb options]

commands.json lists the verbs, their category, their one line, their arguments and who may start
them. `understando <verb> --help` shows the options of one verb.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx as context  # noqa: E402
import journal  # noqa: E402
import ops  # noqa: E402
import tm  # noqa: E402
import verdicts  # noqa: E402

S = Path(__file__).resolve().parent
GLOBAL = {"--repo": "repo", "--pr": "pr", "--run": "run"}


def split_globals(argv: list[str]) -> tuple[dict, list[str]]:
    opts: dict = {"repo": None, "pr": None, "run": None, "json": False}
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        name, eq, value = a.partition("=")
        if name in GLOBAL:
            if eq:
                opts[GLOBAL[name]] = value
            else:
                if i + 1 >= len(argv):
                    tm.fail(f"{name} needs a value", 2)
                opts[GLOBAL[name]] = argv[i + 1]
                i += 1
        elif a == "--json":
            opts["json"] = True
        else:
            rest.append(a)
        i += 1
    return opts, rest


def py(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(S / script), *args]).returncode


def do_map(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando map", description="Update the trust map: scan, mechanical checks, verdicts, "
                                 "then the diff against the previous map. The agent writes the claims and the promises (commands/map.md).")
    ap.add_argument("--scan-src")
    ap.add_argument("--scan-tests")
    ap.add_argument("--fail-on-drop", action="store_true")
    args = ap.parse_args(argv)
    data = c.need_map()
    if args.scan_src:
        repo = c.need_repo()
        if py("scan.py", "--repo", str(repo), "--base", data["base"], "--head", data["head"], "--src-prefix", args.scan_src,
              "--test-prefix", args.scan_tests or "tests/", "--add", str(c.map)):
            return 1
    if c.repo and any("mechanical" in v for v in tm.load(c.map)["verifiers"]):
        if py("mechanical.py", "--map", str(c.map), "--repo", str(c.repo)):
            return 1
    data = tm.load(c.map)
    errors = tm.validate(data)
    if errors:
        print("\n".join(f"{c.map}: {e}" for e in errors))
        print(f"INVALID: {len(errors)} errors")
        return 1
    verdicts.apply(data)
    tm.save(data, c.map)
    hist = c.run / "history"
    hist.mkdir(exist_ok=True)
    previous = sorted(hist.glob("trust-map.*.json"))
    code = 0
    if previous:
        code = py("rerun.py", str(previous[-1]), str(c.map), *(["--fail-on-drop"] if args.fail_on_drop else []))
    else:
        print("map: no previous map in history/; this run is the first one.")
    snap = hist / f"trust-map.{tm.now().replace(':', '').replace('+0000', 'Z')}.{data['head'][:10]}.json"
    shutil.copyfile(c.map, snap)
    print("summary: " + ", ".join(f"{k} {v}" for k, v in data["summary"].items()))
    for f in data["flags"]:
        if f.get("loud"):
            print(f"FLAG {f['flag'].upper()}: {f['detail']}")
    return code


def do_probe(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando probe", description="Run each verifier at its commit, then each control in its own "
                                 "scratch worktree of a private clone. Model-free. The user starts it.")
    ap.add_argument("--control", help="comma-separated control IDs")
    ap.add_argument("--only", help="comma-separated verifier IDs")
    ap.add_argument("--env-file")
    args = ap.parse_args(argv)
    data, repo = c.need_map(), c.need_repo()
    only = {x for x in (args.only or "").split(",") if x} or None
    ks = {x for x in (args.control or "").split(",") if x} or None
    with ops.scratch_clone(repo) as (clone, wt):
        ops.probe(data, clone, wt, only, ks, str(Path(args.env_file).resolve()) if args.env_file else None)
    tm.save(data, c.map)
    for cl in data["claims"]:
        print(f"{cl['id']:<5} {cl['verdict']:<9} tier {cl.get('tier') or '-'}  {cl['text']}")
    print("summary: " + ", ".join(f"{k} {v}" for k, v in data["summary"].items()))
    for f in data["flags"]:
        if f.get("loud"):
            print(f"FLAG {f['flag'].upper()}: {f['detail']}")
    journal.append(c.journal, "result", "probe: " + ", ".join(f"{k} {v}" for k, v in data["summary"].items()), repo)
    return 0


def do_formalize(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando formalize", description="Route a claim to tier 4 (TLA+) or 5 (Lean with conformance). "
                                 "It refuses a claim with no stated intent and no user-confirmed invariant.")
    ap.add_argument("--claim")
    ap.add_argument("--invariant")
    ap.add_argument("--tier", type=int, choices=[4, 5])
    ap.add_argument("--sidecar", help="runs/<repo>/<pr>/formal/verifiers.json: sync it with the trust map (scripts/formal_sync.py)")
    args = ap.parse_args(argv)
    if args.sidecar:
        import formal_sync
        out = formal_sync.sync(c, args.sidecar)
        context.emit(c, out, "\n".join(out["report"]))
        return 0
    data = c.need_map()
    tools = context.tool_status()
    if args.invariant and not args.claim:
        if not ops.confirmed_invariant(data, args.invariant):
            print(f"refuse: invariant {args.invariant} has no user-confirmed row (author user, accepted). Run `understando discover` first.")
            return 1
        claim = next((x for x in data["claims"] if x.get("invariant") == args.invariant), None)
        if not claim:
            print(f"formalize: no claim states {args.invariant} yet. Run `understando build claim --invariant {args.invariant}`.")
            return 1
    elif args.claim:
        claim = next((x for x in data["claims"] if x["id"] == args.claim), None)
        if not claim:
            tm.fail(f"formalize: no claim {args.claim}", 2)
    else:
        rows = [x for x in data["claims"] if (x.get("tier_target") or 0) >= 4]
        context.emit(c, {"targets": [x["id"] for x in rows], "toolchains": tools},
                     "formalize targets: " + (", ".join(f"{x['id']} (tier {x['tier_target']})" for x in rows) or "none")
                     + "\ntoolchains: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in tools.items()))
        return 0
    refusal = ops.intent_ok(data, claim, args.invariant)
    if refusal:
        print(refusal)
        return 1
    tier = args.tier or claim.get("tier_target") or 5
    claim["tier_target"] = max(4, min(5, tier))
    tm.save(data, c.map)
    need = ["lean", "lake"] if claim["tier_target"] == 5 else ["java", "tla2tools"]
    missing = [t for t in need if not tools[t]]
    print(f"formalize {claim['id']}: target tier {claim['tier_target']}. Read commands/formalize.md, then route to "
          + ("the skill lean-formal-feedback-loop." if claim["tier_target"] == 5 else "the TLA+ sub-skill that commands/formalize.md names."))
    print("Record the proof or model as a verifier with a `formal` block and a conformance link; a control must break it.")
    if missing:
        print("missing toolchains (install them yourself): " + ", ".join(missing))
    journal.append(c.journal, "decision", f"formalize {claim['id']}: tier {claim['tier_target']}", c.repo, claims=[claim["id"]])
    return 0


def do_explain(c: context.Ctx, argv: list[str]) -> int:
    data = c.need_map()
    repo = c.need_repo()
    args = ["--map", str(c.map), "--repo", str(repo), "--out", str(c.run)]
    if (c.run / "explain.json").is_file():
        args += ["--extra", str(c.run / "explain.json")]
    if c.journal.is_file():
        args += ["--journal", str(c.journal)]
    if (c.run / "ready.json").is_file():
        args += ["--ready", str(c.run / "ready.json")]
    code = py("explain.py", *args, *argv)
    if code == 0:
        write_glossary(data, c.run / "GLOSSARY.md")
    return code


def write_glossary(data: dict, dest: Path) -> None:
    """The map's glossary in the GLOSSARY.md format of domain-modeling: a term, its meaning, its other forms."""
    lines = [f"# {data.get('title') or data['repo']}", "",
             f"The words that the trust map for {data['repo']} #{data.get('pr')} uses. understando explain writes this file.", "",
             "## Language", ""]
    for g in sorted(data.get("glossary") or [], key=lambda g: g["term"].lower()):
        meaning = g["meaning"][0].upper() + g["meaning"][1:]
        lines += [f"**{g['term']}**:", meaning] + ([f"_Avoid_: {', '.join(g['aliases'])}"] if g.get("aliases") else []) + [""]
    dest.write_text("\n".join(lines), encoding="utf-8")


def do_learn(c: context.Ctx, argv: list[str]) -> int:
    print("learn is paused: it stays merged and tested, and gets no new features.", file=sys.stderr)
    run = c.need_run()
    return subprocess.run(["bash", str(tm.ROOT / "learn" / "learn.sh"), str(run),
                           *(["--repo", str(c.repo)] if c.repo else []), *argv]).returncode


def do_setup(c: context.Ctx, argv: list[str]) -> int:
    return subprocess.run(["bash", str(S / "setup.sh"), *argv]).returncode


def do_mode(c: context.Ctx, argv: list[str]) -> int:
    action = argv[0] if argv else "status"
    state = context.load_mode()
    if action == "on":
        run = c.need_run()
        run.mkdir(parents=True, exist_ok=True)
        rest = argv[1:]
        owners = [rest[i + 1] for i, x in enumerate(rest[:-1]) if x == "--with"]
        state = {"on": True, "run": str(run), "repo": str(c.repo) if c.repo else state.get("repo"),
                 "pr": c.pr or state.get("pr"), "since": tm.now(), "autonomy": "--autonomy" in rest, "with": owners}
        context.save_mode(state)
    elif action == "off":
        state = {**state, "on": False, "off_at": tm.now()}
        context.save_mode(state)
    elif action != "status":
        tm.fail("usage: understando mode on|off|status", 2)
    text = (f"understando mode: {'on' if state.get('on') else 'off'}"
            + (f"\n  run: {state.get('run')}\n  repo: {state.get('repo')}\n  pr: {state.get('pr')}"
               f"\n  autonomy: {'full' if state.get('autonomy') else 'off'}"
               + (f"\n  defers to: {', '.join(state['with'])}" if state.get("with") else "") if state.get("on") else "")
            + f"\n  state file: {context.mode_path()}")
    context.emit(c, {**state, "state_file": str(context.mode_path())}, text)
    return 0


def do_note(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando note", description="Append one redacted row to the intent ledger (journal.jsonl).")
    ap.add_argument("kind", nargs="?", choices=journal.KINDS)
    ap.add_argument("text", nargs="*")
    ap.add_argument("--export-tsv", action="store_true", help="write $R/decisions.tsv in the show-me-your-work columns")
    ap.add_argument("--why")
    ap.add_argument("--evidence")
    ap.add_argument("--result")
    ap.add_argument("--claims", default="")
    ap.add_argument("--source")
    args = ap.parse_args(argv)
    c.need_run()
    if args.export_tsv:
        n = journal.export_tsv(journal.read(c.journal), c.run / "decisions.tsv")
        print(f"wrote {n} rows to {c.run / 'decisions.tsv'}")
        return 0
    if not args.kind or not args.text:
        tm.fail("usage: understando note KIND TEXT", 2)
    row = journal.append(c.journal, args.kind, " ".join(args.text), c.repo, why=args.why, evidence=args.evidence,
                         result=args.result, claims=[x for x in args.claims.split(",") if x], source=args.source)
    context.emit(c, row or {"skipped": "duplicate prompt"}, f"noted {args.kind}" if row else "skipped: the same prompt is already in the ledger")
    return 0


def do_hook(c: context.Ctx, argv: list[str]) -> int:
    """The prompt hook. It prints nothing and always exits 0, so a hook can never block a prompt."""
    try:
        state = context.load_mode()
        if not state.get("on") or not state.get("run"):
            return 0
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        text = payload.get("prompt") or payload.get("user_prompt") or payload.get("input") or ""
        if isinstance(text, str) and text.strip():
            journal.append(Path(state["run"]) / "journal.jsonl", "prompt", text, Path(state["repo"]) if state.get("repo") else None,
                           source="hook")
    except Exception:  # noqa: BLE001  a hook must never break the agent's turn
        pass
    return 0


def run_verb(verb: str, argv: list[str], c: context.Ctx) -> int:
    cmds = context.commands()
    if verb in cmds["aliases"]:
        new = cmds["aliases"][verb]
        print(f"understando {verb} is deprecated: use `understando {new}`.", file=sys.stderr)
        verb = new
    if verb == "map":
        return do_map(c, argv)
    if verb == "probe":
        return do_probe(c, argv)
    if verb == "formalize":
        return do_formalize(c, argv)
    if verb == "explain":
        return do_explain(c, argv)
    if verb == "learn":
        return do_learn(c, argv)
    if verb == "setup":
        return do_setup(c, argv)
    if verb == "mode":
        return do_mode(c, argv)
    if verb == "note":
        return do_note(c, argv)
    if verb == "hook":
        return do_hook(c, argv)
    if verb in ("signals", "menu"):
        import signals
        head = None
        if "--pr-head" in argv:
            head = argv[argv.index("--pr-head") + 1]
        if verb == "menu":
            return signals.menu(c, head)
        sig = signals.collect(c, head)
        print(json.dumps(sig, indent=2, ensure_ascii=False))
        return 0
    if verb == "routes":
        import routes
        return routes.main(c, argv)
    if verb == "import":
        import importers
        return importers.main(c, argv)
    if verb == "doctor":
        import doctor
        return doctor.main(c, argv)
    if verb == "discover":
        import discover
        return discover.main(c, argv)
    if verb == "close":
        import close
        return close.main(c, argv)
    if verb == "trim":
        import trim
        return trim.main(c, argv)
    if verb == "build":
        import build
        return build.main(c, argv)
    if verb == "ready":
        import ready
        return ready.main(c, argv, lambda v, a: run_verb(v, a, c))
    print(f"understando: unknown verb {verb!r}. Run `understando help`.", file=sys.stderr)
    return 2


def help_text() -> str:
    import signals
    cmds = context.commands()
    return (__doc__.strip() + "\n" + signals.table(cmds)
            + "\n\nGlobal options: --repo DIR (local clone of the reviewed repo), --pr N, --run DIR (run folder), --json.")


def main(argv: list[str]) -> int:
    opts, rest = split_globals(argv)
    c = context.resolve(opts["run"], opts["repo"], opts["pr"], opts["json"])
    if not rest:
        return run_verb("menu", [], c)
    verb, args = rest[0], rest[1:]
    if verb in ("help", "-h", "--help"):
        print(help_text())
        return 0
    return run_verb(verb, args, c)


if __name__ == "__main__":
    os.environ.setdefault("DO_NOT_TRACK", "1")
    sys.exit(main(sys.argv[1:]))
