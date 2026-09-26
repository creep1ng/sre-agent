use sre_agent_core::openrouter_output::{select_text, ContentFact, MessageFact, TextPlan};

fn plan(indices: Vec<(usize, usize)>) -> TextPlan {
    TextPlan {
        indices,
        separator: "\n",
    }
}

fn content(kind: &str, is_text: bool) -> ContentFact {
    ContentFact {
        kind: Some(kind.into()),
        is_text,
    }
}

fn message(kind: &str, role: &str, status: &str, contents: Vec<ContentFact>) -> MessageFact {
    MessageFact {
        kind: Some(kind.into()),
        role: Some(role.into()),
        status: Some(status.into()),
        contents: Some(contents),
    }
}

#[test]
fn root_requires_completed_status_and_list() {
    let messages = vec![message(
        "message",
        "assistant",
        "completed",
        vec![content("output_text", true)],
    )];
    assert_eq!(
        select_text(Some("completed"), Some(&messages)),
        Some(plan(vec![(0, 0)]))
    );
    assert_eq!(select_text(Some("in_progress"), Some(&messages)), None);
    assert_eq!(select_text(Some("completed"), None), None);
}

#[test]
fn selects_only_completed_assistant_text_in_order() {
    let messages = vec![
        message(
            "message",
            "user",
            "completed",
            vec![content("output_text", true)],
        ),
        message(
            "message",
            "assistant",
            "in_progress",
            vec![content("output_text", true)],
        ),
        message(
            "reasoning",
            "assistant",
            "completed",
            vec![content("output_text", true)],
        ),
        message(
            "message",
            "assistant",
            "completed",
            vec![
                content("output_text", false),
                content("output_text", true),
                content("refusal", true),
            ],
        ),
        message(
            "message",
            "assistant",
            "completed",
            vec![content("output_text", true)],
        ),
    ];
    assert_eq!(
        select_text(Some("completed"), Some(&messages)),
        Some(plan(vec![(3, 1), (4, 0)]))
    );
}

#[test]
fn empty_text_counts_as_selected_but_no_qualifying_parts_reject() {
    let one = vec![message(
        "message",
        "assistant",
        "completed",
        vec![content("output_text", true)],
    )];
    let two = vec![message(
        "message",
        "assistant",
        "completed",
        vec![content("output_text", true), content("output_text", true)],
    )];
    let none = vec![message(
        "message",
        "assistant",
        "completed",
        vec![content("output_text", false)],
    )];
    assert_eq!(
        select_text(Some("completed"), Some(&one)),
        Some(plan(vec![(0, 0)]))
    );
    assert_eq!(
        select_text(Some("completed"), Some(&two)),
        Some(plan(vec![(0, 0), (0, 1)]))
    );
    assert_eq!(select_text(Some("completed"), Some(&none)), None);
}
