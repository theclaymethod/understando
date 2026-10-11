"""Machine setup steps that scripts/setup.sh calls. Standard library only.

    python3 scripts/setup.py ve-runtime [--set PATH]   pin the visual-explainer runtime (asks once)
    python3 scripts/setup.py path-hint                 the line to add to the shell rc, when ~/.local/bin is not on PATH

ve_runtime lives in ~/.understando/config.toml. When it is set and complete, setup does not ask
again. $UNDERSTANDO_VE_RUNTIME still overrides it for one command.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testguard  # noqa: E402,F401  (the test-isolation guard: it must load before any write)
import config  # noqa: E402


def candidates() -> list[str]:
    """Runtimes that may exist on this machine, best first."""
    home = Path.home()
    out = [home / ".artifacture", home / ".artifacture" / "runtime"]
    skill = home / ".claude" / "skills" / "visual-explainer" / "SKILL.md"
    if skill.exists():
        out.append(skill.resolve().parent.parent.parent)
    return [str(p) for p in out if p.is_dir() and not config.ve_missing(p)]


def ve_runtime(explicit: str | None) -> int:
    cur = config.load_global().get("ve_runtime")
    if explicit:
        path = str(Path(explicit).expanduser().resolve())
    elif cur and not config.ve_missing(cur):
        print(f"ok        ve_runtime                         {cur}")
        return 0
    elif sys.stdin.isatty():
        default = (candidates() or [cur or ""])[0]
        got = input(f"The visual-explainer runtime (an Artifacture checkout) [{default}]: ").strip()
        path = str(Path(got or default).expanduser().resolve()) if (got or default) else ""
    else:
        print("ve_runtime is not set. Run `understando setup --ve-runtime PATH` (an Artifacture checkout that holds "
              + ", ".join(config.VE_PARTS) + ").")
        return 2
    if not path:
        print("ve_runtime: no path given; nothing written.")
        return 2
    missing = config.ve_missing(path)
    if missing:
        print(f"refuse: {path} lacks {', '.join(missing)}; nothing written.")
        return 1
    print(f"wrote ve_runtime = {path} in {config.save_global({'ve_runtime': path})}")
    return 0


def path_hint() -> int:
    bin_dir = Path.home() / ".local" / "bin"
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        return 0
    shell = Path(os.environ.get("SHELL", "")).name
    rc = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "fish": "~/.config/fish/config.fish"}.get(shell, "your shell rc")
    line = 'fish_add_path ~/.local/bin' if shell == "fish" else 'export PATH="$HOME/.local/bin:$PATH"'
    print(f"~/.local/bin is not on PATH. Add this line to {rc}:\n  {line}")
    return 0


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="setup.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("ve-runtime")
    v.add_argument("--set")
    sub.add_parser("path-hint")
    args = ap.parse_args(argv)
    return ve_runtime(args.set) if args.cmd == "ve-runtime" else path_hint()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
