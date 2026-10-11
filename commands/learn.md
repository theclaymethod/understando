# learn (paused)

The learn app is paused. It stays merged and its tests stay green, but it gets no new features, and the menu does not offer it. `ready` and `explain` do not need it.

Open the **learn app** for one run folder: the chapters, five exercise kinds and a tutor. The design is [../docs/LEARN-APP.md](../docs/LEARN-APP.md). Start this sub-command only on an explicit request from the user. A tutor answer costs money on the learner's account. A control costs compute only.

Inputs: `R`, a run folder that `explain` made, and a local clone of the reviewed repo that holds the head commit.

## Steps

1. **Check the run folder.** Run `python3 $U/scripts/validate.py $R/trust-map.json`. Check that `$R/explainer.mdx` exists.
   - **Done when** `VALID` prints and the file exists. Else run `explain` first.
2. **Name the Artifacture checkout.** Set `UNDERSTANDO_VE_RUNTIME` to the checkout that the chapter MDX imports from. The first import line of `$R/chapters/01-*.mdx` names it.
   - **Done when** `$UNDERSTANDO_VE_RUNTIME/visual-explainer-mdx/components.tsx` exists.
3. **Start the app.** Run `$U/learn/learn.sh $R --repo <clone>`. For Function-Health/function-intelligence, `--repo` defaults to `~/dev/function-intelligence`. The script builds the binary and the UI only when they are missing, compiles the chapters when they are stale, and opens the browser.
   - **Done when** the terminal prints the `understando learn:` URL and the `scratch:` folder.
4. **Report.** Give the user the URL, and tell the user which account the tutor bills to: open **Setup doctor** in the app, or run `curl -s <url>/api/setup`.
   - **Done when** the user has the URL and the billing line of the default provider.
5. **Stop.** The user presses Ctrl+C in the terminal of step 3. The app removes its scratch clone and worktree.
   - **Done when** the terminal prints `scratch removed:`.

## Rules

- The learner's record goes to `$R/my-work/`. It stays out of git.
- Live tutor text and an explain-it-back grade are guess tier. A server run is fact tier. Neither one writes the trust map, so no verdict changes in the app.
- To test the app, run `$U/learn/e2e.sh`. It makes no model call.
