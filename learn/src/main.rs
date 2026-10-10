//! understando-learn: a local learning app for one understando run folder.
//!
//!     understando-learn <run-dir> --repo <git repo> [--port N] [--no-open] [--env-file FILE]
//!
//! It loads `<run-dir>/trust-map.json`, makes a private clone and one scratch worktree at the PR
//! head, serves the app on 127.0.0.1, and removes the scratch folder on exit.

mod actions;
mod agent;
mod doctor;
mod git;
mod grading;
mod mywork;
mod proc;
mod server;
mod trustmap;
mod tutor;

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use agent::CodexAuth;

const FI_REPO: &str = "function-health/function-intelligence";
const FI_ENV: &str = "/Users/clayton/dev/function-intelligence/.env";
const FI_ROOT: &str = "/Users/clayton/dev/function-intelligence";
const DEFAULT_PORT: u16 = 4190;

/// The paths and globs that the tutor shell must not read, and the planted files that prove it.
///
/// Denied: the user's checkout of the reviewed repo, each `.env*` under it and under the
/// function-intelligence checkout, the key file, and the secret folders in HOME. The canaries in
/// the scratch folder match the same kinds of rule (a `**/.env*` glob and a folder), so a probe
/// that reads them tests the layer without a read of a real secret.
fn deny_layer(repo: &Path, fi_env: &str, ws: &git::Workspace) -> (Vec<String>, Vec<agent::Probe>) {
    let r = repo.display().to_string();
    let canary = ws.root.join("canary");
    let canary_dir = ws.root.join("canary-dir");
    let note = "understando canary, not a secret\n";
    let _ = std::fs::create_dir_all(canary.join("deep"));
    let _ = std::fs::create_dir_all(&canary_dir);
    let _ = std::fs::write(canary.join(".env"), note);
    let _ = std::fs::write(canary.join("deep/.env.local"), note);
    let _ = std::fs::write(canary_dir.join("secret.txt"), note);
    let c = canary.display().to_string();
    let cd = canary_dir.display().to_string();
    let mut deny = vec![
        r.clone(),
        format!("{r}/**/.env*"),
        format!("{FI_ROOT}/**/.env*"),
        FI_ENV.to_string(),
        fi_env.to_string(),
        format!("{c}/**/.env*"),
        cd.clone(),
    ];
    deny.extend(home_paths(&[".codex", ".claude", ".ssh", ".aws", ".config/gh", ".netrc", "Library/Keychains", ".docker/config.json", ".gnupg", ".npmrc", ".pypirc", ".kube"]));
    deny.dedup();
    let cat = |p: String, ok: bool| agent::Probe { argv: vec!["cat".into(), p], expect_ok: ok };
    let mut probes = vec![
        cat(format!("{c}/.env"), false),
        cat(format!("{c}/deep/.env.local"), false),
        cat(format!("{cd}/secret.txt"), false),
        agent::Probe { argv: vec!["touch".into(), format!("{c}/write-probe")], expect_ok: false },
        cat(ws.worktree.join(".git").display().to_string(), true),
    ];
    for real in [fi_env.to_string(), format!("{r}/.env")] {
        if Path::new(&real).is_file() {
            probes.push(cat(real, false));
        }
    }
    (deny, probes)
}

struct Args {
    run_dir: PathBuf,
    repo: PathBuf,
    port: Option<u16>,
    open: bool,
    env_file: Option<PathBuf>,
}

fn usage() -> ! {
    eprintln!("usage: understando-learn <run-dir> --repo <git repo> [--port N] [--no-open] [--env-file FILE]");
    std::process::exit(2)
}

fn parse_args() -> Args {
    let mut it = std::env::args().skip(1);
    let mut run_dir = None;
    let mut repo = None;
    let mut port = std::env::var("UNDERSTANDO_LEARN_PORT").ok().and_then(|p| p.parse().ok());
    let mut open = true;
    let mut env_file = None;
    while let Some(a) = it.next() {
        match a.as_str() {
            "--repo" => repo = it.next().map(PathBuf::from),
            "--port" => port = it.next().and_then(|p| p.parse().ok()).or_else(|| usage()),
            "--no-open" => open = false,
            "--env-file" => env_file = it.next().map(PathBuf::from),
            "-h" | "--help" => usage(),
            _ if a.starts_with('-') => usage(),
            _ => run_dir = Some(PathBuf::from(a)),
        }
    }
    let (Some(run_dir), Some(repo)) = (run_dir, repo) else { usage() };
    Args { run_dir, repo, port, open, env_file }
}

fn canonical(p: &Path) -> PathBuf {
    p.canonicalize().unwrap_or_else(|_| p.to_path_buf())
}

async fn health_of(port: u16) -> Option<serde_json::Value> {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let mut s = tokio::time::timeout(std::time::Duration::from_millis(400), tokio::net::TcpStream::connect(("127.0.0.1", port))).await.ok()?.ok()?;
    let req = format!("GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    s.write_all(req.as_bytes()).await.ok()?;
    let mut buf = Vec::new();
    tokio::time::timeout(std::time::Duration::from_millis(800), s.read_to_end(&mut buf)).await.ok()?.ok()?;
    let text = String::from_utf8_lossy(&buf);
    let body = text.split("\r\n\r\n").nth(1)?;
    serde_json::from_str(body.trim()).ok()
}

fn open_browser(url: &str) {
    let program = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
    let _ = std::process::Command::new(program).arg(url).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).spawn();
}

fn home_paths(names: &[&str]) -> Vec<String> {
    let home = std::env::var("HOME").unwrap_or_default();
    names.iter().map(|n| format!("{home}/{n}")).collect()
}

#[tokio::main]
async fn main() {
    let args = parse_args();
    let run_dir = canonical(&args.run_dir);
    let repo = canonical(&args.repo);
    let map = match trustmap::TrustMap::load(&run_dir.join("trust-map.json")) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("understando-learn: {e}");
            std::process::exit(1);
        }
    };
    let run_id = run_dir.display().to_string();

    // Reuse a server that already serves this run folder.
    let candidates: Vec<u16> = match args.port {
        Some(p) => vec![p],
        None => (DEFAULT_PORT..DEFAULT_PORT + 100).collect(),
    };
    for &p in &candidates {
        if let Some(h) = health_of(p).await {
            if h.get("app").and_then(|v| v.as_str()) == Some("understando-learn") && h.get("run").and_then(|v| v.as_str()) == Some(run_id.as_str()) {
                let url = format!("http://127.0.0.1:{p}/");
                println!("This run folder is already open at {url}");
                if args.open {
                    open_browser(&url);
                }
                return;
            }
        }
    }
    let mut listener = None;
    for &p in &candidates {
        if let Ok(l) = tokio::net::TcpListener::bind(("127.0.0.1", p)).await {
            listener = Some((l, p));
            break;
        }
    }
    let Some((listener, port)) = listener else {
        eprintln!("understando-learn: no free port. Use --port with a free port.");
        std::process::exit(1);
    };

    git::sweep_stale(&std::env::temp_dir());
    let scratch = std::env::temp_dir().join(format!("understando-learn-{}-{}", std::process::id(), &uuid::Uuid::new_v4().to_string()[..8]));
    let ws = match git::Workspace::create(&repo, map.head(), &scratch) {
        Ok(w) => w,
        Err(e) => {
            let _ = std::fs::remove_dir_all(&scratch);
            eprintln!("understando-learn: {e}");
            std::process::exit(1);
        }
    };

    let api_key_repo = map.repo().to_ascii_lowercase() == FI_REPO;
    let codex_auth = if api_key_repo {
        let path = std::env::var("UNDERSTANDO_FI_ENV").map(PathBuf::from).unwrap_or_else(|_| PathBuf::from(FI_ENV));
        agent::read_env_key(&path).map(|key| CodexAuth::ApiKey { key, source: path.display().to_string() })
    } else {
        Ok(CodexAuth::OwnLogin)
    };
    let fi_env = std::env::var("UNDERSTANDO_FI_ENV").unwrap_or_else(|_| FI_ENV.to_string());
    let (deny_read, probes) = deny_layer(&repo, &fi_env, &ws);
    let (sandbox_ready, sandbox_detail) = doctor::os_sandbox(&ws.worktree).await;

    let origin = format!("http://127.0.0.1:{port}");
    let app = Arc::new(server::App {
        map,
        run_dir: run_dir.clone(),
        repo: repo.clone(),
        env_file: args.env_file.as_deref().map(canonical),
        mywork: mywork::MyWork::new(&run_dir),
        allowed_origins: HashSet::from([origin.clone(), format!("http://localhost:{port}")]),
        allowed_hosts: HashSet::from([format!("127.0.0.1:{port}"), format!("localhost:{port}")]),
        codex_auth,
        api_key_repo,
        deny_read,
        probes,
        codex_deny: Mutex::new(None),
        sandbox_ready,
        busy: Mutex::new(None),
        proposals: Mutex::new(HashMap::new()),
        doctor_cache: tokio::sync::Mutex::new(None),
        run_id,
        ws,
    });
    let _ = &app.repo;

    println!("understando learn: {origin}/");
    println!("run: {}", run_dir.display());
    println!("scratch: {}", app.ws.root.display());
    println!("worktree: {}", app.ws.worktree.display());
    println!("tutor shell: {}", if sandbox_ready { "on, in the OS sandbox" } else { sandbox_detail.as_str() });
    println!("Keep this terminal open. Press Ctrl+C to stop. The scratch folder is removed on exit.");

    // Prepare the worktree once, so the tutor finds a ready toolchain.
    {
        let app = app.clone();
        tokio::spawn(async move {
            if app.map.setup().is_empty() {
                return;
            }
            let Ok(slot) = (|| {
                let mut s = app.busy.lock().unwrap();
                if s.is_some() {
                    return Err(());
                }
                let (tx, _) = tokio::sync::watch::channel(false);
                *s = Some(("the worktree setup".to_string(), tx));
                Ok(())
            })() else { return };
            let _ = slot;
            for step in app.map.setup() {
                let argv: Vec<String> = step.get("argv").and_then(|a| a.as_array()).map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
                if argv.is_empty() {
                    break;
                }
                let cwd = step.get("cwd").and_then(|c| c.as_str()).and_then(|c| app.ws.inside(c).ok()).unwrap_or(app.ws.worktree.clone());
                let (_tx, rx) = tokio::sync::watch::channel(false);
                let out = proc::run(
                    proc::Spec { program: &argv[0], args: &argv[1..], cwd: &cwd, env: proc::clean_env(),
                                 timeout: std::time::Duration::from_secs(step.get("timeout_s").and_then(|t| t.as_u64()).unwrap_or(900)), output_cap: 4_000_000, stdin: None },
                    rx, |_| {}).await;
                if out.code != Some(0) {
                    eprintln!("setup step {argv:?} failed; graded runs repeat it");
                    break;
                }
            }
            *app.busy.lock().unwrap() = None;
            println!("worktree setup: done");
        });
    }

    // Check the Codex read-deny layer once, with no model request. A failure turns the Codex shell off.
    if sandbox_ready && proc::which("codex").is_some() {
        let app = app.clone();
        tokio::spawn(async move {
            let Ok(auth) = app.codex_auth.clone() else { return };
            if let Err(e) = agent::codex_deny_check(&auth, &app.ws.root, &app.ws.worktree, &app.deny_read, &app.probes).await {
                let reason = format!("{}: {e}", agent::DENY_CHECK_FAILED);
                eprintln!("{reason}");
                *app.codex_deny.lock().unwrap() = Some(reason);
            }
        });
    }

    if args.open {
        open_browser(&format!("{origin}/"));
    }

    let stop = Arc::new(tokio::sync::Notify::new());
    let shutdown_app = app.clone();
    let stop2 = stop.clone();
    let shutdown = async move {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).unwrap();
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {}
            _ = term.recv() => {}
        }
        server::cancel_active(&shutdown_app);
        stop2.notify_one();
    };
    let served = axum::serve(listener, server::router(app.clone())).with_graceful_shutdown(shutdown);
    // An open stream can hold the server; stop after a short grace period.
    let res = tokio::select! {
        r = served => r.map_err(|e| e.to_string()),
        _ = async { stop.notified().await; tokio::time::sleep(std::time::Duration::from_secs(3)).await; } => Ok(()),
    };
    // Wait briefly for a cancelled child to exit, then remove the scratch folder.
    for _ in 0..20 {
        if app.busy.lock().unwrap().is_none() {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(150)).await;
    }
    app.ws.remove();
    println!("scratch removed: {}", app.ws.root.display());
    if let Err(e) = res {
        eprintln!("understando-learn: {e}");
        std::process::exit(1);
    }
}
