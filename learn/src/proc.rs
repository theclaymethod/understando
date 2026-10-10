//! Child processes: one process group per run, a timeout, an output cap, and a group kill.

use std::collections::HashMap;
use std::path::Path;
use std::process::Stdio;
use std::time::{Duration, Instant};

use tokio::io::{AsyncBufReadExt, AsyncRead, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, watch};

/// Environment names that never reach a child process. Provider keys, agent
/// session markers and the common secret names.
const STRIP_EXACT: &[&str] = &[
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CODEX_THREAD_ID",
    "CODEX_TURN_ID",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_API_KEY_OP_REF",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
];

fn secret_like(name: &str) -> bool {
    let upper = name.to_ascii_uppercase();
    STRIP_EXACT.contains(&upper.as_str())
        || upper.ends_with("_API_KEY")
        || upper.ends_with("_TOKEN")
        || upper.ends_with("_SECRET")
        || upper.contains("PASSWORD")
        || upper.ends_with("_OP_REF")
}

/// The parent environment without provider keys and inherited secrets.
pub fn clean_env() -> HashMap<String, String> {
    std::env::vars()
        .filter(|(k, _)| !secret_like(k))
        .chain([("NO_COLOR".to_string(), "1".to_string())])
        .collect()
}

pub struct Spec<'a> {
    pub program: &'a str,
    pub args: &'a [String],
    pub cwd: &'a Path,
    pub env: HashMap<String, String>,
    pub timeout: Duration,
    pub output_cap: usize,
    pub stdin: Option<Vec<u8>>,
}

#[derive(Debug, Default, Clone)]
pub struct Outcome {
    pub code: Option<i32>,
    pub output: String,
    pub seconds: f64,
    pub timed_out: bool,
    pub cancelled: bool,
    pub overflow: bool,
    pub missing: bool,
}

fn spawn(spec: &Spec) -> std::io::Result<Child> {
    let mut cmd = Command::new(spec.program);
    cmd.args(spec.args)
        .current_dir(spec.cwd)
        .env_clear()
        .envs(&spec.env)
        .stdin(if spec.stdin.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    #[cfg(unix)]
    cmd.process_group(0);
    cmd.spawn()
}

pub fn kill_group(child: &Child, signal: i32) {
    #[cfg(unix)]
    if let Some(pid) = child.id() {
        // SAFETY: killpg only sends a signal to the group that this child leads.
        unsafe {
            libc::killpg(pid as i32, signal);
        }
    }
}

fn pump<R: AsyncRead + Unpin + Send + 'static>(reader: R, tx: mpsc::UnboundedSender<String>) {
    tokio::spawn(async move {
        let mut lines = BufReader::new(reader).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if tx.send(line).is_err() {
                break;
            }
        }
    });
}

/// Run a command to its end. `on_line` gets each output line as it arrives.
/// A true value on `cancel` kills the process group.
pub async fn run(
    spec: Spec<'_>,
    mut cancel: watch::Receiver<bool>,
    mut on_line: impl FnMut(&str),
) -> Outcome {
    let start = Instant::now();
    let mut outcome = Outcome::default();
    let mut child = match spawn(&spec) {
        Ok(c) => c,
        Err(e) => {
            outcome.missing = e.kind() == std::io::ErrorKind::NotFound;
            outcome.output = format!("[understando] could not start {}: {e}", spec.program);
            return outcome;
        }
    };
    if let (Some(data), Some(mut stdin)) = (spec.stdin.clone(), child.stdin.take()) {
        tokio::spawn(async move {
            use tokio::io::AsyncWriteExt;
            let _ = stdin.write_all(&data).await;
            let _ = stdin.shutdown().await;
        });
    }
    let (tx, mut rx) = mpsc::unbounded_channel();
    pump(child.stdout.take().unwrap(), tx.clone());
    pump(child.stderr.take().unwrap(), tx);
    let deadline = tokio::time::sleep(spec.timeout);
    tokio::pin!(deadline);
    let mut kill_reason: Option<&str> = None;
    loop {
        tokio::select! {
            line = rx.recv() => match line {
                Some(line) => {
                    if outcome.output.len() + line.len() + 1 > spec.output_cap {
                        outcome.overflow = true;
                        kill_reason.get_or_insert("output cap");
                        kill_group(&child, libc::SIGTERM);
                        continue;
                    }
                    on_line(&line);
                    outcome.output.push_str(&line);
                    outcome.output.push('\n');
                }
                None => break,
            },
            _ = &mut deadline, if kill_reason.is_none() => {
                outcome.timed_out = true;
                kill_reason = Some("timeout");
                kill_group(&child, libc::SIGTERM);
            }
            changed = cancel.changed(), if kill_reason.is_none() => {
                if changed.is_err() || *cancel.borrow() {
                    outcome.cancelled = true;
                    kill_reason = Some("cancel");
                    kill_group(&child, libc::SIGTERM);
                }
            }
        }
    }
    if kill_reason.is_some() {
        tokio::select! {
            _ = child.wait() => {}
            _ = tokio::time::sleep(Duration::from_millis(1500)) => {
                kill_group(&child, libc::SIGKILL);
            }
        }
    }
    let status = child.wait().await.ok();
    outcome.code = if kill_reason.is_some() { None } else { status.and_then(|s| s.code()) };
    if let Some(reason) = kill_reason {
        outcome.output.push_str(&format!("[understando] stopped: {reason}\n"));
    }
    outcome.seconds = (start.elapsed().as_secs_f64() * 100.0).round() / 100.0;
    outcome
}

/// A short, quiet run for probes such as `--version`.
pub async fn probe(program: &str, args: &[&str], cwd: &Path, env: HashMap<String, String>, timeout_ms: u64) -> Outcome {
    let args: Vec<String> = args.iter().map(|s| s.to_string()).collect();
    let (_tx, rx) = watch::channel(false);
    run(
        Spec { program, args: &args, cwd, env, timeout: Duration::from_millis(timeout_ms), output_cap: 512_000, stdin: None },
        rx,
        |_| {},
    )
    .await
}

/// Find a program on PATH, like `command -v`.
pub fn which(program: &str) -> Option<std::path::PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|d| d.join(program)).find(|p| {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            p.metadata().map(|m| m.is_file() && m.permissions().mode() & 0o111 != 0).unwrap_or(false)
        }
        #[cfg(not(unix))]
        p.is_file()
    })
}
