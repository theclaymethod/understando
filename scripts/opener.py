"""understando open: open the explainer of the run in the user's browser, at a level, a promise or a claim.

    understando open [<pr>] [--level story|loop|change|promises|verifiers|unclaimed|tradeoffs|glossary]
                     [--anchor ID] [--no-open] [--teach] [--ask TEXT] [--json]

For the reviewer: with a PR number and no local run, it fetches the review branch
understando/<pr>-review into a read-only worktree (scripts/publish.py) and opens its explainer.
Then one question: walk through it (teach), or ask about one part. --ask records the question
as a `confusion` row with its anchor in the reviewer's own run journal.

It opens $R/explainer.html with `open` (macOS) or `xdg-open` (Linux, with a display). With no
display, with --no-open, or with $UNDERSTANDO_NO_OPEN set, it prints the file path and the file://
URL. $UNDERSTANDO_OPENER names another opener command (the e2e test uses a fake). Each open writes
one row to $R/opened.jsonl, so a stop can say what it opened.

The anchors are the stable ids of the explainer: the levels (#story, #loop, #change, #promises,
#verifiers, #unclaimed, #tradeoffs, #glossary), the merge verdict (#merge), a
promise (#promise-<id>) and a claim (#claim-<id>). `--anchor G3` and `--anchor C15` give
#promise-g3 and #claim-c15; `--level changed` is #change.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import ctx as context  # noqa: E402
import tm  # noqa: E402

LEVELS = {"story": "story", "verdict": "merge", "merge": "merge", "why": "why", "loop": "loop",
          "change": "changed", "changed": "changed", "promises": "promises", "verifiers": "verifiers",
          "unclaimed": "unclaimed", "tradeoffs": "tradeoffs", "glossary": "glossary"}
SECTION_NAME = {"story": "the story", "merge": "'Can you merge it?'", "why": "why it was built this way",
                "loop": "the loop", "changed": "what changed", "promises": "the promises", "verifiers": "the checks",
                "unclaimed": "the unclaimed changes", "tradeoffs": "the trade-offs", "glossary": "the glossary"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def anchor_for(data: dict | None, level: str | None, anchor: str | None) -> str:
    if anchor:
        a = anchor.lstrip("#")
        if data:
            if any(p["id"] == a for p in data.get("promises", [])):
                return f"promise-{slug(a)}"
            if any(c["id"] == a for c in data.get("claims", [])):
                return f"claim-{slug(a)}"
        return LEVELS.get(a, a)
    return LEVELS.get(level or "story", level or "story")


def section_name(data: dict | None, anchor: str) -> str:
    if anchor.startswith("promise-") and data:
        p = next((p for p in data.get("promises", []) if f"promise-{slug(p['id'])}" == anchor), None)
        if p:
            return f"the promise '{p.get('label') or p['id']}'"
    if anchor.startswith("claim-") and data:
        c = next((c for c in data.get("claims", []) if f"claim-{slug(c['id'])}" == anchor), None)
        if c:
            return f"the claim '{c.get('name') or c['text']}'"
    return SECTION_NAME.get(anchor, anchor)


def status(run: Path, data: dict | None) -> dict:
    """{present, stale, why, path}. Stale: the page was built at another map head, or before the last map."""
    html, mdx = run / "explainer.html", run / "explainer.mdx"
    out = {"present": html.is_file(), "path": str(html), "mdx": mdx.is_file(), "stale": False, "why": None}
    if not html.is_file():
        out["why"] = "no explainer page yet" if not mdx.is_file() else "the explainer source exists, but no page was exported"
        return out
    if (run / "explain.stamp.json").is_file() and data:
        import publish
        why = [r for r in publish.stale_reasons(run, data) if "no explainer.html" not in r]
        if why:
            plain = ("it was built at an older map head" if "head" in why[0] else
                     "the trust map changed after it was built" if "trust-map" in why[0] else "its source changed after the export")
            out.update(stale=True, why=plain)
        return out
    cache = run / "refs.resolved.json"
    built_head = None
    if cache.is_file():
        try:
            built_head = json.loads(cache.read_text(encoding="utf-8")).get("head")
        except json.JSONDecodeError:
            built_head = None
    if data and built_head and built_head != data.get("head"):
        out.update(stale=True, why="it was built at an older map head")
    elif data and (run / "trust-map.json").is_file() and html.stat().st_mtime < (run / "trust-map.json").stat().st_mtime:
        out.update(stale=True, why="it is older than the trust map")
    elif mdx.is_file() and html.stat().st_mtime < mdx.stat().st_mtime:
        out.update(stale=True, why="it is older than its source")
    return out


def opener() -> list[str] | None:
    if os.environ.get("UNDERSTANDO_NO_OPEN"):
        return None
    if os.environ.get("UNDERSTANDO_OPENER"):
        return [os.environ["UNDERSTANDO_OPENER"]]
    if sys.platform == "darwin" and shutil.which("open"):
        return [shutil.which("open")]
    if shutil.which("xdg-open") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return [shutil.which("xdg-open")]
    return None


def open_page(run: Path, data: dict | None, level: str | None = None, anchor: str | None = None,
              no_open: bool = False, why: str = "", log_dir: Path | None = None) -> dict:
    """Open the explainer at the anchor, or print where it is. Returns the event row."""
    st = status(run, data)
    a = anchor_for(data, level, anchor)
    url = Path(st["path"]).resolve().as_uri() + "#" + a
    row = {"at": tm.now(), "anchor": a, "url": url, "path": st["path"], "section": section_name(data, a),
           "stale": st["stale"], "stale_why": st["why"] if st["stale"] else None, "why": why, "opened": False, "present": st["present"]}
    if st["present"]:
        cmd = None if no_open else opener()
        if cmd:
            out = subprocess.run([*cmd, url], capture_output=True, text=True)
            row["opened"] = out.returncode == 0
            row["by"] = Path(cmd[0]).name
    if st["present"]:
        with open((log_dir or run) / "opened.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def said(row: dict) -> str:
    """The plain line for chat."""
    if not row["present"]:
        return "No explainer page yet."
    stale = f" It is out of date ({row['stale_why']}), so its verdicts can be old." if row["stale"] else ""
    if row["opened"]:
        return f"I opened the explainer at {row['section']}.{stale}"
    return f"The explainer is ready at {row['section']} (ref: {row['url']}).{stale}"


def find_run(c: context.Ctx, pr: str | None) -> tuple[Path | None, Path | None, str]:
    """(the folder with the explainer, the reviewer's own run folder for state and journal, how).
    --run or the mode, else the local run under config.runs_root(), else the review branch that
    publish.fetch_review_branch() checks out read-only; then the state goes to the local run folder."""
    if c.run and (not pr or c.run.name == str(pr)):
        return c.run, c.run, "local"
    import config
    import repoinfo
    root = c.repo or repoinfo.repo_root(Path.cwd())
    if not pr:
        return None, None, "no run folder: pass a PR number, or --run DIR"
    local = config.runs_root() / repoinfo.repo_name(root) / str(pr) if root else None
    if local and ((local / "explainer.html").is_file() or (local / "trust-map.json").is_file()):
        return local, local, "local"
    if not root:
        return None, None, "run it in a clone of the reviewed repo: the review branch comes from its origin"
    try:
        import publish  # the publish side owns this helper; understando keeps no second copy
        page = publish.fetch_review_branch(root, str(pr))
    except ImportError:
        return None, None, "the review branch cannot be fetched: scripts/publish.py (fetch_review_branch) is missing"
    except Exception as exc:  # noqa: BLE001
        return None, None, f"cannot fetch the review branch understando/{pr}-review (fetch_review_branch): {exc}"
    local.mkdir(parents=True, exist_ok=True)
    return Path(page), local, "review-branch"


def state(run: Path) -> dict:
    p = run / "open.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save(run: Path, st: dict) -> None:
    (run / "open.json").write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def last_anchor(run: Path) -> str | None:
    p = run / "opened.jsonl"
    if not p.is_file():
        return None
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows[-1]["anchor"] if rows else None


def question(pr: str, row: dict) -> dict:
    import prompt
    lines = [said(row)] if row["present"] else ["No explainer page in this run yet."]
    return prompt.make(lines, "How do you want to read it?", [
        prompt.option("Walk me through it", "Opens the explainer one part at a time: the story, the loop, what changed, the weakest promises. "
                      "In chat: at most four ideas, the code by refs, and your questions.", f"understando open {pr} --teach"),
        prompt.option("Ask about one part", "Opens that part, then answers in at most three sentences.",
                      f"understando open {pr} --ask \"<your question>\""),
        ],
        {"step": "open", "does": "Read the explainer of the PR", "scope": "the whole page", "cost": "$0, no model call",
         "time": "as long as you want", "writes": "your own run journal, which the author sees only after publish --feedback"})


def main(c: context.Ctx, argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="understando open", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", nargs="?")
    ap.add_argument("--level")
    ap.add_argument("--anchor")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--teach", action="store_true", help="the next teach turn (the same teach stop as review)")
    ap.add_argument("--ask", metavar="TEXT", help="record a question or an 'I don't get this' moment, at the open anchor")
    args = ap.parse_args(argv)
    no_open = args.no_open or bool(os.environ.get("UNDERSTANDO_NO_OPEN"))
    run, home, how = find_run(c, args.pr)
    if not run:
        context.emit(c, {"error": how}, f"open: {how}")
        return 2
    refusal = context.refuse_run_write(home, c.repo)
    if refusal:
        context.emit(c, {"error": refusal}, refusal)
        return 1
    page_dir = run
    c = context.Ctx(home, c.repo, args.pr or c.pr, c.json)
    data = tm.load(page_dir / "trust-map.json") if (page_dir / "trust-map.json").is_file() else c.data()
    pr = str(args.pr or (data or {}).get("pr") or "")
    if args.teach:
        import review
        st = state(home)
        text = review.teach_turn(c, st, no_open, page_dir=page_dir, data=data)
        save(home, st)
        context.emit(c, {"teach": st.get("teach"), "reply": text}, text)
        return 0
    if args.ask:
        import journal
        if args.anchor or args.level:
            open_page(page_dir, data, args.level, args.anchor, no_open, why="question", log_dir=home)
        anchor = last_anchor(home)
        journal.append(c.journal, "confusion", args.ask, c.repo, anchor=anchor, source="reviewer")
        text = (f"Noted at {section_name(data, anchor)} in your own run journal. "
                "The author sees it only after you run `understando publish --feedback`.") if anchor else \
            "Noted in your own run journal."
        context.emit(c, {"recorded": True, "anchor": anchor}, text)
        return 0
    row = open_page(page_dir, data, args.level or ("verdict" if not args.anchor else None), args.anchor, no_open, why="open", log_dir=home)
    if not row["present"]:
        context.emit(c, {"error": "no explainer page", **row}, f"open: no explainer page in {page_dir}. Run `understando explain --html` first.")
        return 1
    if args.level or args.anchor or not pr:
        text = f"{row['path']}\n{row['url']}" + (f"\nstale: {row['stale_why']}" if row["stale"] else "")
        context.emit(c, row, text)
        return 0
    import prompt
    q = question(pr, row)
    context.emit(c, {**row, "source": how, "prompt": q}, f"{row['path']}\n{row['url']}\n\n" + prompt.render(q))
    return 0
