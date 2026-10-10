//! HTTP: 127.0.0.1 only, Host/Origin/sec-fetch-site guards, JSON and NDJSON routes, embedded UI.

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Instant;

use axum::body::Body;
use axum::extract::{Query, Request, State};
use axum::http::{header, HeaderMap, HeaderValue, Method, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use rust_embed::RustEmbed;
use serde_json::{json, Value};
use tokio::sync::{mpsc, watch};
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::StreamExt;

use crate::actions::{self, Piece, TagStream};
use crate::agent::{self, CodexAuth, Provider, Role};
use crate::doctor;
use crate::git::{self, Workspace};
use crate::grading;
use crate::mywork::MyWork;
use crate::trustmap::{self, Graded, TrustMap};
use crate::tutor;

#[derive(RustEmbed)]
#[folder = "web/dist/"]
struct Assets;

pub struct App {
    pub map: TrustMap,
    pub run_dir: PathBuf,
    pub repo: PathBuf,
    pub ws: Workspace,
    pub env_file: Option<PathBuf>,
    pub mywork: MyWork,
    pub allowed_origins: HashSet<String>,
    pub allowed_hosts: HashSet<String>,
    pub codex_auth: Result<CodexAuth, String>,
    pub api_key_repo: bool,
    pub deny_read: Vec<String>,
    pub sandbox_ready: bool,
    pub busy: Mutex<Option<(String, watch::Sender<bool>)>>,
    pub proposals: Mutex<HashMap<String, (String, String)>>,
    pub doctor_cache: tokio::sync::Mutex<Option<(Instant, Value)>>,
    pub run_id: String,
}

type Shared = Arc<App>;

/// Holds the single activity slot: one tutor turn or one graded run at a time.
struct Busy {
    app: Shared,
}
impl Drop for Busy {
    fn drop(&mut self) {
        *self.app.busy.lock().unwrap() = None;
    }
}

fn take_busy(app: &Shared, what: &str) -> Result<(Busy, watch::Receiver<bool>), Response> {
    let mut slot = app.busy.lock().unwrap();
    if let Some((current, _)) = slot.as_ref() {
        return Err(err(StatusCode::CONFLICT, &format!("Wait: {current} is running. Stop it or wait for it to finish.")));
    }
    let (tx, rx) = watch::channel(false);
    *slot = Some((what.to_string(), tx));
    Ok((Busy { app: app.clone() }, rx))
}

pub fn cancel_active(app: &App) {
    if let Some((_, tx)) = app.busy.lock().unwrap().as_ref() {
        let _ = tx.send(true);
    }
}

fn err(code: StatusCode, message: &str) -> Response {
    (code, Json(json!({"error": message}))).into_response()
}

fn ndjson(rx: mpsc::UnboundedReceiver<Value>) -> Response {
    let stream = UnboundedReceiverStream::new(rx).map(|v| Ok::<_, Infallible>(format!("{v}\n")));
    Response::builder()
        .status(200)
        .header(header::CONTENT_TYPE, "application/x-ndjson; charset=utf-8")
        .header(header::CACHE_CONTROL, "no-store, no-transform")
        .header("X-Accel-Buffering", "no")
        .body(Body::from_stream(stream))
        .unwrap()
}

async fn guard(State(app): State<Shared>, req: Request, next: Next) -> Response {
    let headers = req.headers();
    let host = headers.get(header::HOST).and_then(|h| h.to_str().ok()).unwrap_or("");
    if !app.allowed_hosts.contains(host) {
        return (StatusCode::FORBIDDEN, "Invalid host.").into_response();
    }
    if headers.get("sec-fetch-site").and_then(|h| h.to_str().ok()) == Some("cross-site") {
        return err(StatusCode::FORBIDDEN, "Use the local learn page.");
    }
    if req.method() != Method::GET && req.method() != Method::HEAD {
        let origin = headers.get(header::ORIGIN).and_then(|h| h.to_str().ok()).unwrap_or("");
        let json_body = headers.get(header::CONTENT_TYPE).and_then(|h| h.to_str().ok()).map(|c| c.starts_with("application/json")).unwrap_or(false);
        if !app.allowed_origins.contains(origin) || !json_body {
            return err(StatusCode::FORBIDDEN, "Use the local learn page.");
        }
    }
    let mut res = next.run(req).await;
    let h = res.headers_mut();
    h.insert("X-Content-Type-Options", HeaderValue::from_static("nosniff"));
    h.insert("Referrer-Policy", HeaderValue::from_static("no-referrer"));
    h.insert("X-Frame-Options", HeaderValue::from_static("DENY"));
    res
}

pub fn router(app: Shared) -> Router {
    Router::new()
        .route("/api/health", get(health))
        .route("/api/session", get(session))
        .route("/api/trust-map", get(trust_map))
        .route("/api/chapters", get(chapters))
        .route("/api/exercises", get(exercises))
        .route("/api/progress", get(progress))
        .route("/api/file", get(file))
        .route("/api/setup", get(setup))
        .route("/api/run", post(run_direct))
        .route("/api/run/cancel", post(cancel))
        .route("/api/actions/confirm", post(confirm_action))
        .route("/api/exercises/predict", post(predict))
        .route("/api/exercises/find-line", post(find_line))
        .route("/api/exercises/trace", post(trace))
        .route("/api/exercises/close-gap/test", post(close_gap_test))
        .route("/api/exercises/close-gap/run", post(close_gap_run))
        .route("/api/exercises/explain", post(explain_back))
        .route("/api/tutor/conversation", get(conversation))
        .route("/api/tutor/chat", post(chat))
        .route("/api/tutor/cancel", post(cancel))
        .route("/run/explainer.html", get(explainer_html))
        .fallback(get(asset))
        .layer(middleware::from_fn_with_state(app.clone(), guard))
        .with_state(app)
}

// ---------------------------------------------------------------- read routes

async fn health(State(app): State<Shared>) -> Json<Value> {
    Json(json!({"app": "understando-learn", "run": app.run_id, "pid": std::process::id()}))
}

async fn session(State(app): State<Shared>) -> Json<Value> {
    let raw = &app.map.raw;
    Json(json!({
        "repo": app.map.repo(), "pr": raw.get("pr"), "title": raw.get("title"), "head": app.map.head(),
        "summary": raw.get("summary"), "worktree": app.ws.worktree.display().to_string(),
        "scratch": app.ws.root.display().to_string(), "shell": app.sandbox_ready,
        "hasChapters": app.run_dir.join("learn/chapters.json").is_file(),
        "hasExplainerHtml": app.run_dir.join("explainer.html").is_file(),
    }))
}

async fn trust_map(State(app): State<Shared>) -> Json<Value> {
    // Answer keys of authored exercises stay on the server.
    let mut raw = app.map.raw.clone();
    if let Some(o) = raw.as_object_mut() {
        o.remove("exercises");
    }
    Json(raw)
}

async fn chapters(State(app): State<Shared>) -> Response {
    match std::fs::read_to_string(app.run_dir.join("learn/chapters.json")) {
        Ok(t) => ([(header::CONTENT_TYPE, "application/json; charset=utf-8")], t).into_response(),
        Err(_) => err(StatusCode::NOT_FOUND, "No compiled chapters in this run folder. Run learn/web/scripts/compile-chapters.mjs."),
    }
}

async fn explainer_html(State(app): State<Shared>) -> Response {
    match std::fs::read(app.run_dir.join("explainer.html")) {
        Ok(b) => ([(header::CONTENT_TYPE, "text/html; charset=utf-8"), (header::CACHE_CONTROL, "no-store")], b).into_response(),
        Err(_) => err(StatusCode::NOT_FOUND, "No explainer.html in this run folder."),
    }
}

async fn exercises(State(app): State<Shared>) -> Json<Value> {
    Json(app.map.public_exercises())
}

async fn progress(State(app): State<Shared>) -> Json<Value> {
    let mut p = app.mywork.read("progress.json", MyWork::empty_progress()).await;
    let tests = app.mywork.read("close-gap.json", json!({})).await;
    p["closeGapTests"] = tests;
    Json(p)
}

/// A file at the PR head, from the clone's object store. Tutor edits do not show here.
async fn file(State(app): State<Shared>, Query(q): Query<HashMap<String, String>>) -> Response {
    let path = q.get("path").map(String::as_str).unwrap_or("");
    if path.is_empty() || path.starts_with('/') || path.split('/').any(|p| p == ".." || p == ".git") || path.len() > 400 {
        return err(StatusCode::BAD_REQUEST, "Give a plain relative path.");
    }
    match git::git(&app.ws.clone, &["show", &format!("{}:{}", app.map.head(), path)]) {
        Ok(text) if text.len() <= 400_000 => Json(json!({"path": path, "text": text})).into_response(),
        Ok(_) => err(StatusCode::PAYLOAD_TOO_LARGE, "The file is too large to show."),
        Err(_) => err(StatusCode::NOT_FOUND, "No such file at the PR head."),
    }
}

async fn setup(State(app): State<Shared>, Query(q): Query<HashMap<String, String>>) -> Json<Value> {
    let mut cache = app.doctor_cache.lock().await;
    if let Some((at, v)) = cache.as_ref() {
        if !q.contains_key("refresh") && at.elapsed().as_secs() < 30 {
            return Json(v.clone());
        }
    }
    let v = doctor::run(doctor::DoctorInput {
        cwd: &app.ws.worktree,
        scratch: &app.ws.root,
        codex_auth: app.codex_auth.clone(),
        api_key_repo: app.api_key_repo,
        worktree_ready: app.ws.worktree.join(".git").exists(),
    })
    .await;
    *cache = Some((Instant::now(), v.clone()));
    Json(v)
}

// ---------------------------------------------------------------- graded runs

fn body_object(body: &Value, allowed: &[&str]) -> Result<(), Response> {
    let Some(o) = body.as_object() else {
        return Err(err(StatusCode::BAD_REQUEST, "Send a JSON object."));
    };
    if let Some(extra) = o.keys().find(|k| !allowed.contains(&k.as_str())) {
        return Err(err(
            StatusCode::BAD_REQUEST,
            &format!("Refused: the field {extra:?} is not permitted. The server takes only a kind and an id, and it runs the argv that the trust map records."),
        ));
    }
    Ok(())
}

fn str_field<'a>(body: &'a Value, key: &str) -> &'a str {
    body.get(key).and_then(Value::as_str).unwrap_or("")
}

/// Start a graded run in the background and stream its events.
fn start_graded(app: Shared, plan: Graded, test: Option<String>, on_done: impl FnOnce(Shared, Value) -> Option<Value> + Send + 'static) -> Response {
    let (busy, cancel_rx) = match take_busy(&app, &format!("graded run {}", plan.id())) {
        Ok(b) => b,
        Err(r) => return r,
    };
    let (tx, rx) = mpsc::unbounded_channel::<Value>();
    let started = doctor::now();
    let _ = tx.send(json!({"type": "start", "kind": plan.kind(), "id": plan.id(), "tier": "fact"}));
    tokio::spawn(async move {
        let _busy = busy;
        let closer = tx.clone();
        let cancel_tx = app.busy.lock().unwrap().as_ref().map(|(_, t)| t.clone());
        let watcher = tokio::spawn(async move {
            closer.closed().await;
            if let Some(t) = cancel_tx {
                let _ = t.send(true);
            }
        });
        let emit_tx = tx.clone();
        let emit = move |v: Value| {
            let _ = emit_tx.send(v);
        };
        let ctx = grading::Ctx { map: &app.map, ws: &app.ws, env_file: app.env_file.as_deref(), cancel: cancel_rx };
        let result = grading::run(ctx, &plan, test.as_deref(), &emit).await;
        let _ = app
            .mywork
            .record_run(json!({"kind": plan.kind(), "id": plan.id(), "status": result.get("status"), "at": started}))
            .await;
        let _ = tx.send(json!({"type": "result", "kind": plan.kind(), "id": plan.id(), "result": result}));
        if let Some(grade) = on_done(app.clone(), result) {
            let _ = tx.send(json!({"type": "grade", "grade": grade}));
        }
        let _ = tx.send(json!({"type": "done"}));
        watcher.abort();
    });
    ndjson(rx)
}

async fn run_direct(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["kind", "id"]) {
        return r;
    }
    match app.map.authorize(str_field(&body, "kind"), str_field(&body, "id")) {
        Ok(plan @ (Graded::Control { .. } | Graded::Verifier { .. })) => start_graded(app, plan, None, |_, _| None),
        Ok(_) => err(StatusCode::FORBIDDEN, "Refused: use the close-gap route for that exercise."),
        Err(e) => err(StatusCode::FORBIDDEN, &format!("Refused: {e}")),
    }
}

async fn confirm_action(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["proposalId"]) {
        return r;
    }
    let Some((kind, id)) = app.proposals.lock().unwrap().remove(str_field(&body, "proposalId")) else {
        return err(StatusCode::NOT_FOUND, "Refused: this proposal is not known or it already ran.");
    };
    match app.map.authorize(&kind, &id) {
        Ok(plan) => start_graded(app, plan, None, |_, _| None),
        Err(e) => err(StatusCode::FORBIDDEN, &format!("Refused: {e}")),
    }
}

async fn cancel(State(app): State<Shared>) -> Json<Value> {
    let active = app.busy.lock().unwrap().is_some();
    cancel_active(&app);
    Json(json!({"stopped": active}))
}

async fn predict(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["control", "prediction"]) {
        return r;
    }
    let prediction = str_field(&body, "prediction").to_string();
    if prediction != "red" && prediction != "green" {
        return err(StatusCode::BAD_REQUEST, "Predict red or green.");
    }
    let control = str_field(&body, "control").to_string();
    let plan = match app.map.authorize("run-control", &control) {
        Ok(p) => p,
        Err(e) => return err(StatusCode::FORBIDDEN, &format!("Refused: {e}")),
    };
    // The prediction is saved before the run starts.
    let ex = format!("predict-{control}");
    let _ = app.mywork.record_attempt(&ex, "predict", json!({"prediction": prediction, "at": doctor::now(), "phase": "predicted"})).await;
    start_graded(app, plan, None, move |app, result| {
        let status = result.get("status").and_then(Value::as_str).unwrap_or("error").to_string();
        let graded = status == "red" || status == "green";
        let correct = graded && status == prediction;
        let cannot_fail = status == "green";
        let grade = json!({"exercise": ex, "prediction": prediction, "actual": status, "graded": graded, "correct": correct,
            "cannotFail": cannot_fail, "tier": "fact",
            "message": if !graded { "The run did not give red or green, so it grades nothing. Read the output.".to_string() }
                else if correct { format!("Correct. The check went {status}.") } else { format!("Not this time. The check went {status}.") }});
        let ex2 = ex.clone();
        let g2 = grade.clone();
        tokio::spawn(async move {
            let mut a = g2;
            a["at"] = json!(doctor::now());
            let _ = app.mywork.record_attempt(&ex2, "predict", a).await;
        });
        Some(grade)
    })
}

async fn find_line(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["claim", "path", "line"]) {
        return r;
    }
    let claim_id = str_field(&body, "claim");
    let Some(claim) = app.map.claim(claim_id) else {
        return err(StatusCode::NOT_FOUND, "No such claim.");
    };
    let path = str_field(&body, "path").trim_start_matches("./");
    let Some(line) = body.get("line").and_then(Value::as_i64) else {
        return err(StatusCode::BAD_REQUEST, "Give a line number.");
    };
    let refs = claim.get("code").and_then(Value::as_array).cloned().unwrap_or_default();
    let correct = refs.iter().any(|r| {
        r.get("path").and_then(Value::as_str) == Some(path) && {
            let start = r.get("start").and_then(Value::as_i64).unwrap_or(1);
            let end = r.get("end").and_then(Value::as_i64).unwrap_or(start);
            line >= start && line <= end
        }
    });
    let ex = format!("line-{claim_id}");
    let attempt = json!({"path": path, "line": line, "correct": correct, "at": doctor::now()});
    let _ = app.mywork.record_attempt(&ex, "find-line", attempt).await;
    Json(json!({"correct": correct, "tier": "fact", "answer": if correct { json!(refs) } else { Value::Null },
        "message": if correct { "Correct. That line is in the code that the claim names." } else { "Not that line. Look again, or ask the tutor for a hint." }}))
    .into_response()
}

async fn trace(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["exercise", "step", "choice"]) {
        return r;
    }
    let id = str_field(&body, "exercise");
    let Some(x) = app.map.exercise(id).filter(|x| x.get("kind").and_then(Value::as_str) == Some("trace")) else {
        return err(StatusCode::NOT_FOUND, "No such trace exercise.");
    };
    let (Some(step), Some(choice)) = (body.get("step").and_then(Value::as_u64), body.get("choice").and_then(Value::as_u64)) else {
        return err(StatusCode::BAD_REQUEST, "Give a step and a choice.");
    };
    let Some(st) = x.get("steps").and_then(Value::as_array).and_then(|a| a.get(step as usize)) else {
        return err(StatusCode::NOT_FOUND, "No such step.");
    };
    let correct = st.get("answer").and_then(Value::as_u64) == Some(choice);
    let _ = app.mywork.record_attempt(id, "trace", json!({"step": step, "choice": choice, "correct": correct, "at": doctor::now()})).await;
    Json(json!({"correct": correct, "tier": "fact", "why": if correct { st.get("why").cloned().unwrap_or(Value::Null) } else { Value::Null }}))
        .into_response()
}

async fn close_gap_test(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["exercise", "content"]) {
        return r;
    }
    let id = str_field(&body, "exercise").to_string();
    if app.map.authorize("close-gap", &id).is_err() {
        return err(StatusCode::FORBIDDEN, "Refused: no such close-gap exercise.");
    }
    let content = str_field(&body, "content").to_string();
    if content.len() > 64_000 || content.contains('\0') {
        return err(StatusCode::PAYLOAD_TOO_LARGE, "The test file is too large.");
    }
    let x = app.map.exercise(&id).unwrap();
    let test_path = x.get("test_path").and_then(Value::as_str).unwrap_or("");
    // The learner can write only the test file that the exercise names.
    if let Err(e) = app.ws.inside(test_path) {
        return err(StatusCode::FORBIDDEN, &e);
    }
    let saved = app
        .mywork
        .update("close-gap.json", json!({}), |v| {
            if !v.is_object() {
                *v = json!({});
            }
            v[&id] = json!({"path": test_path, "content": content, "savedAt": doctor::now()});
        })
        .await;
    // Also put it in the worktree, so the tutor can read it. A graded run writes it again after the reset.
    if app.busy.lock().unwrap().is_none() {
        if let Ok(p) = app.ws.inside(test_path) {
            let _ = p.parent().map(std::fs::create_dir_all);
            let _ = std::fs::write(p, &content);
        }
    }
    match saved {
        Ok(_) => Json(json!({"saved": true, "path": test_path})).into_response(),
        Err(e) => err(StatusCode::INTERNAL_SERVER_ERROR, &e),
    }
}

async fn close_gap_run(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["exercise"]) {
        return r;
    }
    let id = str_field(&body, "exercise").to_string();
    let plan = match app.map.authorize("close-gap", &id) {
        Ok(p) => p,
        Err(e) => return err(StatusCode::FORBIDDEN, &format!("Refused: {e}")),
    };
    let tests = app.mywork.read("close-gap.json", json!({})).await;
    let Some(content) = tests.pointer(&format!("/{id}/content")).and_then(Value::as_str).map(String::from) else {
        return err(StatusCode::BAD_REQUEST, "Save your test first.");
    };
    start_graded(app, plan, Some(content), move |app, result| {
        let passed = result.get("passed").and_then(Value::as_bool) == Some(true);
        let grade = json!({"exercise": id, "correct": passed, "tier": "fact",
            "message": if passed { "Your test passes at the PR head and fails on the planted bug. The gap has a check now." }
                else { "Not yet. The test must pass at the head and fail on the planted bug." }});
        let g = grade.clone();
        tokio::spawn(async move {
            let mut a = g;
            a["at"] = json!(doctor::now());
            let _ = app.mywork.record_attempt(&id, "close-gap", a).await;
        });
        Some(grade)
    })
}

// ---------------------------------------------------------------- model calls

fn provider_of(body: &Value) -> Result<Provider, Response> {
    Provider::parse(str_field(body, "provider")).ok_or_else(|| err(StatusCode::BAD_REQUEST, "Choose Claude Code or Codex."))
}

fn codex_auth(app: &App) -> Result<CodexAuth, String> {
    app.codex_auth.clone()
}

async fn explain_back(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["claim", "text", "provider"]) {
        return r;
    }
    let provider = match provider_of(&body) {
        Ok(p) => p,
        Err(r) => return r,
    };
    let text = str_field(&body, "text").trim().to_string();
    if text.is_empty() || text.len() > 6000 {
        return err(StatusCode::BAD_REQUEST, "Write an explanation of 1 to 6000 characters.");
    }
    let claim_id = str_field(&body, "claim").to_string();
    let Some(claim) = app.map.claim(&claim_id).cloned() else {
        return err(StatusCode::NOT_FOUND, "No such claim.");
    };
    let auth = if provider == Provider::Codex {
        match codex_auth(&app) {
            Ok(a) => a,
            Err(e) => return err(StatusCode::BAD_REQUEST, &e),
        }
    } else {
        CodexAuth::OwnLogin
    };
    let (_busy, cancel_rx) = match take_busy(&app, "the grader") {
        Ok(b) => b,
        Err(r) => return r,
    };
    let empty = app.ws.root.join(format!("grader-{}", uuid::Uuid::new_v4()));
    let _ = std::fs::create_dir_all(&empty);
    let prompt = json!({"answerKey": tutor::answer_key(&app.map, &claim), "learnerExplanation": text}).to_string();
    let call = agent::Call {
        provider,
        role: Role::Grader,
        system: tutor::grader_system(),
        prompt,
        cwd: empty.clone(),
        output_schema: Some(tutor::grader_schema()),
        codex_auth: auth,
        deny_read: vec![],
    };
    let out = agent::run(call, cancel_rx, |_| {}).await;
    let _ = std::fs::remove_dir_all(&empty);
    match out {
        Ok(a) => {
            let grade: Value = serde_json::from_str(a.text.trim()).unwrap_or(json!({"feedback": a.text}));
            let rec = json!({"text": text, "grade": grade, "provider": provider.id(), "model": a.model, "tier": "guess", "at": doctor::now()});
            let _ = app.mywork.record_attempt(&format!("explain-{claim_id}"), "explain-back", rec).await;
            Json(json!({"grade": grade, "tier": "guess", "provider": provider.id(), "model": a.model,
                "label": "Model-generated grade. It is a guess, not a fact. It does not change a verdict."}))
            .into_response()
        }
        Err(e) => err(StatusCode::BAD_GATEWAY, &e),
    }
}

async fn conversation(State(app): State<Shared>) -> Json<Value> {
    Json(app.mywork.read("tutor-conversation.json", json!({"schema": 1, "messages": []})).await)
}

const CONTEXT_KEYS: &[&str] = &["chapter", "claim", "selection", "exercise", "control", "verifier"];

async fn chat(State(app): State<Shared>, Json(body): Json<Value>) -> Response {
    if let Err(r) = body_object(&body, &["provider", "message", "level", "context"]) {
        return r;
    }
    let provider = match provider_of(&body) {
        Ok(p) => p,
        Err(r) => return r,
    };
    let message = str_field(&body, "message").trim().to_string();
    if message.is_empty() || message.len() > 12_000 {
        return err(StatusCode::BAD_REQUEST, "Write a message of 1 to 12000 characters.");
    }
    let level = str_field(&body, "level");
    let level = if tutor::LEVELS.contains(&level) { level.to_string() } else { "familiar".to_string() };
    let mut context = serde_json::Map::new();
    if let Some(c) = body.get("context").and_then(Value::as_object) {
        for (k, v) in c {
            if CONTEXT_KEYS.contains(&k.as_str()) {
                if let Some(s) = v.as_str() {
                    context.insert(k.clone(), json!(s.chars().take(8000).collect::<String>()));
                }
            }
        }
    }
    let auth = if provider == Provider::Codex {
        match codex_auth(&app) {
            Ok(a) => a,
            Err(e) => return err(StatusCode::BAD_REQUEST, &e),
        }
    } else {
        CodexAuth::OwnLogin
    };
    let (busy, cancel_rx) = match take_busy(&app, "a tutor turn") {
        Ok(b) => b,
        Err(r) => return r,
    };
    let (tx, rx) = mpsc::unbounded_channel::<Value>();
    tokio::spawn(async move {
        let _busy = busy;
        let cancel_tx = app.busy.lock().unwrap().as_ref().map(|(_, t)| t.clone());
        let closer = tx.clone();
        let watcher = tokio::spawn(async move {
            closer.closed().await;
            if let Some(t) = cancel_tx {
                let _ = t.send(true);
            }
        });
        let saved = app.mywork.read("tutor-conversation.json", json!({"schema": 1, "messages": []})).await;
        let mut messages: Vec<Value> = saved.get("messages").and_then(Value::as_array).cloned().unwrap_or_default();
        let mut recent = Vec::new();
        let mut size = 0;
        for m in messages.iter().rev() {
            let e = json!({"role": m.get("role"), "text": m.get("text")});
            size += e.to_string().len();
            if size > 30_000 || recent.len() >= 12 {
                break;
            }
            recent.insert(0, e);
        }
        let user = json!({"id": uuid::Uuid::new_v4().to_string(), "role": "user", "text": message, "level": level,
                          "context": Value::Object(context.clone()), "createdAt": doctor::now()});
        messages.push(user);
        let shell = app.sandbox_ready;
        let mut assistant = json!({"id": uuid::Uuid::new_v4().to_string(), "role": "assistant", "text": "", "provider": provider.id(),
            "tier": "guess", "status": "streaming", "createdAt": doctor::now(), "tools": [], "actions": [], "shell": shell});
        let _ = tx.send(json!({"type": "message", "message": assistant}));
        let _ = tx.send(json!({"type": "status", "message": "Reading the trust map and the worktree."}));
        let save = |msgs: &Vec<Value>, a: &Value| {
            let mut all = msgs.clone();
            all.push(a.clone());
            json!({"schema": 1, "messages": all})
        };
        let snapshot = save(&messages, &assistant);
        let _ = app.mywork.update("tutor-conversation.json", json!({}), |v| *v = snapshot).await;

        let prompt = json!({"learnerMessage": message, "level": tutor::level_text(&level), "current": Value::Object(context),
                            "recentConversation": recent}).to_string();
        let call = agent::Call {
            provider,
            role: Role::Tutor { shell },
            system: tutor::system_prompt(&app.map, shell),
            prompt,
            cwd: app.ws.worktree.clone(),
            output_schema: None,
            codex_auth: auth,
            deny_read: app.deny_read.clone(),
        };
        let stream = Arc::new(Mutex::new((TagStream::default(), String::new(), Vec::<Value>::new(), Vec::<Value>::new())));
        let handle = |pieces: Vec<Piece>, st: &mut (TagStream, String, Vec<Value>, Vec<Value>)| {
            for p in pieces {
                match p {
                    Piece::Text(t) => {
                        st.1.push_str(&t);
                        let _ = tx.send(json!({"type": "delta", "text": t}));
                    }
                    Piece::Tag(tag) => {
                        let ev = authorize_tag(&app, &tag, st.3.len());
                        if ev["type"] == "action" {
                            st.3.push(ev["proposal"].clone());
                        }
                        let _ = tx.send(ev);
                    }
                }
            }
        };
        let st2 = stream.clone();
        let tx2 = tx.clone();
        let result = agent::run(call, cancel_rx, move |e| match e {
            agent::Event::Delta(t) => {
                let mut st = st2.lock().unwrap();
                let mut pieces = Vec::new();
                st.0.push(&t, &mut pieces);
                handle(pieces, &mut st);
            }
            agent::Event::Tool { id, name, status, detail } => {
                let tool = json!({"id": id, "name": name, "status": status, "detail": grading::redact(&detail), "tier": "guess"});
                st2.lock().unwrap().2.push(tool.clone());
                let _ = tx2.send(json!({"type": "tool", "tool": tool}));
            }
        })
        .await;
        {
            let mut st = stream.lock().unwrap();
            let mut pieces = Vec::new();
            st.0.finish(&mut pieces);
            let tx3 = tx.clone();
            for p in pieces {
                match p {
                    Piece::Text(t) => {
                        st.1.push_str(&t);
                        let _ = tx3.send(json!({"type": "delta", "text": t}));
                    }
                    Piece::Tag(tag) => {
                        let ev = authorize_tag(&app, &tag, st.3.len());
                        if ev["type"] == "action" {
                            st.3.push(ev["proposal"].clone());
                        }
                        let _ = tx3.send(ev);
                    }
                }
            }
        }
        let (streamed, tools, actions_list) = {
            let st = stream.lock().unwrap();
            (st.1.clone(), st.2.clone(), st.3.clone())
        };
        assistant["tools"] = json!(tools);
        assistant["actions"] = json!(actions_list);
        match result {
            Ok(a) => {
                let final_text = actions::strip_tags(&a.text);
                assistant["text"] = json!(if final_text.trim().is_empty() { streamed } else { final_text.trim_end().to_string() });
                assistant["status"] = json!("complete");
                assistant["model"] = json!(a.model);
                assistant["usage"] = a.usage;
            }
            Err(e) => {
                assistant["status"] = json!("error");
                assistant["text"] = json!(if streamed.is_empty() { format!("The tutor could not answer: {e}") } else { streamed });
                let _ = tx.send(json!({"type": "error", "message": e}));
            }
        }
        let snapshot = save(&messages, &assistant);
        let _ = app.mywork.update("tutor-conversation.json", json!({}), |v| *v = snapshot).await;
        let _ = tx.send(json!({"type": "message", "message": assistant}));
        let _ = tx.send(json!({"type": "done"}));
        watcher.abort();
    });
    ndjson(rx)
}

fn authorize_tag(app: &App, tag: &actions::Tag, count: usize) -> Value {
    let refuse = |reason: String| json!({"type": "action_refused", "reason": reason, "tag": tag.raw, "tier": "guess"});
    if count >= 3 {
        return refuse("The tutor can propose at most three runs in one answer.".into());
    }
    if !tag.extra.is_empty() {
        return refuse(format!("Refused: the attribute {:?} is not permitted. A tag holds only kind and id.", tag.extra));
    }
    let (Some(kind), Some(id)) = (tag.attrs.get("kind"), tag.attrs.get("id")) else {
        return refuse("Refused: a tag needs a kind and an id.".into());
    };
    if !trustmap::valid_id(id) {
        return refuse(format!("Refused: {id:?} is not an id."));
    }
    match app.map.authorize(kind, id) {
        Ok(plan @ (Graded::Control { .. } | Graded::Verifier { .. })) => {
            let pid = uuid::Uuid::new_v4().to_string();
            app.proposals.lock().unwrap().insert(pid.clone(), (kind.clone(), id.clone()));
            let (vid, desc) = match &plan {
                Graded::Control { control, verifier } => (
                    verifier.clone(),
                    app.map.control(control).and_then(|k| k.get("description")).and_then(Value::as_str).unwrap_or("").to_string(),
                ),
                Graded::Verifier { verifier } => (
                    verifier.clone(),
                    app.map.verifier(verifier).and_then(|k| k.get("description")).and_then(Value::as_str).unwrap_or("").to_string(),
                ),
                Graded::CloseGap { .. } => unreachable!(),
            };
            let cmd = app.map.verifier(&vid).and_then(|v| v.get("command")).cloned().unwrap_or(Value::Null);
            json!({"type": "action", "proposal": {"id": pid, "kind": kind, "target": id, "verifier": vid, "description": desc,
                   "argv": cmd.get("argv"), "cwd": cmd.get("cwd").cloned().unwrap_or(json!("."))}})
        }
        Ok(_) => refuse("Refused: the tutor cannot start a close-gap run.".into()),
        Err(e) => refuse(format!("Refused: {e}")),
    }
}

// ---------------------------------------------------------------- static UI

async fn asset(req: Request) -> Response {
    let path = req.uri().path().trim_start_matches('/');
    let path = if path.is_empty() { "index.html" } else { path };
    let (file, name) = match Assets::get(path) {
        Some(f) => (f, path.to_string()),
        None if !path.contains('.') => match Assets::get("index.html") {
            Some(f) => (f, "index.html".to_string()),
            None => return (StatusCode::NOT_FOUND, "The UI is not built. Run npm run build in learn/web.").into_response(),
        },
        None => return (StatusCode::NOT_FOUND, "Not found.").into_response(),
    };
    let mime = mime_guess::from_path(&name).first_or_octet_stream();
    let mut headers = HeaderMap::new();
    headers.insert(header::CONTENT_TYPE, HeaderValue::from_str(mime.as_ref()).unwrap());
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static(if name == "index.html" { "no-cache" } else { "public, max-age=3600" }));
    if name == "index.html" {
        headers.insert(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(
                "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; \
                 font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; \
                 frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            ),
        );
    }
    (headers, file.data.into_owned()).into_response()
}
