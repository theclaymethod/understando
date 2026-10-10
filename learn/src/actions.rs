//! `<understando-action kind="run-control" id="K16"/>` tags in tutor text.
//!
//! The tutor can only propose. The stream parser takes each tag out of the visible text, and
//! the server checks it against the allowlist. Only `kind` and `id` attributes are permitted.

use std::collections::HashMap;

const OPEN: &str = "<understando-action";

static ATTR: std::sync::LazyLock<regex::Regex> =
    std::sync::LazyLock::new(|| regex::Regex::new(r#"([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*"([^"]*)""#).unwrap());

#[derive(Debug, Clone)]
pub struct Tag {
    pub raw: String,
    pub attrs: HashMap<String, String>,
    pub extra: Vec<String>,
}

/// Parse the inside of one tag. Attributes other than kind and id go to `extra`.
pub fn parse_tag(raw: &str) -> Tag {
    let mut attrs = HashMap::new();
    let mut extra = Vec::new();
    for c in ATTR.captures_iter(raw) {
        let k = c[1].to_string();
        if k == "kind" || k == "id" {
            attrs.insert(k, c[2].to_string());
        } else {
            extra.push(k);
        }
    }
    Tag { raw: raw.chars().take(300).collect(), attrs, extra }
}

#[derive(Default)]
pub struct TagStream {
    pending: String,
    inside: bool,
    tag: String,
}

pub enum Piece {
    Text(String),
    Tag(Tag),
}

impl TagStream {
    pub fn push(&mut self, text: &str, out: &mut Vec<Piece>) {
        self.pending.push_str(text);
        self.drain(false, out);
    }

    pub fn finish(&mut self, out: &mut Vec<Piece>) {
        self.drain(true, out);
        if !self.pending.is_empty() {
            out.push(Piece::Text(std::mem::take(&mut self.pending)));
        }
        self.tag.clear();
        self.inside = false;
    }

    fn drain(&mut self, last: bool, out: &mut Vec<Piece>) {
        loop {
            if self.pending.is_empty() {
                return;
            }
            if self.inside {
                match self.pending.find('>') {
                    Some(end) => {
                        self.tag.push_str(&self.pending[..end]);
                        self.pending.drain(..=end);
                        self.inside = false;
                        let raw = std::mem::take(&mut self.tag);
                        // A closing tag after a non-self-closing open tag is dropped.
                        if self.pending.starts_with("</understando-action>") {
                            self.pending.drain(.."</understando-action>".len());
                        }
                        if raw.len() <= 2000 {
                            out.push(Piece::Tag(parse_tag(&raw)));
                        }
                        continue;
                    }
                    None => {
                        if self.tag.len() + self.pending.len() > 2000 || last {
                            self.pending.clear();
                            self.tag.clear();
                            self.inside = false;
                            return;
                        }
                        self.tag.push_str(&std::mem::take(&mut self.pending));
                        return;
                    }
                }
            }
            match self.pending.find(OPEN) {
                Some(at) => {
                    if at > 0 {
                        out.push(Piece::Text(self.pending[..at].to_string()));
                    }
                    self.pending.drain(..at + OPEN.len());
                    self.inside = true;
                }
                None => {
                    if last {
                        return;
                    }
                    // Hold back a tail that could be the start of a tag.
                    let mut held = 0;
                    for n in 1..OPEN.len() {
                        if n <= self.pending.len() && self.pending.is_char_boundary(self.pending.len() - n) && self.pending.ends_with(&OPEN[..n]) {
                            held = n;
                        }
                    }
                    let safe = self.pending.len() - held;
                    if safe > 0 {
                        out.push(Piece::Text(self.pending[..safe].to_string()));
                        self.pending.drain(..safe);
                    }
                    return;
                }
            }
        }
    }
}

/// Take every tag out of a full text, for the saved answer.
pub fn strip_tags(text: &str) -> String {
    let mut s = TagStream::default();
    let mut out = Vec::new();
    s.push(text, &mut out);
    s.finish(&mut out);
    out.into_iter()
        .filter_map(|p| match p {
            Piece::Text(t) => Some(t),
            Piece::Tag(_) => None,
        })
        .collect()
}
