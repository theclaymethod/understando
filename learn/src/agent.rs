//! Headless agent calls: `claude -p` (stream-json) and `codex app-server` (JSON-RPC over stdio).
//!
//! Isolation for both providers:
//! - a clean environment: no provider keys, no agent session markers, no inherited secrets;
//! - no hooks, no MCP servers, no plugins, no setting sources, no session persistence;
//! - the tutor works in the scratch worktree only. Its shell runs inside the OS sandbox of the
//!   CLI: writes only inside the worktree, no network. When the sandbox cannot start, the shell
//!   is off (fail closed). The grader gets no tools at all.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;
use tokio::sync::{mpsc, watch};

use crate::proc;

pub const TURN_TIMEOUT: Duration = Duration::from_secs(300);
const OUTPUT_CAP: usize = 4_000_000;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Provider {
    Claude,
    Codex,
}

impl Provider {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "claude" => Some(Self::Claude),
            "codex" => Some(Self::Codex),
            _ => None,
        }
    }
    pub fn id(self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
        }
    }
}

/// How the Codex process gets its account.
#[derive(Clone)]
pub enum CodexAuth {
    /// The learner's own Codex login in the default CODEX_HOME.
    OwnLogin,
    /// An API key that the server reads from a file. Codex gets an empty CODEX_HOME, the
    /// ephemeral credential store and an `account/login/start` RPC. The key is in no env var.
    ApiKey { key: String, source: String },
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Role {
    /// The tutor. `shell` is true only when the OS sandbox is ready.
    Tutor { shell: bool },
    /// The grader of an explain-it-back answer: no tools, a JSON schema output.
    Grader,
}

pub struct Call {
    pub provider: Provider,
    pub role: Role,
    pub system: String,
    pub prompt: String,
    pub cwd: PathBuf,
    pub output_schema: Option<Value>,
    pub codex_auth: CodexAuth,
    /// Paths and globs that the sandboxed shell must not read: the user's checkout, `.env*`
    /// files and secret folders.
    pub deny_read: Vec<String>,
    /// Codex only: commands that check the read-deny layer before the turn starts.
    pub probes: Vec<Probe>,
}

/// One check of the deny layer: `argv` runs in the Codex sandbox through `command/exec`, which
/// sends no model request. `expect_ok` false means the command must fail (a denied read or write).
#[derive(Clone, Debug)]
pub struct Probe {
    pub argv: Vec<String>,
    pub expect_ok: bool,
}

/// The prefix of the error when the Codex deny check fails. The server then turns the shell off.
pub const DENY_CHECK_FAILED: &str = "The Codex read-deny check failed, so the Codex shell is off";

#[derive(Debug)]
pub enum Event {
    Delta(String),
    Tool { id: String, name: String, status: String, detail: String },
}

pub struct Answer {
    pub text: String,
    pub model: Option<String>,
    pub usage: Value,
}

fn clip(s: &str, n: usize) -> String {
    let t: String = s.chars().filter(|c| !c.is_control() || *c == '\n').take(n).collect();
    t
}

pub fn claude_settings(deny_read: &[String]) -> Value {
    json!({
        "disableAllHooks": true,
        "sandbox": {
            "enabled": true,
            "failIfUnavailable": true,
            "autoAllowBashIfSandboxed": true,
            "allowUnsandboxedCommands": false,
            "network": {"allowedDomains": []},
            "filesystem": {"denyRead": deny_read}
        }
    })
}

pub fn claude_args(call: &Call) -> Vec<String> {
    let mut a: Vec<String> = [
        "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--no-session-persistence", "--disable-slash-commands", "--no-chrome",
        "--setting-sources", "", "--strict-mcp-config", "--mcp-config", r#"{"mcpServers":{}}"#,
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    match call.role {
        Role::Tutor { shell: true } => {
            // Bash is allowed because the sandbox settings below wrap every command; dontAsk denies the rest.
            a.extend(["--restricted", "--tools", "Bash,Read,Grep,Glob,Edit,Write", "--allowedTools", "Bash,Read,Grep,Glob,Edit,Write"].map(String::from));
            a.push("--settings".into());
            a.push(claude_settings(&call.deny_read).to_string());
        }
        Role::Tutor { shell: false } => {
            a.extend(["--restricted", "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob"].map(String::from));
            a.push("--settings".into());
            a.push(json!({"disableAllHooks": true}).to_string());
        }
        Role::Grader => {
            a.extend(["--tools", ""].map(String::from));
            a.push("--settings".into());
            a.push(json!({"disableAllHooks": true}).to_string());
        }
    }
    a.extend(["--permission-mode", "dontAsk", "--permission-prompts", "none"].map(String::from));
    if let Some(schema) = &call.output_schema {
        a.push("--json-schema".into());
        a.push(schema.to_string());
    }
    if let Ok(m) = std::env::var("UNDERSTANDO_CLAUDE_MODEL") {
        if !m.is_empty() {
            a.push("--model".into());
            a.push(m);
        }
    }
    a.push("--system-prompt".into());
    a.push(call.system.clone());
    a
}

pub async fn run(call: Call, cancel: watch::Receiver<bool>, on_event: impl FnMut(Event) + Send) -> Result<Answer, String> {
    match call.provider {
        Provider::Claude => run_claude(call, cancel, on_event).await,
        Provider::Codex => run_codex(call, cancel, on_event).await,
    }
}

async fn run_claude(call: Call, cancel: watch::Receiver<bool>, mut on_event: impl FnMut(Event) + Send) -> Result<Answer, String> {
    let args = claude_args(&call);
    let mut text = String::new();
    let mut final_text = String::new();
    let mut failure = String::new();
    let mut model = None;
    let mut usage = Value::Null;
    let mut stderr_tail = String::new();
    let mut tools: HashMap<String, (String, String)> = HashMap::new();
    let out = proc::run(
        proc::Spec {
            program: "claude",
            args: &args,
            cwd: &call.cwd,
            env: proc::clean_env(),
            timeout: TURN_TIMEOUT,
            output_cap: OUTPUT_CAP,
            stdin: Some(call.prompt.clone().into_bytes()),
        },
        cancel,
        |line| {
            let Ok(e) = serde_json::from_str::<Value>(line) else {
                stderr_tail = clip(&format!("{stderr_tail}\n{line}"), 4000);
                return;
            };
            match e.get("type").and_then(Value::as_str) {
                Some("stream_event") => {
                    if e.pointer("/event/delta/type").and_then(Value::as_str) == Some("text_delta") {
                        if let Some(t) = e.pointer("/event/delta/text").and_then(Value::as_str) {
                            text.push_str(t);
                            on_event(Event::Delta(t.to_string()));
                        }
                    }
                }
                Some("assistant") => {
                    if model.is_none() {
                        model = e.pointer("/message/model").and_then(Value::as_str).map(String::from);
                    }
                    for b in e.pointer("/message/content").and_then(Value::as_array).into_iter().flatten() {
                        if b.get("type").and_then(Value::as_str) == Some("tool_use") {
                            let id = b.get("id").and_then(Value::as_str).unwrap_or("tool").to_string();
                            let name = b.get("name").and_then(Value::as_str).unwrap_or("tool").to_string();
                            let detail = b.get("input").map(|i| clip(&i.to_string(), 400)).unwrap_or_default();
                            tools.insert(id.clone(), (name.clone(), detail.clone()));
                            on_event(Event::Tool { id, name, status: "running".into(), detail });
                        }
                    }
                }
                Some("user") => {
                    for b in e.pointer("/message/content").and_then(Value::as_array).into_iter().flatten() {
                        if b.get("type").and_then(Value::as_str) == Some("tool_result") {
                            let id = b.get("tool_use_id").and_then(Value::as_str).unwrap_or("tool").to_string();
                            let (name, input) = tools.get(&id).cloned().unwrap_or_else(|| ("tool".into(), String::new()));
                            let err = b.get("is_error").and_then(Value::as_bool) == Some(true);
                            let out = b.get("content").map(|c| clip(&c.to_string(), 600)).unwrap_or_default();
                            let detail = format!("{input} -> {out}");
                            on_event(Event::Tool { id, name, status: if err { "failed" } else { "completed" }.into(), detail });
                        }
                    }
                }
                Some("result") => {
                    usage = e.get("usage").cloned().unwrap_or(Value::Null);
                    let is_error = e.get("is_error").and_then(Value::as_bool) == Some(true);
                    let subtype_ok = e.get("subtype").and_then(Value::as_str).map(|s| s == "success").unwrap_or(true);
                    if is_error || (call.output_schema.is_some() && !subtype_ok) {
                        failure = clip(e.get("result").and_then(Value::as_str).unwrap_or("Claude could not complete this turn."), 1200);
                    } else if call.output_schema.is_some() {
                        match e.get("structured_output") {
                            Some(v) if !v.is_null() => final_text = v.to_string(),
                            _ => failure = "Claude finished without valid structured output.".into(),
                        }
                    } else {
                        final_text = e.get("result").and_then(Value::as_str).unwrap_or("").to_string();
                    }
                }
                _ => {}
            }
        },
    )
    .await;
    if out.missing {
        return Err("The claude CLI was not found. Install Claude Code and sign in.".into());
    }
    if out.cancelled {
        return Err("Stopped.".into());
    }
    if out.timed_out {
        return Err("The tutor took too long, so ask a shorter question.".into());
    }
    if out.overflow {
        return Err("The tutor response is larger than the local limit.".into());
    }
    if !failure.is_empty() {
        return Err(failure);
    }
    if out.code != Some(0) {
        let auth = regex::Regex::new(r"(?i)not logged in|authentication|unauthorized|login required|401").unwrap();
        return Err(if auth.is_match(&stderr_tail) {
            "Sign in to Claude Code in your terminal (claude auth login), then try again.".into()
        } else {
            "Claude Code stopped before it answered. Check the sign-in and the model.".into()
        });
    }
    let text = if final_text.is_empty() { text } else { final_text };
    if text.trim().is_empty() {
        return Err("The tutor gave no answer, so ask again.".into());
    }
    Ok(Answer { text, model, usage })
}

// ---------------------------------------------------------------- Codex

pub fn codex_config_args(api_key_mode: bool) -> Vec<String> {
    let mut a: Vec<String> = Vec::new();
    let mut c = |kv: &str| {
        a.push("-c".into());
        a.push(kv.into());
    };
    c("project_doc_max_bytes=0");
    c(r#"approval_policy="never""#);
    c(r#"web_search="disabled""#);
    c("skills.include_instructions=false");
    c("skills.bundled.enabled=false");
    c("shell_environment_policy.ignore_default_excludes=false");
    c(r#"shell_environment_policy.exclude=["*KEY*","*TOKEN*","*SECRET*","*PASSWORD*","CODEX_*","OPENAI_*","ANTHROPIC_*"]"#);
    if api_key_mode {
        c(r#"cli_auth_credentials_store="ephemeral""#);
        c(r#"forced_login_method="api""#);
    }
    for f in [
        "apps", "plugins", "hooks", "plugin_hooks", "browser_use", "browser_use_external", "computer_use",
        "image_generation", "in_app_browser", "multi_agent", "multi_agent_v2", "memories", "code_mode_host", "js_repl",
    ] {
        c(&format!("features.{f}=false"));
    }
    a
}

pub struct CodexEnv {
    pub env: HashMap<String, String>,
    pub base_args: Vec<String>,
    pub home: Option<PathBuf>,
}

impl Drop for CodexEnv {
    fn drop(&mut self) {
        if let Some(h) = &self.home {
            let _ = std::fs::remove_dir_all(h);
        }
    }
}

pub fn codex_env(auth: &CodexAuth, scratch: &Path) -> Result<CodexEnv, String> {
    let mut env = proc::clean_env();
    env.insert("UNDERSTANDO_CHILD_PROCESS".into(), "1".into());
    let mut home = None;
    let api = matches!(auth, CodexAuth::ApiKey { .. });
    if api {
        let h = scratch.join(format!("codex-home-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&h).map_err(|e| e.to_string())?;
        env.insert("CODEX_HOME".into(), h.display().to_string());
        home = Some(h);
    }
    Ok(CodexEnv { env, base_args: codex_config_args(api), home })
}

/// Read the MCP inventory with the given args. The server list must parse, or isolation fails.
async fn mcp_inventory(env: &HashMap<String, String>, args: &[String], cwd: &Path) -> Result<Vec<Value>, String> {
    let mut full: Vec<String> = vec!["mcp".into(), "list".into(), "--json".into()];
    full.extend(args.iter().cloned());
    let refs: Vec<&str> = full.iter().map(String::as_str).collect();
    let out = proc::probe("codex", &refs, cwd, env.clone(), 15_000).await;
    if out.code != Some(0) {
        return Err(format!("codex mcp list failed: {}", clip(out.output.lines().last().unwrap_or(""), 300)));
    }
    let start = out.output.find('[').ok_or("codex mcp list printed no JSON")?;
    let v: Value = serde_json::from_str(out.output[start..].trim()).map_err(|_| "codex mcp list printed bad JSON".to_string())?;
    v.as_array().cloned().ok_or_else(|| "codex mcp list did not print a list".into())
}

static MCP_NAME: std::sync::LazyLock<regex::Regex> = std::sync::LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]+$").unwrap());

/// Turn off every configured MCP server, then check that the list shows each one off.
/// A URL server needs a URL in its override; a stdio server needs a command.
pub async fn codex_isolation(env: &HashMap<String, String>, base: &[String], cwd: &Path) -> Result<Vec<String>, String> {
    let servers = mcp_inventory(env, base, cwd).await?;
    let mut args = base.to_vec();
    for s in &servers {
        let name = s.get("name").and_then(Value::as_str).unwrap_or("");
        if !MCP_NAME.is_match(name) {
            return Err("an MCP server has a name that cannot be overridden".into());
        }
        let ty = s.pointer("/transport/type").and_then(Value::as_str).unwrap_or("stdio");
        args.push("-c".into());
        args.push(if ty == "stdio" {
            format!(r#"mcp_servers.{name}={{enabled=false,command="/usr/bin/false"}}"#)
        } else {
            format!(r#"mcp_servers.{name}={{enabled=false,url="http://127.0.0.1:9/"}}"#)
        });
    }
    let after = mcp_inventory(env, &args, cwd).await?;
    if after.len() != servers.len() || after.iter().any(|s| s.get("enabled").and_then(Value::as_bool) != Some(false)) {
        return Err("an MCP server is still on after the override".into());
    }
    Ok(args)
}

/// The Codex permission profile for a tutor with a shell. It extends `:read-only`, so the shell
/// has no network and no write outside the worktree, and it denies reads of each `deny` entry.
/// Codex applies it in its own seatbelt: a second `sandbox-exec` cannot nest around Codex's.
pub fn codex_profile_args(worktree: &Path, deny: &[String]) -> Vec<String> {
    let q = |s: &str| serde_json::to_string(s).unwrap();
    let mut fs = vec![format!("{}=\"write\"", q(&worktree.display().to_string()))];
    fs.extend(deny.iter().map(|d| format!("{}=\"deny\"", q(d))));
    vec![
        "-c".into(),
        format!("permissions.learn={{extends=\":read-only\", filesystem={{{}}}}}", fs.join(", ")),
        "-c".into(),
        r#"default_permissions="learn""#.into(),
    ]
}

pub fn codex_sandbox_policy(worktree: &Path, shell: bool) -> Value {
    if shell {
        json!({"type": "workspaceWrite", "writableRoots": [worktree.display().to_string()], "networkAccess": false,
               "excludeTmpdirEnvVar": true, "excludeSlashTmp": true})
    } else {
        json!({"type": "readOnly", "networkAccess": false})
    }
}

async fn run_codex(call: Call, mut cancel: watch::Receiver<bool>, mut on_event: impl FnMut(Event) + Send) -> Result<Answer, String> {
    let scratch = call.cwd.parent().map(Path::to_path_buf).unwrap_or_else(std::env::temp_dir);
    let cenv = codex_env(&call.codex_auth, &scratch)?;
    let args = codex_isolation(&cenv.env, &cenv.base_args, &call.cwd)
        .await
        .map_err(|e| format!("Codex tool isolation could not be verified: {e}"))?;
    let shell = matches!(call.role, Role::Tutor { shell: true });
    let mut full = vec!["app-server".to_string(), "--stdio".to_string()];
    full.extend(args);
    if shell {
        full.extend(codex_profile_args(&call.cwd, &call.deny_read));
    } else {
        full.extend(["-c", "features.shell_tool=false", "-c", "features.unified_exec=false"].map(String::from));
    }
    let mut cmd = Command::new("codex");
    cmd.args(&full)
        .current_dir(&call.cwd)
        .env_clear()
        .envs(&cenv.env)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    #[cfg(unix)]
    cmd.process_group(0);
    let mut child = cmd.spawn().map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            "The codex CLI was not found. Install Codex.".to_string()
        } else {
            format!("Codex did not start: {e}")
        }
    })?;
    let mut stdin = child.stdin.take().unwrap();
    let mut lines = BufReader::new(child.stdout.take().unwrap()).lines();
    let stderr = child.stderr.take().unwrap();
    tokio::spawn(async move {
        let mut l = BufReader::new(stderr).lines();
        while let Ok(Some(_)) = l.next_line().await {}
    });
    let (wtx, mut wrx) = mpsc::unbounded_channel::<String>();
    tokio::spawn(async move {
        while let Some(line) = wrx.recv().await {
            if stdin.write_all(line.as_bytes()).await.is_err() || stdin.write_all(b"\n").await.is_err() {
                break;
            }
            let _ = stdin.flush().await;
        }
    });
    let send = |id: u64, method: &str, params: Value| {
        let _ = wtx.send(json!({"id": id, "method": method, "params": params}).to_string());
    };

    // Request ids: 1 initialize, 2 login, 3 model/list, 4 thread/start, 5 turn/start.
    send(1, "initialize", json!({"clientInfo": {"name": "understando-learn", "title": "understando learn", "version": env!("CARGO_PKG_VERSION")}}));
    let mut text = String::new();
    let mut final_text = String::new();
    let mut failure = String::new();
    let mut model: Option<String> = std::env::var("UNDERSTANDO_CODEX_MODEL").ok().filter(|m| !m.is_empty());
    let mut usage = Value::Null;
    let mut thread_id = String::new();
    let mut turn_id = String::new();
    let mut done = false;
    let mut bytes = 0usize;
    let deadline = tokio::time::sleep(TURN_TIMEOUT);
    tokio::pin!(deadline);
    let worktree = call.cwd.display().to_string();

    // With a shell, the permission profile is the sandbox, so no sandbox field may override it.
    let thread_start = |model: &Option<String>| {
        let mut p = json!({"cwd": worktree, "ephemeral": true, "approvalPolicy": "never",
               "baseInstructions": call.system, "developerInstructions": call.system, "model": model,
               "config": {"web_search": "disabled", "project_doc_max_bytes": 0}});
        if !shell { p["sandbox"] = json!("read-only"); }
        p
    };
    let probe = |i: usize| {
        let pr = &call.probes[i];
        json!({"command": pr.argv, "cwd": worktree, "timeoutMs": 10_000})
    };
    let mut next_probe = 0usize;

    while !done {
        tokio::select! {
            line = lines.next_line() => {
                let Ok(Some(line)) = line else { break };
                bytes += line.len();
                if bytes > OUTPUT_CAP { failure = "The tutor response is larger than the local limit.".into(); break; }
                let Ok(e) = serde_json::from_str::<Value>(&line) else { continue };
                // A server request (an approval). The policy is never, so decline any that come.
                if e.get("method").is_some() && e.get("id").is_some() {
                    let _ = wtx.send(json!({"id": e["id"], "error": {"code": -32000, "message": "declined by understando"}}).to_string());
                    continue;
                }
                if let Some(id) = e.get("id").and_then(Value::as_u64) {
                    if let Some(err) = e.get("error") {
                        failure = clip(err.get("message").and_then(Value::as_str).unwrap_or("Codex app server request failed."), 600);
                        break;
                    }
                    let r = &e["result"];
                    match id {
                        1 | 100.. => {
                            if id == 1 {
                                let _ = wtx.send(json!({"method": "initialized", "params": {}}).to_string());
                            } else {
                                let pr = &call.probes[(id - 100) as usize];
                                let ok = r.get("exitCode").and_then(Value::as_i64) == Some(0);
                                if ok != pr.expect_ok {
                                    failure = format!("{DENY_CHECK_FAILED}: `{}` {}.", pr.argv.join(" "),
                                        if pr.expect_ok { "did not run" } else { "was not denied" });
                                    break;
                                }
                            }
                            if shell && next_probe < call.probes.len() {
                                send(100 + next_probe as u64, "command/exec", probe(next_probe));
                                next_probe += 1;
                                continue;
                            }
                            if shell && call.probes.is_empty() {
                                failure = format!("{DENY_CHECK_FAILED}: no check was given.");
                                break;
                            }
                            match &call.codex_auth {
                                CodexAuth::ApiKey { key, .. } => send(2, "account/login/start", json!({"type": "apiKey", "apiKey": key})),
                                CodexAuth::OwnLogin => {
                                    if model.is_some() { send(4, "thread/start", thread_start(&model)); }
                                    else { send(3, "model/list", json!({"limit": 100, "includeHidden": false})); }
                                }
                            }
                        }
                        2 => {
                            if model.is_some() { send(4, "thread/start", thread_start(&model)); }
                            else { send(3, "model/list", json!({"limit": 100, "includeHidden": false})); }
                        }
                        3 => {
                            let list = r.get("data").and_then(Value::as_array).cloned().unwrap_or_default();
                            model = list.iter().find(|m| m.get("isDefault").and_then(Value::as_bool) == Some(true))
                                .or(list.first()).and_then(|m| m.get("model")).and_then(Value::as_str).map(String::from);
                            send(4, "thread/start", thread_start(&model));
                        }
                        4 => {
                            thread_id = r.pointer("/thread/id").and_then(Value::as_str).unwrap_or("").to_string();
                            if let Some(m) = r.get("model").and_then(Value::as_str) { model = Some(m.to_string()); }
                            if thread_id.is_empty() { failure = "Codex did not start a thread.".into(); break; }
                            let sb = &r["sandbox"];
                            if shell && (sb.get("type").and_then(Value::as_str) == Some("dangerFullAccess") || sb.get("networkAccess").and_then(Value::as_bool) == Some(true)) {
                                failure = format!("{DENY_CHECK_FAILED}: the thread sandbox is {sb}.");
                                break;
                            }
                            let mut p = json!({"threadId": thread_id, "input": [{"type": "text", "text": call.prompt}], "approvalPolicy": "never"});
                            if !shell { p["sandboxPolicy"] = codex_sandbox_policy(&call.cwd, false); }
                            if let Some(s) = &call.output_schema { p["outputSchema"] = s.clone(); }
                            send(5, "turn/start", p);
                        }
                        5 => {
                            turn_id = r.pointer("/turn/id").and_then(Value::as_str).unwrap_or("").to_string();
                            if turn_id.is_empty() { failure = "Codex did not start a turn.".into(); break; }
                        }
                        _ => {}
                    }
                    continue;
                }
                let method = e.get("method").and_then(Value::as_str).unwrap_or("");
                let p = &e["params"];
                let ours = p.get("turnId").and_then(Value::as_str) == Some(turn_id.as_str()) && !turn_id.is_empty();
                match method {
                    "item/agentMessage/delta" if ours => {
                        if let Some(d) = p.get("delta").and_then(Value::as_str) { text.push_str(d); on_event(Event::Delta(d.to_string())); }
                    }
                    "item/started" | "item/completed" if ours => {
                        let item = &p["item"];
                        let ty = item.get("type").and_then(Value::as_str).unwrap_or("");
                        if ty == "agentMessage" && method == "item/completed" {
                            if let Some(t) = item.get("text").and_then(Value::as_str) { final_text = t.to_string(); }
                        } else if ty == "commandExecution" || ty == "fileChange" || ty == "mcpToolCall" {
                            let id = item.get("id").and_then(Value::as_str).unwrap_or("tool").to_string();
                            let name = if ty == "commandExecution" { "shell" } else if ty == "fileChange" { "edit" } else { "mcp" }.to_string();
                            let mut detail = item.get("command").map(|c| clip(&c.to_string(), 400)).unwrap_or_default();
                            if let Some(out) = item.get("aggregatedOutput").and_then(Value::as_str) {
                                detail = format!("{detail} -> {}", clip(out, 600));
                            }
                            let status = if method == "item/started" { "running".to_string() } else {
                                match item.get("status").and_then(Value::as_str) { Some("failed") | Some("declined") => "failed".into(), _ => "completed".into() }
                            };
                            on_event(Event::Tool { id, name, status, detail });
                        }
                    }
                    "thread/tokenUsage/updated" => { usage = p.get("tokenUsage").cloned().unwrap_or(Value::Null); }
                    "error" if ours => { failure = clip(p.pointer("/error/message").and_then(Value::as_str).unwrap_or("Codex could not complete this turn."), 1200); }
                    "turn/completed" if p.pointer("/turn/id").and_then(Value::as_str) == Some(turn_id.as_str()) => {
                        let status = p.pointer("/turn/status").and_then(Value::as_str).unwrap_or("");
                        if status != "completed" && failure.is_empty() {
                            failure = p.pointer("/turn/error/message").and_then(Value::as_str).map(|m| clip(m, 1200))
                                .unwrap_or_else(|| "Codex could not complete this turn.".into());
                        }
                        done = true;
                    }
                    _ => {}
                }
            }
            _ = &mut deadline => { failure = "The tutor took too long, so ask a shorter question.".into(); break; }
            ch = cancel.changed() => { if ch.is_err() || *cancel.borrow() { failure = "Stopped.".into(); break; } }
        }
    }
    drop(wtx);
    proc::kill_group(&child, libc::SIGTERM);
    tokio::select! {
        _ = child.wait() => {}
        _ = tokio::time::sleep(Duration::from_millis(1500)) => { proc::kill_group(&child, libc::SIGKILL); let _ = child.wait().await; }
    }
    if !failure.is_empty() {
        return Err(failure);
    }
    if !done {
        return Err("Codex stopped before it answered. Check the Codex sign-in or the API key.".into());
    }
    let text = if final_text.is_empty() { text } else { final_text };
    if text.trim().is_empty() {
        return Err("The tutor gave no answer, so ask again.".into());
    }
    let _ = thread_id;
    Ok(Answer { text, model, usage })
}

/// Read OPENAI_API_KEY from a dotenv file. The value never goes into a log or a response.
pub fn read_env_key(path: &Path) -> Result<String, String> {
    let text = std::fs::read_to_string(path).map_err(|_| format!("Could not read {}.", path.display()))?;
    for line in text.lines() {
        let l = line.trim();
        let l = l.strip_prefix("export ").unwrap_or(l);
        if let Some(v) = l.strip_prefix("OPENAI_API_KEY=") {
            let v = v.trim().trim_matches('"').trim_matches('\'');
            if !v.is_empty() {
                return Ok(v.to_string());
            }
        }
    }
    Err(format!("{} has no OPENAI_API_KEY.", path.display()))
}

/// Run the deny probes in a fresh `codex app-server` with the tutor's profile, and no model
/// request. The doctor and the server start use it. Ok means each probe gave the expected result.
pub async fn codex_deny_check(auth: &CodexAuth, scratch: &Path, worktree: &Path, deny: &[String], probes: &[Probe]) -> Result<(), String> {
    if probes.is_empty() {
        return Err("no check was given".into());
    }
    let cenv = codex_env(auth, scratch)?;
    let mut args = codex_isolation(&cenv.env, &cenv.base_args, worktree).await?;
    args.extend(codex_profile_args(worktree, deny));
    let mut full = vec!["app-server".to_string(), "--stdio".to_string()];
    full.extend(args);
    let mut child = Command::new("codex")
        .args(&full)
        .current_dir(worktree)
        .env_clear()
        .envs(&cenv.env)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("codex app-server did not start: {e}"))?;
    let mut stdin = child.stdin.take().unwrap();
    let mut lines = BufReader::new(child.stdout.take().unwrap()).lines();
    let msg = |v: Value| format!("{v}\n");
    let wt = worktree.display().to_string();
    let result = tokio::time::timeout(Duration::from_secs(30), async {
        stdin
            .write_all(msg(json!({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "understando-check", "title": "check", "version": "1"}}})).as_bytes())
            .await
            .map_err(|e| e.to_string())?;
        let mut next = 0usize;
        while let Ok(Some(line)) = lines.next_line().await {
            let Ok(v) = serde_json::from_str::<Value>(&line) else { continue };
            let Some(id) = v.get("id").and_then(Value::as_u64) else { continue };
            if v.get("method").is_some() {
                continue;
            }
            if let Some(e) = v.get("error") {
                return Err(format!("command/exec failed: {}", e.get("message").and_then(Value::as_str).unwrap_or("")));
            }
            if id == 1 {
                let _ = stdin.write_all(msg(json!({"method": "initialized", "params": {}})).as_bytes()).await;
            } else {
                let pr = &probes[(id - 100) as usize];
                let ok = v.pointer("/result/exitCode").and_then(Value::as_i64) == Some(0);
                if ok != pr.expect_ok {
                    return Err(format!("`{}` {}", pr.argv.join(" "), if pr.expect_ok { "did not run" } else { "was not denied" }));
                }
            }
            if next == probes.len() {
                return Ok(());
            }
            let p = json!({"id": 100 + next as u64, "method": "command/exec", "params": {"command": probes[next].argv, "cwd": wt, "timeoutMs": 10_000}});
            let _ = stdin.write_all(msg(p).as_bytes()).await;
            next += 1;
        }
        Err("codex app-server closed before the check finished".to_string())
    })
    .await
    .unwrap_or_else(|_| Err("the check took more than 30 s".into()));
    let _ = child.kill().await;
    result
}
