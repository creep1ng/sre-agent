//! Selection policy for completed OpenRouter assistant output text.

/// JSON-shaped facts supplied by the Python boundary, without transferring text bytes.
pub struct ContentFact {
    pub kind: Option<String>,
    pub is_text: bool,
}

pub struct MessageFact {
    pub kind: Option<String>,
    pub role: Option<String>,
    pub status: Option<String>,
    pub contents: Option<Vec<ContentFact>>,
}

#[derive(Debug, Eq, PartialEq)]
pub struct TextPlan {
    pub indices: Vec<(usize, usize)>,
    pub separator: &'static str,
}

pub fn status_completed(status: Option<&str>) -> bool {
    status == Some("completed")
}

pub fn root_accepts(status: Option<&str>, output_is_list: bool) -> bool {
    status_completed(status) && output_is_list
}

pub fn message_kind_relevant(kind: Option<&str>) -> bool {
    kind == Some("message")
}

pub fn message_role_relevant(role: Option<&str>) -> bool {
    role == Some("assistant")
}

pub fn content_kind_relevant(kind: Option<&str>) -> bool {
    kind == Some("output_text")
}

/// Return ordered message/content indices, or reject when no text qualifies.
/// A single empty string qualifies; two empty strings remain two selections.
pub fn select_text(status: Option<&str>, messages: Option<&[MessageFact]>) -> Option<TextPlan> {
    if !root_accepts(status, messages.is_some()) {
        return None;
    }
    let messages = messages?;
    let mut selected = Vec::new();
    for (message_index, message) in messages.iter().enumerate() {
        if !message_kind_relevant(message.kind.as_deref())
            || !message_role_relevant(message.role.as_deref())
            || !status_completed(message.status.as_deref())
        {
            continue;
        }
        let Some(contents) = &message.contents else {
            continue;
        };
        for (content_index, content) in contents.iter().enumerate() {
            if content_kind_relevant(content.kind.as_deref()) && content.is_text {
                selected.push((message_index, content_index));
            }
        }
    }
    (!selected.is_empty()).then_some(TextPlan {
        indices: selected,
        separator: "\n",
    })
}
