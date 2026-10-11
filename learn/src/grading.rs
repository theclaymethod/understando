//! Fact-tier runs. The server resets the worktree, runs the setup steps, applies the recorded
//! edits and runs the recorded argv. Only these results grade an exercise. Nothing here writes
//! the trust map, so a live run never changes a verdict.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::{json, Value};
use tokio::sync::watch;

use crate::git::Workspace;
use crate::proc;
use crate::trustmap::{Graded, TrustMap};

const TAIL_LINES: usize = 40;

static SECRETS: std::sync::LazyLock<[regex::Regex; 3]> = std::sync::LazyLock::new(|| {
    [
        regex::Regex::new(r"sk-[A-Za-z0-9_-]{16,}").unwrap(),
        regex::Regex::new(r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[=:]\s*)\S+").unwrap(),
        regex::Regex::new(r"gh[pousr]_[A-Za-z0-9]{20,}").unwrap(),
    ]
});

pub fn redact(text: &str) -> String {
    let t = SECRETS[0].replace_all(text, "sk-REDACTED");
    let t = SECRETS[1].replace_all(&t, "${1}${2}REDACTED");
    SECRETS[2].replace_all(&t, "gh_REDACTED").into_owned()
}

pub fn tail(text: &str, worktree: &Path) -> String {
    let mut t = text.replace(&worktree.display().to_string(), "<worktree>");
    if let Some(home) = std::env::var_os("HOME") {
        t = t.replace(&home.to_string_lossy().to_string(), "~");
    }
    let lines: Vec<&str> = t.trim_end().lines().collect();
    redact(&lines[lines.len().saturating_sub(TAIL_LINES)..].join("\n"))
}

pub struct Ctx<'a> {
    pub map: &'a TrustMap,
    pub ws: &'a Workspace,
    pub env_file: Option<&'a Path>,
    pub cancel: watch::Receiver<bool>,
}

pub type Emit<'a> = &'a (dyn Fn(Value) + Send + Sync);

fn s<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(Value::as_str).unwrap_or("")
}

fn apply_edit(ws: &Workspace, edit: &Value) -> Result<(), String> {
    let rel = s(edit, "path");
    let path = ws.inside(rel)?;
    let op = s(edit, "op");
    let anchored = edit.get("symbol").is_some() || edit.get("match").is_some();
    if matches!(op, "delete-line" | "invert-condition" | "replace-with" | "drop-allowlist-row") || (op == "corrupt-byte" && anchored) {
        // An anchor op resolves in scripts/coderef.py, the same code that the probe runs.
        let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../scripts/coderef.py");
        let out = std::process::Command::new("python3")
            .arg("-I").arg(&script).arg("--apply-edit").arg(&path).arg(edit.to_string())
            .output().map_err(|e| format!("{rel}: {e}"))?;
        return if out.status.success() { Ok(()) } else { Err(format!("{rel}: {}", String::from_utf8_lossy(&out.stderr).trim())) };
    }
    match op {
        "delete-file" => std::fs::remove_file(&path).map_err(|e| format!("{rel}: {e}")),
        "corrupt-byte" => {
            let mut data = std::fs::read(&path).map_err(|e| format!("{rel}: {e}"))?;
            if data.is_empty() {
                return Err(format!("{rel} is empty"));
            }
            let off = edit.get("offset").and_then(Value::as_i64).unwrap_or((data.len() / 2) as i64);
            let off = if off < 0 { data.len() as i64 + off } else { off } as usize;
            let byte = data.get_mut(off).ok_or_else(|| format!("{rel}: offset {off} is out of range"))?;
            *byte ^= 0x01;
            std::fs::write(&path, data).map_err(|e| format!("{rel}: {e}"))
        }
        "append" => {
            let mut text = std::fs::read_to_string(&path).map_err(|e| format!("{rel}: {e}"))?;
            text.push_str(s(edit, "text"));
            std::fs::write(&path, text).map_err(|e| format!("{rel}: {e}"))
        }
        "replace" => {
            let text = std::fs::read_to_string(&path).map_err(|e| format!("{rel}: {e}"))?;
            let find = s(edit, "find");
            let want = edit.get("count").and_then(Value::as_u64).unwrap_or(1) as usize;
            let found = if find.is_empty() { 0 } else { text.matches(find).count() };
            if found != want {
                return Err(format!("{rel}: the find text occurs {found} times, expected {want}"));
            }
            std::fs::write(&path, text.replace(find, s(edit, "replace"))).map_err(|e| format!("{rel}: {e}"))
        }
        other => Err(format!("unknown edit op {other:?}")),
    }
}

struct Ran {
    code: Option<i32>,
    output: String,
    seconds: f64,
    stopped: bool,
}

async fn run_command(ctx: &Ctx<'_>, command: &Value, use_env_file: bool, emit: Emit<'_>) -> Result<Ran, String> {
    let argv: Vec<String> = command
        .get("argv")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect())
        .unwrap_or_default();
    if argv.is_empty() {
        return Err("the command has no argv".into());
    }
    let cwd_rel = command.get("cwd").and_then(Value::as_str).unwrap_or(".");
    let cwd: PathBuf = if cwd_rel == "." { ctx.ws.worktree.clone() } else { ctx.ws.inside(cwd_rel)? };
    let (program, args): (String, Vec<String>) = if use_env_file && command.get("env_file").and_then(Value::as_bool) == Some(true) {
        let file = ctx.env_file.ok_or("This verifier needs an env file. Start the app with --env-file <file>.")?;
        let mut a = vec!["-c".to_string(), r#"source "$0" && exec "$@""#.to_string(), file.display().to_string()];
        a.extend(argv);
        ("bash".into(), a)
    } else {
        (argv[0].clone(), argv[1..].to_vec())
    };
    let timeout = command.get("timeout_s").and_then(Value::as_u64).unwrap_or(900).clamp(1, 3600);
    let out = proc::run(
        proc::Spec {
            program: &program,
            args: &args,
            cwd: &cwd,
            env: proc::clean_env(),
            timeout: Duration::from_secs(timeout),
            output_cap: 4_000_000,
            stdin: None,
        },
        ctx.cancel.clone(),
        |line| emit(json!({"type": "output", "text": redact(line)})),
    )
    .await;
    Ok(Ran { code: out.code, output: out.output, seconds: out.seconds, stopped: out.cancelled })
}

fn classify(code: Option<i32>, command: &Value) -> &'static str {
    match code {
        Some(0) => "green",
        Some(c) => {
            let reds: Vec<i64> = command
                .get("red_exits")
                .and_then(Value::as_array)
                .map(|a| a.iter().filter_map(Value::as_i64).collect())
                .unwrap_or_else(|| vec![1]);
            if reds.contains(&(c as i64)) {
                "red"
            } else {
                "error"
            }
        }
        None => "error",
    }
}

async fn prepare(ctx: &Ctx<'_>, emit: Emit<'_>) -> Result<(), String> {
    emit(json!({"type": "status", "message": "Resetting the worktree to the PR head."}));
    ctx.ws.reset()?;
    for step in ctx.map.setup() {
        let label = step.get("argv").map(|a| a.to_string()).unwrap_or_default();
        emit(json!({"type": "status", "message": format!("Setup step: {label}")}));
        let ran = run_command(ctx, step, false, emit).await?;
        if ran.code != Some(0) {
            return Err(format!("setup {label} failed:\n{}", tail(&ran.output, &ctx.ws.worktree)));
        }
    }
    Ok(())
}

/// Leave the worktree at the head, ready for the tutor, after a graded run.
async fn restore(ctx: &Ctx<'_>, emit: Emit<'_>) {
    if ctx.ws.reset().is_ok() {
        let quiet = |_v: Value| {};
        for step in ctx.map.setup() {
            if run_command(ctx, step, false, &quiet).await.map(|r| r.code != Some(0)).unwrap_or(true) {
                break;
            }
        }
    }
    emit(json!({"type": "status", "message": "The worktree is back at the PR head."}));
}

fn recorded(v: Option<&Value>) -> Value {
    v.map(|r| json!({"status": r.get("status"), "exit": r.get("exit"), "seconds": r.get("seconds"), "ran_at": r.get("ran_at")}))
        .unwrap_or(Value::Null)
}

fn result_value(status: &str, ran: &Ran, matched: Option<bool>, ws: &Workspace) -> Value {
    json!({"status": status, "exit": ran.code, "seconds": ran.seconds, "matched": matched,
           "outputTail": tail(&ran.output, &ws.worktree), "stopped": ran.stopped})
}

/// Run one allowlisted plan. `test` is the learner's test file for close-gap.
pub async fn run(ctx: Ctx<'_>, plan: &Graded, test: Option<&str>, emit: Emit<'_>) -> Value {
    let out = run_inner(&ctx, plan, test, emit).await;
    restore(&ctx, emit).await;
    match out {
        Ok(v) => v,
        Err(e) => json!({"status": "error", "note": redact(&e)}),
    }
}

async fn run_inner(ctx: &Ctx<'_>, plan: &Graded, test: Option<&str>, emit: Emit<'_>) -> Result<Value, String> {
    let map = ctx.map;
    match plan {
        Graded::Verifier { verifier } => {
            let v = map.verifier(verifier).unwrap();
            let cmd = v.get("command").unwrap();
            prepare(ctx, emit).await?;
            emit(json!({"type": "status", "message": format!("Running verifier {verifier}.")}));
            let ran = run_command(ctx, cmd, true, emit).await?;
            let status = classify(ran.code, cmd);
            let mut r = result_value(status, &ran, None, ctx.ws);
            r["recorded"] = recorded(v.get("baseline"));
            Ok(r)
        }
        Graded::Control { control, verifier } => {
            let k = map.control(control).unwrap();
            let v = map.verifier(verifier).unwrap();
            let cmd = v.get("command").unwrap();
            prepare(ctx, emit).await?;
            emit(json!({"type": "status", "message": format!("Planting control {control}: {}", s(k, "description"))}));
            for edit in k.get("edits").and_then(Value::as_array).into_iter().flatten() {
                if let Err(e) = apply_edit(ctx.ws, edit) {
                    return Ok(json!({"status": "error", "note": format!("The control did not apply: {e}")}));
                }
            }
            emit(json!({"type": "status", "message": format!("Running verifier {verifier} on the planted bug.")}));
            let ran = run_command(ctx, cmd, true, emit).await?;
            let status = classify(ran.code, cmd);
            let matched = match (status, k.pointer("/expect/pattern").and_then(Value::as_str)) {
                ("red", Some(p)) => Some(regex::RegexBuilder::new(p).multi_line(true).build().map(|re| re.is_match(&ran.output)).unwrap_or(false)),
                _ => None,
            };
            let mut r = result_value(status, &ran, matched, ctx.ws);
            r["recorded"] = recorded(k.get("result"));
            r["cannotFail"] = json!(status == "green");
            Ok(r)
        }
        Graded::CloseGap { exercise } => {
            let x = map.exercise(exercise).unwrap();
            let cmd = x.get("command").unwrap();
            let test_path = s(x, "test_path");
            let content = test.ok_or("Write the test first.")?;
            // 1. At the head, the learner's test must pass.
            prepare(ctx, emit).await?;
            std::fs::write(ctx.ws.inside(test_path)?, content).map_err(|e| e.to_string())?;
            emit(json!({"type": "status", "message": "Running your test at the PR head. It must pass."}));
            let head_run = run_command(ctx, cmd, true, emit).await?;
            let head_status = classify(head_run.code, cmd);
            let head = result_value(head_status, &head_run, None, ctx.ws);
            if head_status != "green" {
                return Ok(json!({"status": "error", "passed": false, "head": head,
                    "note": "Your test does not pass on the code at the PR head. Fix the test first."}));
            }
            // 2. With the matching bug planted, the same test must fail.
            prepare(ctx, emit).await?;
            std::fs::write(ctx.ws.inside(test_path)?, content).map_err(|e| e.to_string())?;
            emit(json!({"type": "status", "message": format!("Planting the bug: {}", x.pointer("/bug/description").and_then(Value::as_str).unwrap_or(""))}));
            for edit in x.pointer("/bug/edits").and_then(Value::as_array).into_iter().flatten() {
                apply_edit(ctx.ws, edit).map_err(|e| format!("The bug did not apply: {e}"))?;
            }
            emit(json!({"type": "status", "message": "Running your test on the planted bug. It must fail."}));
            let bug_run = run_command(ctx, cmd, true, emit).await?;
            let bug_status = classify(bug_run.code, cmd);
            let matched = match (bug_status, x.pointer("/expect/pattern").and_then(Value::as_str)) {
                ("red", Some(p)) => Some(regex::Regex::new(p).map(|re| re.is_match(&bug_run.output)).unwrap_or(false)),
                _ => None,
            };
            let passed = bug_status == "red" && matched != Some(false);
            Ok(json!({"status": bug_status, "passed": passed, "head": head,
                      "bug": result_value(bug_status, &bug_run, matched, ctx.ws)}))
        }
    }
}
