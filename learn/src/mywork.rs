//! The learner's record under `<run>/my-work/`. Each write goes to a temp file, then a rename.

use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use tokio::sync::Mutex;

pub struct MyWork {
    dir: PathBuf,
    lock: Mutex<()>,
}

impl MyWork {
    pub fn new(run_dir: &Path) -> Self {
        Self { dir: run_dir.join("my-work"), lock: Mutex::new(()) }
    }

    fn path(&self, name: &str) -> PathBuf {
        self.dir.join(name)
    }

    pub async fn read(&self, name: &str, empty: Value) -> Value {
        let _g = self.lock.lock().await;
        self.read_unlocked(name, empty)
    }

    fn read_unlocked(&self, name: &str, empty: Value) -> Value {
        std::fs::read_to_string(self.path(name))
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or(empty)
    }

    fn write_unlocked(&self, name: &str, value: &Value) -> Result<(), String> {
        std::fs::create_dir_all(&self.dir).map_err(|e| e.to_string())?;
        let meta = std::fs::symlink_metadata(&self.dir).map_err(|e| e.to_string())?;
        if meta.file_type().is_symlink() {
            return Err("my-work cannot be a symbolic link".into());
        }
        let tmp = self.dir.join(format!(".{name}.{}.tmp", uuid::Uuid::new_v4()));
        let mut text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
        text.push('\n');
        std::fs::write(&tmp, text).map_err(|e| e.to_string())?;
        std::fs::rename(&tmp, self.path(name)).map_err(|e| e.to_string())
    }

    /// Read, change and write one file under the lock.
    pub async fn update<F: FnOnce(&mut Value)>(&self, name: &str, empty: Value, f: F) -> Result<Value, String> {
        let _g = self.lock.lock().await;
        let mut v = self.read_unlocked(name, empty);
        f(&mut v);
        self.write_unlocked(name, &v)?;
        Ok(v)
    }

    pub fn empty_progress() -> Value {
        json!({"schema": 1, "exercises": {}, "runs": []})
    }

    /// Add one attempt to the progress record.
    pub async fn record_attempt(&self, exercise: &str, kind: &str, attempt: Value) -> Result<Value, String> {
        self.update("progress.json", Self::empty_progress(), |p| {
            normalize(p);
            let entry = p["exercises"]
                .as_object_mut()
                .unwrap()
                .entry(exercise.to_string())
                .or_insert_with(|| json!({"kind": kind, "attempts": [], "passed": false}));
            if attempt.get("correct").and_then(Value::as_bool) == Some(true) {
                entry["passed"] = json!(true);
            }
            let list = entry["attempts"].as_array_mut().unwrap();
            list.push(attempt);
            if list.len() > 50 {
                list.remove(0);
            }
        })
        .await
    }

    pub async fn record_run(&self, run: Value) -> Result<(), String> {
        self.update("progress.json", Self::empty_progress(), |p| {
            normalize(p);
            let list = p["runs"].as_array_mut().unwrap();
            list.push(run);
            if list.len() > 100 {
                list.remove(0);
            }
        })
        .await
        .map(|_| ())
    }
}

fn normalize(p: &mut Value) {
    if !p.get("exercises").map(Value::is_object).unwrap_or(false) || !p.get("runs").map(Value::is_array).unwrap_or(false) {
        *p = MyWork::empty_progress();
    }
}
