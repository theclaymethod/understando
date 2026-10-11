#!/usr/bin/env python3
"""understando: one entry point for every verb. `understando` with no verb asks one question (the menu).
`understando N` is `understando review N`. `understando help` prints the three entry points (review,
open, build); `understando help --all` prints every verb, also the advanced and internal ones.

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
import tempfile
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
            elif name == "--repo" and (i + 1 >= len(argv) or argv[i + 1].startswith("-")):
                opts["repo_flag"] = True  # `setup --repo` with no folder: the cwd clone
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


def snapshot_before(c: context.Ctx) -> Path | None:
    """Keep the map as it is now in history/ before a verb rewrites it, so that map diffs against it.
    It writes a copy only when history/ has no copy with the same content."""
    if not (c.run and c.map and c.map.is_file()):
        return None
    hist = c.run / "history"
    hist.mkdir(exist_ok=True)
    body = c.map.read_bytes()
    previous = sorted(hist.glob("trust-map.*.json"))
    if previous and previous[-1].read_bytes() == body:
        return previous[-1]
    head = (json.loads(body).get("head") or "")[:10]
    snap = hist / f"trust-map.{tm.now().replace(':', '').replace('+0000', 'Z')}.{head}.before.json"
    snap.write_bytes(body)
    return snap


def do_map(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando map", description="Update the trust map: scan, mechanical checks, verdicts, "
                                 "then the diff against the previous map. The agent writes the claims and the promises (commands/map.md).")
    ap.add_argument("--scan-src")
    ap.add_argument("--scan-tests")
    ap.add_argument("--fail-on-drop", action="store_true")
    args = ap.parse_args(argv)
    data = c.need_map()
    snapshot_before(c)
    if args.scan_src:
        repo = c.need_repo()
        if py("scan.py", "--repo", str(repo), "--base", data["base"], "--head", data["head"], "--src-prefix", args.scan_src,
              "--test-prefix", args.scan_tests or "tests/", "--add", str(c.map)):
            return 1
    if c.repo and any("mechanical" in v for v in tm.load(c.map)["verifiers"]):
        if py("mechanical.py", "--map", str(c.map), "--repo", str(c.repo)):
            return 1
    data = tm.load(c.map)
    import names
    named = names.fill(data)
    errors = tm.validate(data)
    if errors:
        print("\n".join(f"{c.map}: {e}" for e in errors))
        print(f"INVALID: {len(errors)} errors")
        return 1
    verdicts.apply(data)
    tm.save(data, c.map)
    if named:
        print(f"map: wrote a plain name for {named} claims, verifiers and invariants (the prompts show these names; edit any name in the map)")
    hist = c.run / "history"
    hist.mkdir(exist_ok=True)
    previous = sorted(hist.glob("trust-map.*.json"))
    code = 0
    if previous:
        code = py("rerun.py", str(previous[-1]), str(c.map), *(["--fail-on-drop"] if args.fail_on_drop else []))
    else:
        print("map: no earlier map to compare; this map is the first one.")
    if c.repo:
        import newtests
        for line in newtests.report(c, data):
            print(line)
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
    ap.add_argument("--paid", default="", help="verifier IDs that need the model key: the user said yes to their shown cost")
    args = ap.parse_args(argv)
    data, repo = c.need_map(), c.need_repo()
    only = {x for x in (args.only or "").split(",") if x} or None
    ks = {x for x in (args.control or "").split(",") if x} or None
    import ci
    import config
    import repoinfo
    cfg = config.load(repoinfo.repo_name(repo))
    config.drop_inherited_key(cfg)
    refusal, notes = ci.gate(c, data, only)
    for n in notes:
        print(f"probe: {n}", file=sys.stderr)
    if refusal:
        print(refusal)
        return 1
    paid = {x for x in args.paid.split(",") if x}
    keyed = {v["id"] for v in data["verifiers"] if "command" in v and config.needs_key(cfg, v["command"]["argv"])}
    skip = keyed - paid
    import userpath
    for vid in userpath.mark(data, repo, only):
        print(f"probe: {vid} is labelled e2e, but it only calls internal functions; its tier label is now integration")
    # Report a skip only for a verifier in scope (--only); the prompt shows the paid ones once, with their cost.
    for vid in sorted(skip & only if only else skip):
        print(f"skip {vid}: it needs {(cfg.get('llm') or {}).get('env_var', 'the model key')} from the key file, and it is a paid step. "
              f"It never runs with the key unset. Show the cost; after a clear yes, run probe --paid {vid}.")
    if skip:
        only = (only or {v["id"] for v in data["verifiers"] if "command" in v}) - skip
        ks = {k["id"] for k in data["controls"] if k["verifier"] in only} if ks is None else ks - {k["id"] for k in data["controls"] if k["verifier"] in skip}
    env_file = str(Path(args.env_file).resolve()) if args.env_file else None
    with tempfile.TemporaryDirectory(prefix="understando-key-") as kd:
        if keyed & paid:
            llm = cfg.get("llm") or {}
            if not llm.get("env_file") or not config.key_names_present(Path(llm["env_file"]), llm.get("env_var", "")):
                print(f"refuse: {', '.join(sorted(keyed & paid))} need {llm.get('env_var')} from {llm.get('env_file')}, and it is not set there.")
                return 1
            wrapper = str(config.key_wrapper(cfg, Path(kd), env_file))
            for v in data["verifiers"]:
                if v["id"] in keyed & paid:
                    v["command"]["_env"] = wrapper   # for this run only: popped before the save
        # A verifier that needs no key gets no key: it runs with the user's --env-file, or with none.
        for v in data["verifiers"]:
            if "command" in v and "_env" not in v["command"]:
                v["command"]["_env"] = env_file if v["command"].get("env_file") else None
        try:
            with ops.scratch_clone(repo) as (clone, wt):
                ops.probe(data, clone, wt, only, ks, env_file)
        finally:
            for v in data["verifiers"]:
                (v.get("command") or {}).pop("_env", None)
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
    import config
    import publish
    ve = config.ve_runtime()
    if ve and "--runtime" not in argv:
        args += ["--runtime", ve]
    html = "--html" in argv
    argv = [a for a in argv if a != "--html"]
    map_sha = publish._sha256(c.map)
    code = py("explain.py", *args, *argv)
    if code == 0:
        write_glossary(data, c.run / "GLOSSARY.md")
        publish.write_stamp(c.run, map_sha)
    if code == 0 and html:
        # The page: the explainer source exported by the visual-explainer runtime (commands/explain.md, step 5).
        runtime = ve or subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import explain; print(explain.runtime_path(None))", str(S)],
                                       capture_output=True, text=True).stdout.strip()
        cli = Path(runtime) / "scripts" / "artifacture.mjs"
        if not cli.is_file():
            print(f"explain --html: no Artifacture runtime at {runtime}. Set UNDERSTANDO_VE_RUNTIME, or run setup.")
            return 1
        code = subprocess.run(["node", str(cli), "export", str(c.run / "explainer.mdx"), "--out", str(c.run / "explainer.html")]).returncode
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
    if REPO_FLAG[0] or "--repo" in argv:
        import config
        import repoinfo
        args = [a for a in argv if a != "--repo"]
        answers = args[args.index("--answers") + 1] if "--answers" in args else None
        repo = c.repo or repoinfo.repo_root(Path.cwd())
        if not repo:
            tm.fail("setup --repo: run it in a clone of the reviewed repo, or pass --repo DIR", 2)
        return config.setup_repo(repoinfo.repo_name(repo), repoinfo.slug(repoinfo.origin_url(repo)), answers)
    return subprocess.run(["bash", str(S / "setup.sh"), *argv]).returncode


REPO_FLAG = [False]


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
        if not state.get("on") or not state.get("run") or context.refuse_run_write(Path(state["run"]), Path(state["repo"]) if state.get("repo") else None):
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


def lock_paths(verb: str, argv: list[str]) -> list[str]:
    """The paths that a verb writes, for the run lock. Read-only forms take no lock."""
    if "--help" in argv or "-h" in argv:
        return []
    if verb == "map":
        return ["run:trust-map.json", "run:history/"]
    if verb == "probe":
        return ["run:trust-map.json"]
    if verb == "close":
        return [] if "--list" in argv or "--next" in argv or not (argv or sys.stdin.isatty()) else ["run:trust-map.json", "ready:"]
    if verb == "trim":
        if "--accept" in argv:
            return ["run:trim.json"]
        return ["run:trim.json"] if "--report" in argv else ["run:trust-map.json", "run:trim.json", "ready:"]
    if verb == "discover":
        return [] if (argv[:1] in (["status"], ["questions"])) else ["run:trust-map.json", "run:discover.json"]
    if verb == "formalize":
        return ["run:trust-map.json", "run:formal/"] if "--sidecar" in argv or "--claim" in argv or "--invariant" in argv else []
    if verb == "import":
        return ["run:trust-map.json"]
    if verb == "explain":
        return ["run:explainer.html", "run:refs.resolved.json", "run:pr-section.md", "run:GLOSSARY.md", "run:explain.stamp.json"]
    if verb == "ready":
        return ["run:ready.json"]
    if verb == "ci":
        return [] if "--check-argv" in argv else ["run:ci.json"]
    if verb == "build":
        return ["run:trust-map.json"] if argv[:1] in (["claim"], ["verifier"], ["red-first"]) else []
    return []


def run_verb(verb: str, argv: list[str], c: context.Ctx) -> int:
    cmds = context.commands()
    if verb in cmds["aliases"]:
        new = cmds["aliases"][verb]
        print(f"understando {verb} is deprecated: use `understando {new}`.", file=sys.stderr)
        verb = new
    paths = lock_paths(verb, argv)
    writes_run = bool(paths) or verb == "note" or (verb == "mode" and argv[:1] == ["on"])
    refusal = context.refuse_run_write(c.run, c.repo) if writes_run and "--help" not in argv and "-h" not in argv else None
    if refusal:
        print(refusal)
        return 1
    if paths and c.run:
        import lock
        try:
            with lock.held(c.run, verb, paths):
                return dispatch(verb, argv, c)
        except lock.Busy as exc:
            print(str(exc))
            return 1
    return dispatch(verb, argv, c)


def dispatch(verb: str, argv: list[str], c: context.Ctx) -> int:
    if verb == "review":
        import review
        return review.main(c, argv)
    if verb == "ci":
        import ci
        return ci.main(c, argv)
    if verb == "lock":
        import lock
        return lock.main(c, argv)
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
            return signals.menu(c, head, show_all="--all" in argv or "all" in argv)
        sig = signals.collect(c, head)
        print(json.dumps(sig, indent=2, ensure_ascii=False))
        return 0
    if verb == "routes":
        import routes
        return routes.main(c, argv)
    if verb == "import":
        import importers
        return importers.main(c, argv)
    if verb == "open":
        import opener
        return opener.main(c, argv)
    if verb == "snippet":
        import coderef
        return coderef.main(c, argv)
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
    if verb == "publish":
        import publish
        return publish.main(c, argv)
    print(f"understando: unknown verb {verb!r}. Run `understando help`.", file=sys.stderr)
    return 2


def help_text(show_all: bool = False) -> str:
    import signals
    cmds = context.commands()
    if show_all:
        body = signals.table(cmds)
    else:
        body = "\nEntry points\n" + "\n".join(f"  {v['id']:<10} {v['line']}" for v in cmds["verbs"] if v.get("tier") == "entry") \
            + "\n\nAdvanced verbs: `understando help --all`."
    return (__doc__.strip() + "\n" + body
            + "\n\nGlobal options: --repo DIR (local clone of the reviewed repo), --pr N, --run DIR (run folder), --json.")


def main(argv: list[str]) -> int:
    opts, rest = split_globals(argv)
    REPO_FLAG[0] = bool(opts["repo"] or opts.get("repo_flag")) and rest[:1] == ["setup"]
    c = context.resolve(opts["run"], opts["repo"], opts["pr"], opts["json"])
    if not rest:
        return run_verb("menu", [], c)
    verb, args = rest[0], rest[1:]
    if verb.isdigit():
        verb, args = "review", rest
    if verb in ("help", "-h", "--help"):
        print(help_text("--all" in args or "all" in args))
        return 0
    return run_verb(verb, args, c)


if __name__ == "__main__":
    os.environ.setdefault("DO_NOT_TRACK", "1")
    sys.exit(main(sys.argv[1:]))
