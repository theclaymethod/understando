//! The trust map of one run, the allowlist built from it, and the exercises it holds.
//!
//! The trust map is data. Only ids that it names, with the argv and cwd that it records, can run.

use serde_json::{json, Value};
use std::path::Path;

pub struct TrustMap {
    pub raw: Value,
}

/// One graded run that the allowlist permits. The server builds it from the trust map only.
#[derive(Clone, Debug)]
pub enum Graded {
    Verifier { verifier: String },
    Control { control: String, verifier: String },
    CloseGap { exercise: String },
}

impl Graded {
    pub fn kind(&self) -> &'static str {
        match self {
            Graded::Verifier { .. } => "run-verifier",
            Graded::Control { .. } => "run-control",
            Graded::CloseGap { .. } => "close-gap",
        }
    }
    pub fn id(&self) -> &str {
        match self {
            Graded::Verifier { verifier } => verifier,
            Graded::Control { control, .. } => control,
            Graded::CloseGap { exercise } => exercise,
        }
    }
}

fn arr<'a>(v: &'a Value, key: &str) -> &'a [Value] {
    v.get(key).and_then(Value::as_array).map(Vec::as_slice).unwrap_or(&[])
}

fn s<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(Value::as_str).unwrap_or("")
}

static ID: std::sync::LazyLock<regex::Regex> =
    std::sync::LazyLock::new(|| regex::Regex::new(r"^[A-Z][A-Za-z0-9_.-]{0,40}$").unwrap());

pub fn valid_id(id: &str) -> bool {
    ID.is_match(id)
}

fn valid_command(c: &Value) -> bool {
    c.get("argv")
        .and_then(Value::as_array)
        .map(|a| !a.is_empty() && a.iter().all(Value::is_string))
        .unwrap_or(false)
}

impl TrustMap {
    pub fn load(path: &Path) -> Result<Self, String> {
        let text = std::fs::read_to_string(path).map_err(|e| format!("could not read {}: {e}", path.display()))?;
        let raw: Value = serde_json::from_str(&text).map_err(|e| format!("{} is not JSON: {e}", path.display()))?;
        for key in ["repo", "head", "claims", "verifiers", "controls"] {
            if raw.get(key).is_none() {
                return Err(format!("the trust map has no {key}"));
            }
        }
        let head = s(&raw, "head");
        if !(7..=40).contains(&head.len()) || !head.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err("the trust map head is not a commit SHA".into());
        }
        Ok(Self { raw })
    }

    pub fn repo(&self) -> &str {
        s(&self.raw, "repo")
    }
    pub fn head(&self) -> &str {
        s(&self.raw, "head")
    }
    pub fn claims(&self) -> &[Value] {
        arr(&self.raw, "claims")
    }
    pub fn verifiers(&self) -> &[Value] {
        arr(&self.raw, "verifiers")
    }
    pub fn controls(&self) -> &[Value] {
        arr(&self.raw, "controls")
    }
    pub fn setup(&self) -> &[Value] {
        arr(&self.raw, "setup")
    }
    pub fn authored_exercises(&self) -> &[Value] {
        arr(&self.raw, "exercises")
    }

    pub fn verifier(&self, id: &str) -> Option<&Value> {
        self.verifiers().iter().find(|v| s(v, "id") == id)
    }
    pub fn control(&self, id: &str) -> Option<&Value> {
        self.controls().iter().find(|v| s(v, "id") == id)
    }
    pub fn claim(&self, id: &str) -> Option<&Value> {
        self.claims().iter().find(|v| s(v, "id") == id)
    }
    pub fn exercise(&self, id: &str) -> Option<&Value> {
        self.authored_exercises().iter().find(|v| s(v, "id") == id)
    }

    /// The allowlist check. A kind and an id go in; a plan built from the trust map comes out.
    pub fn authorize(&self, kind: &str, id: &str) -> Result<Graded, String> {
        if !valid_id(id) {
            return Err(format!("{id:?} is not an id in this trust map."));
        }
        match kind {
            "run-verifier" => {
                let v = self.verifier(id).ok_or_else(|| format!("No verifier {id} is in this trust map."))?;
                if !v.get("command").map(valid_command).unwrap_or(false) {
                    return Err(format!("Verifier {id} has no command. Its evidence is recorded, not run."));
                }
                Ok(Graded::Verifier { verifier: id.into() })
            }
            "run-control" => {
                let k = self.control(id).ok_or_else(|| format!("No control {id} is in this trust map."))?;
                let vid = s(k, "verifier");
                let v = self.verifier(vid).ok_or_else(|| format!("Control {id} names no known verifier."))?;
                if !v.get("command").map(valid_command).unwrap_or(false) {
                    return Err(format!("Verifier {vid} of control {id} has no command."));
                }
                if arr(k, "edits").is_empty() {
                    return Err(format!("Control {id} has no edits."));
                }
                Ok(Graded::Control { control: id.into(), verifier: vid.into() })
            }
            "close-gap" => {
                let x = self.exercise(id).ok_or_else(|| format!("No exercise {id} is in this trust map."))?;
                if s(x, "kind") != "close-gap" || !x.get("command").map(valid_command).unwrap_or(false) {
                    return Err(format!("Exercise {id} is not a close-gap exercise with a command."));
                }
                Ok(Graded::CloseGap { exercise: id.into() })
            }
            _ => Err(format!("The action kind {kind:?} is not permitted. Use run-control or run-verifier.")),
        }
    }

    /// Ids the tutor may name in an action tag.
    pub fn action_ids(&self) -> (Vec<String>, Vec<String>) {
        let controls = self
            .controls()
            .iter()
            .filter(|k| self.authorize("run-control", s(k, "id")).is_ok())
            .map(|k| s(k, "id").to_string())
            .collect();
        let verifiers = self
            .verifiers()
            .iter()
            .filter(|v| v.get("command").map(valid_command).unwrap_or(false))
            .map(|v| s(v, "id").to_string())
            .collect();
        (controls, verifiers)
    }

    /// The exercises as the learner sees them. Answer keys stay on the server.
    pub fn public_exercises(&self) -> Value {
        let mut out = Vec::new();
        for k in self.controls() {
            let id = s(k, "id");
            if self.authorize("run-control", id).is_err() {
                continue;
            }
            let v = self.verifier(s(k, "verifier")).unwrap();
            out.push(json!({
                "id": format!("predict-{id}"), "kind": "predict", "control": id,
                "verifier": s(v, "id"), "verifierDescription": s(v, "description"),
                "claims": v.get("claims"), "recipe": s(k, "recipe"), "description": s(k, "description"),
                "title": format!("Predict, then run: {id} on {}", s(v, "id")),
            }));
        }
        for c in self.claims() {
            let id = s(c, "id");
            let code = arr(c, "code");
            if let Some(first) = code.first() {
                let paths: Vec<&str> = code.iter().map(|r| s(r, "path")).collect();
                out.push(json!({
                    "id": format!("line-{id}"), "kind": "find-line", "claim": id,
                    "title": format!("Find the line: {id}"),
                    "prompt": c.pointer("/plain/what").and_then(Value::as_str).unwrap_or(s(c, "text")),
                    "hintPath": s(first, "path"), "paths": paths,
                }));
            }
            if c.get("plain").is_some() {
                out.push(json!({
                    "id": format!("explain-{id}"), "kind": "explain-back", "claim": id,
                    "title": format!("Explain it back: {id}"), "prompt": s(c, "text"), "tier": "guess",
                }));
            }
        }
        for x in self.authored_exercises() {
            match s(x, "kind") {
                "trace" => {
                    let steps: Vec<Value> = arr(x, "steps")
                        .iter()
                        .map(|st| json!({"prompt": st.get("prompt"), "choices": st.get("choices")}))
                        .collect();
                    out.push(json!({"id": x.get("id"), "kind": "trace", "claim": x.get("claim"), "title": x.get("title"),
                        "scenario": x.get("scenario"), "steps": steps}));
                }
                "close-gap" => out.push(json!({"id": x.get("id"), "kind": "close-gap", "claim": x.get("claim"),
                    "title": x.get("title"), "brief": x.get("brief"), "testPath": x.get("test_path"),
                    "starter": x.get("starter"), "bug": x.pointer("/bug/description"),
                    "argv": x.pointer("/command/argv")})),
                _ => {}
            }
        }
        Value::Array(out)
    }
}
