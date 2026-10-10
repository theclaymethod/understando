//! The scratch workspace: a private clone of the reviewed repo, and one worktree at the PR head.
//!
//! The user's checkout is never a cwd. `git clone --local --no-checkout` makes a clone with its
//! own object store (hard links, no alternates), so the worktree metadata lives in the clone and
//! the tutor sandbox can deny reads of the user's checkout.

use std::path::{Path, PathBuf};
use std::process::Command;

pub fn git(dir: &Path, args: &[&str]) -> Result<String, String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"])
        .args(args)
        .env_remove("GIT_DIR")
        .env_remove("GIT_WORK_TREE")
        .output()
        .map_err(|e| format!("git did not start: {e}"))?;
    if !out.status.success() {
        return Err(format!("git {} failed: {}", args.join(" "), String::from_utf8_lossy(&out.stderr).trim()));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

pub struct Workspace {
    pub root: PathBuf,
    pub clone: PathBuf,
    pub worktree: PathBuf,
    pub head: String,
}

impl Workspace {
    /// Make `<root>/clone` and `<root>/worktree`. `root` must not exist yet.
    pub fn create(repo: &Path, head: &str, root: &Path) -> Result<Self, String> {
        git(repo, &["cat-file", "-e", &format!("{head}^{{commit}}")])
            .map_err(|_| format!("The repo at {} does not hold the head commit {head}.", repo.display()))?;
        std::fs::create_dir_all(root).map_err(|e| format!("could not make {}: {e}", root.display()))?;
        let clone = root.join("clone");
        let worktree = root.join("worktree");
        let out = Command::new("git")
            .args(["clone", "--quiet", "--local", "--no-checkout", "--no-tags"])
            .arg(repo)
            .arg(&clone)
            .output()
            .map_err(|e| format!("git clone did not start: {e}"))?;
        if !out.status.success() {
            return Err(format!("git clone failed: {}", String::from_utf8_lossy(&out.stderr).trim()));
        }
        git(&clone, &["cat-file", "-e", &format!("{head}^{{commit}}")])?;
        git(&clone, &["worktree", "add", "--detach", worktree.to_str().unwrap(), head])?;
        Ok(Self { root: root.to_path_buf(), clone, worktree, head: head.to_string() })
    }

    /// Put the worktree back to the head commit exactly: tracked files, untracked files and
    /// ignored files. Graded runs call this first, so a tutor edit cannot change a grade.
    pub fn reset(&self) -> Result<(), String> {
        git(&self.worktree, &["checkout", "--quiet", "--force", "--detach", &self.head])?;
        git(&self.worktree, &["reset", "--quiet", "--hard", &self.head])?;
        git(&self.worktree, &["clean", "-ffdxq"])?;
        let left = git(&self.worktree, &["status", "--porcelain", "--ignored"])?;
        if !left.is_empty() {
            return Err(format!("the worktree is not clean after the reset: {left}"));
        }
        Ok(())
    }

    /// Remove the worktree, the clone and the root. Safe to call twice.
    pub fn remove(&self) {
        if self.worktree.exists() {
            let _ = git(&self.clone, &["worktree", "remove", "--force", self.worktree.to_str().unwrap()]);
        }
        let _ = std::fs::remove_dir_all(&self.root);
    }

    /// Resolve a path that a learner or a trust map names, and refuse one that leaves the worktree.
    pub fn inside(&self, rel: &str) -> Result<PathBuf, String> {
        if rel.is_empty() || rel.starts_with('/') || rel.split('/').any(|p| p == ".." || p == ".git") || rel.contains('\0') {
            return Err(format!("The path {rel:?} is not a plain relative path."));
        }
        let path = self.worktree.join(rel);
        let mut probe = path.clone();
        while !probe.exists() {
            if !probe.pop() {
                break;
            }
        }
        let real_root = self.worktree.canonicalize().map_err(|e| e.to_string())?;
        let real = probe.canonicalize().map_err(|e| e.to_string())?;
        if !real.starts_with(&real_root) {
            return Err(format!("The path {rel:?} leaves the worktree."));
        }
        Ok(path)
    }
}
