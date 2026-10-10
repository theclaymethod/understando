//! The setup doctor. It sends no model request.

use std::path::Path;
use std::process::Stdio;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;

use crate::agent::{self, CodexAuth};
use crate::proc;

fn check(id: &str, label: &str, required: bool, ready: bool, detail: String) -> Value {
    json!({"id": id, "label": label, "required": required, "status": if ready { "ready" } else { "needs-action" }, "detail": detail})
}

fn first_line(s: &str) -> String {
    s.lines().map(str::trim).find(|l| !l.is_empty()).unwrap_or("").chars().take(200).collect()
}

/// Can the OS sandbox that Claude Code and Codex use start here?
pub async fn os_sandbox(cwd: &Path) -> (bool, String) {
    if cfg!(target_os = "macos") {
        let out = proc::probe("/usr/bin/sandbox-exec", &["-p", "(version 1)(allow default)", "/usr/bin/true"], cwd, proc::clean_env(), 5000).await;
        if out.code == Some(0) {
            (true, "macOS Seatbelt (sandbox-exec) works.".into())
        } else {
            (false, "macOS sandbox-exec did not run. The tutor shell is off.".into())
        }
    } else if cfg!(target_os = "linux") {
        let bwrap = proc::which("bwrap").is_some();
        let socat = proc::which("socat").is_some();
        if bwrap && socat {
            (true, "bubblewrap and socat are on PATH.".into())
        } else {
            (false, "Install bubblewrap and socat for the sandbox. The tutor shell is off.".into())
        }
    } else {
        (false, "No supported OS sandbox on this platform. The tutor shell is off.".into())
    }
}

/// The default Codex model, from `model/list`. That RPC sends no model request.
pub async fn codex_default_model(cenv: &agent::CodexEnv, args: &[String], cwd: &Path) -> Option<String> {
    let mut full = vec!["app-server".to_string(), "--stdio".to_string()];
    full.extend(args.iter().cloned());
    let mut child = Command::new("codex")
        .args(&full)
        .current_dir(cwd)
        .env_clear()
        .envs(&cenv.env)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true)
        .spawn()
        .ok()?;
    let mut stdin = child.stdin.take()?;
    let mut lines = BufReader::new(child.stdout.take()?).lines();
    let msg = |v: Value| format!("{v}\n");
    stdin
        .write_all(msg(json!({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "understando-doctor", "title": "doctor", "version": "1"}}})).as_bytes())
        .await
        .ok()?;
    let result = tokio::time::timeout(Duration::from_secs(20), async {
        while let Ok(Some(line)) = lines.next_line().await {
            let Ok(v) = serde_json::from_str::<Value>(&line) else { continue };
            match v.get("id").and_then(Value::as_u64) {
                Some(1) => {
                    let _ = stdin.write_all(msg(json!({"method": "initialized", "params": {}})).as_bytes()).await;
                    let _ = stdin.write_all(msg(json!({"id": 2, "method": "model/list", "params": {"limit": 100, "includeHidden": false}})).as_bytes()).await;
                }
                Some(2) => {
                    let list = v.pointer("/result/data").and_then(Value::as_array).cloned().unwrap_or_default();
                    return list
                        .iter()
                        .find(|m| m.get("isDefault").and_then(Value::as_bool) == Some(true))
                        .or(list.first())
                        .and_then(|m| m.get("model"))
                        .and_then(Value::as_str)
                        .map(String::from);
                }
                _ => {}
            }
        }
        None
    })
    .await
    .ok()
    .flatten();
    let _ = child.kill().await;
    result
}

pub struct DoctorInput<'a> {
    pub cwd: &'a Path,
    pub scratch: &'a Path,
    pub codex_auth: Result<CodexAuth, String>,
    pub api_key_repo: bool,
    pub worktree_ready: bool,
}

pub async fn run(input: DoctorInput<'_>) -> Value {
    let cwd = input.cwd;
    let env = proc::clean_env();
    let mut checks = Vec::new();

    let git = proc::probe("git", &["--version"], cwd, env.clone(), 5000).await;
    checks.push(check("git", "git", true, git.code == Some(0), first_line(&git.output)));
    checks.push(check(
        "worktree",
        "Scratch worktree",
        true,
        input.worktree_ready,
        if input.worktree_ready { "The scratch worktree is at the PR head.".into() } else { "The scratch worktree is not ready.".into() },
    ));
    let (sandbox_ready, sandbox_detail) = os_sandbox(cwd).await;
    checks.push(check("sandbox", "OS sandbox for the tutor shell", false, sandbox_ready, sandbox_detail.clone()));

    // Claude Code
    let cv = proc::probe("claude", &["--version"], cwd, env.clone(), 8000).await;
    let claude_installed = cv.code == Some(0);
    let mut claude_ready = false;
    let mut claude_billing = String::from("Not signed in.");
    let mut claude_detail = "Install Claude Code: https://code.claude.com/docs/en/setup".to_string();
    if claude_installed {
        let auth = proc::probe("claude", &["auth", "status", "--json"], cwd, env.clone(), 8000).await;
        let parsed: Value = auth.output.find('{').and_then(|i| serde_json::from_str(auth.output[i..].trim()).ok()).unwrap_or(Value::Null);
        let logged = parsed.get("loggedIn").and_then(Value::as_bool) == Some(true);
        let help = proc::probe("claude", &["--help"], cwd, env.clone(), 8000).await;
        let restricted = help.output.contains("--restricted");
        claude_ready = logged && restricted;
        let method = parsed.get("authMethod").and_then(Value::as_str).unwrap_or("unknown");
        let plan = parsed.get("subscriptionType").and_then(Value::as_str).unwrap_or("");
        claude_billing = if logged {
            format!("Your signed-in Claude account ({method}{}). No API key: the server strips ANTHROPIC_API_KEY.", if plan.is_empty() { String::new() } else { format!(", {plan}") })
        } else {
            "Not signed in.".into()
        };
        claude_detail = if !logged {
            "Run claude auth login in your terminal, then check again.".into()
        } else if !restricted {
            "This Claude Code has no --restricted flag. Update Claude Code.".into()
        } else {
            format!("Signed in. {}", if sandbox_ready { "The shell runs in the OS sandbox." } else { "The shell is off: the OS sandbox is not ready." })
        };
    }
    checks.push(json!({"id": "claude", "label": "Claude Code", "required": false, "status": if claude_ready { "ready" } else { "needs-action" },
        "detail": claude_detail, "version": first_line(&cv.output)}));

    // Codex
    let xv = proc::probe("codex", &["--version"], cwd, env.clone(), 8000).await;
    let codex_installed = xv.code == Some(0);
    let mut codex_ready = false;
    let mut codex_billing = String::from("Not available.");
    let mut codex_detail = "Install Codex: https://developers.openai.com/codex/cli/".to_string();
    let mut codex_model = Value::Null;
    let mut isolation_detail = String::from("Not checked.");
    if codex_installed {
        match &input.codex_auth {
            Err(e) => {
                codex_detail = e.clone();
                codex_billing = "No key.".into();
            }
            Ok(auth) => {
                let auth_ok;
                match auth {
                    CodexAuth::ApiKey { source, .. } => {
                        auth_ok = true;
                        codex_billing = format!("The OpenAI API key in {source} (API billing). Empty CODEX_HOME, no keychain, no ChatGPT login.");
                    }
                    CodexAuth::OwnLogin => {
                        let st = proc::probe("codex", &["login", "status"], cwd, env.clone(), 8000).await;
                        auth_ok = st.code == Some(0);
                        codex_billing = if auth_ok { format!("Your Codex login: {}", first_line(&st.output)) } else { "Not signed in.".into() };
                    }
                }
                match agent::codex_env(auth, input.scratch) {
                    Ok(cenv) => match agent::codex_isolation(&cenv.env, &cenv.base_args, cwd).await {
                        Ok(args) => {
                            isolation_detail = "Every MCP server, plugin, hook, browser, multi-agent, memory and web-search feature is off.".into();
                            codex_model = codex_default_model(&cenv, &args, cwd).await.map(Value::from).unwrap_or(Value::Null);
                            codex_ready = auth_ok;
                            codex_detail = if !auth_ok {
                                "Run codex login in your terminal, then check again.".into()
                            } else {
                                format!("Ready. {}", if sandbox_ready { "The shell runs in the workspace-write sandbox, with no network." } else { "The shell is read-only: the OS sandbox is not ready." })
                            };
                        }
                        Err(e) => {
                            isolation_detail = format!("Isolation failed: {e}");
                            codex_detail = isolation_detail.clone();
                        }
                    },
                    Err(e) => codex_detail = e,
                }
            }
        }
    }
    let _ = input.api_key_repo;
    checks.push(json!({"id": "codex", "label": "Codex", "required": false, "status": if codex_ready { "ready" } else { "needs-action" },
        "detail": codex_detail, "version": first_line(&xv.output)}));
    checks.push(check("codex-isolation", "Codex tool isolation", false, isolation_detail.starts_with("Every"), isolation_detail));

    let default = if claude_ready { "claude" } else if codex_ready { "codex" } else { "claude" };
    let tutor_ready = claude_ready || codex_ready;
    checks.push(check("tutor", "A tutor provider", true, tutor_ready, if tutor_ready { format!("The default tutor is {default}.") } else { "Sign in to Claude Code or Codex.".into() }));
    let required_ready = checks.iter().filter(|c| c["required"] == json!(true)).all(|c| c["status"] == "ready");
    json!({
        "ready": required_ready,
        "checkedAt": now(),
        "defaultProvider": default,
        "sandbox": {"ready": sandbox_ready, "detail": sandbox_detail},
        "providers": [
            {"id": "claude", "label": "Claude Code", "installed": claude_installed, "ready": claude_ready, "billing": claude_billing,
             "model": std::env::var("UNDERSTANDO_CLAUDE_MODEL").ok().filter(|m| !m.is_empty()).map(Value::from).unwrap_or(json!("the CLI default")),
             "shell": claude_ready && sandbox_ready},
            {"id": "codex", "label": "Codex", "installed": codex_installed, "ready": codex_ready, "billing": codex_billing,
             "model": std::env::var("UNDERSTANDO_CODEX_MODEL").ok().filter(|m| !m.is_empty()).map(Value::from).unwrap_or(codex_model),
             "shell": codex_ready && sandbox_ready}
        ],
        "checks": checks
    })
}

pub fn now() -> String {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    // Civil date from days since the epoch (Howard Hinnant's algorithm).
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3600, (rem / 60) % 60, rem % 60)
}
