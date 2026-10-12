# setup

Start it only on an explicit request from the user.

1. Run `understando setup`. It is idempotent. It links the CLI into `~/.local/bin` and the skill into the four skill folders, makes the mutation venv (`~/.understando/tools/mutation`: mutmut, cosmic-ray and pytest from PyPI, through uv), and, for the scope that the user picks, installs a missing Code Contracts skill, the pstack verification skills, asd-ste100 and visual-explainer. It ends with `understando doctor`.
   - **Done when** doctor names no missing required piece.
2. When a link step prints `refuse:`, another skill holds the name. Keep that skill. Report the path and stop.
3. `understando setup --links-only` makes only the links; `understando setup --mutation` makes only the mutation venv.

Lean (elan, `lake`), java and `~/.understando/tools/tla2tools.jar` are for formalize. understando finds java at `$JAVA_HOME/bin/java` or Homebrew's openjdk without a PATH edit. Install them yourself.
