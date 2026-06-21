"""
Task-to-scope policy engine.

Given a service name and a natural-language task, derives the minimum
permission allow-list the agent needs.  Conservative default: deny anything
not clearly signalled by the task text.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Action catalogs
#
# Structure: service → action → (trigger_phrases, is_destructive)
#
# is_destructive=False  — read/browse actions; granted on any trigger match
# is_destructive=True   — write/mutate actions; triggers are explicit
#                         intent verbs so the bar is naturally higher
# ---------------------------------------------------------------------------
_CATALOGS: dict[str, dict[str, tuple[list[str], bool]]] = {
    "amazon": {
        "search":   (["search", "find", "look", "compare", "price", "browse",
                      "check", "product", "item", "cheapest", "list"], False),
        "read":     (["read", "view", "compare", "price", "detail", "info",
                      "check", "see", "result", "rating", "review",
                      "product", "item", "describe", "description"], False),
        "browse":   (["browse", "navigate", "visit", "explore", "page"], False),
        "purchase": (["buy", "purchase", "order", "checkout", "add to cart",
                      "cart", "pay", "payment", "place order", "acquire",
                      "transaction"], True),
        "review":   (["write review", "post review", "submit review",
                      "leave review", "rate product"], True),
        "write":    (["create listing", "update listing", "add listing",
                      "edit listing", "modify listing"], True),
        "delete":   (["delete", "cancel", "remove", "return item",
                      "refund"], True),
    },
    "google": {
        "search":         (["search", "find", "look", "query", "google",
                            "browse", "research", "discover"], False),
        "read":           (["read", "view", "open", "see", "check", "get",
                            "access", "retrieve"], False),
        "email_read":     (["email", "mail", "inbox", "read email",
                            "check email", "message", "gmail", "unread"], False),
        "calendar_read":  (["calendar", "schedule", "meeting", "event",
                            "appointment", "availability", "when am i",
                            "my day", "agenda"], False),
        "drive_read":     (["drive", "file", "document", "doc", "sheet",
                            "slides", "spreadsheet", "read file",
                            "open file", "gdoc"], False),
        "email_send":     (["send email", "reply to", "compose", "email to",
                            "write email", "draft email", "respond to email",
                            "forward email", "reply email"], True),
        "calendar_write": (["create event", "schedule meeting", "book meeting",
                            "add event", "set up meeting", "add to calendar",
                            "invite to meeting", "new event"], True),
        "drive_write":    (["create file", "upload", "write doc", "edit file",
                            "save to drive", "create document",
                            "update file", "new document"], True),
    },
    "github": {
        "repo_read":    (["repo", "repository", "code", "file", "commit",
                          "branch", "source", "codebase", "read", "view",
                          "check"], False),
        "issue_read":   (["issue", "bug", "ticket", "problem", "error",
                          "open issue", "closed issue", "backlog"], False),
        "pr_read":      (["pr", "pull request", "review", "diff",
                          "change", "patch", "merge request"], False),
        "release_read": (["release", "version", "changelog", "tag",
                          "latest release"], False),
        "issue_write":  (["create issue", "open issue", "file bug",
                          "report bug", "new issue", "submit issue",
                          "add issue"], True),
        "pr_write":     (["create pr", "open pr", "submit pr",
                          "new pull request", "merge pr",
                          "push changes", "raise pr"], True),
        "repo_write":   (["push", "commit", "write file", "modify file",
                          "create file", "update code", "edit code",
                          "add file"], True),
        "delete":       (["delete", "remove", "close issue", "close pr",
                          "archive", "drop branch"], True),
    },
    "slack": {
        "read":          (["read", "view", "check", "see", "search",
                           "find", "browse", "look"], False),
        "channel_read":  (["channel", "message", "chat", "conversation",
                           "thread", "dm", "inbox", "notification",
                           "mention", "slack"], False),
        "send_message":  (["send", "post message", "message", "reply",
                           "respond", "dm", "notify", "alert", "write",
                           "ping"], True),
        "create_channel":(["create channel", "new channel", "make channel",
                           "set up channel"], True),
        "delete":        (["delete message", "remove message",
                           "archive channel", "kick user"], True),
    },
    "jira": {
        "issue_read":   (["read", "view", "check", "see", "find", "search",
                          "browse", "issue", "ticket", "task", "story",
                          "bug", "sprint", "board", "backlog"], False),
        "issue_write":  (["create issue", "new ticket", "file bug",
                          "update issue", "assign ticket", "resolve",
                          "close ticket", "edit issue", "add comment",
                          "transition issue"], True),
        "delete":       (["delete issue", "remove ticket", "archive"], True),
    },
}

# Read prerequisites auto-added when a destructive action is granted.
# Ensures an agent that can purchase can also search/read (coherent scope).
_PREREQUISITES: dict[str, list[str]] = {
    "purchase":       ["search", "read"],
    "review":         ["read"],
    "write":          ["read"],
    "email_send":     ["email_read"],
    "calendar_write": ["calendar_read"],
    "drive_write":    ["drive_read"],
    "pr_write":       ["pr_read", "repo_read"],
    "issue_write":    ["issue_read"],
    "repo_write":     ["repo_read"],
    "send_message":   ["channel_read"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def derive_scope(service: str, task: str) -> list[str]:
    """
    Derive the minimum permission allow-list for a service + task.
    Returns [] for unknown services or tasks that match no actions.
    """
    catalog = _CATALOGS.get(service.lower())
    if not catalog:
        return []

    task_lower = task.lower()
    granted: set[str] = set()

    for action, (triggers, _is_destructive) in catalog.items():
        if _any_trigger_matches(task_lower, triggers):
            granted.add(action)

    # Add coherence prerequisites for any destructive action that was granted
    for action in list(granted):
        for prereq in _PREREQUISITES.get(action, []):
            if prereq in catalog:
                granted.add(prereq)

    return sorted(granted)


def list_service_actions(service: str) -> list[str]:
    """All possible actions for a service (shown in UI / MCP tool description)."""
    return sorted(_CATALOGS.get(service.lower(), {}).keys())


def list_supported_services() -> list[str]:
    """Services with known action catalogs."""
    return sorted(_CATALOGS.keys())


def is_action_in_scope(action: str, scope: list[str]) -> bool:
    """Check whether a requested action is permitted by the issued scope."""
    return action in scope


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _any_trigger_matches(task: str, triggers: list[str]) -> bool:
    return any(_phrase_in_text(phrase, task) for phrase in triggers)


def _phrase_in_text(phrase: str, text: str) -> bool:
    """
    Word-boundary-aware search.
    - Single words: left-boundary only, so 'meeting' matches 'meetings' and
      'buy' doesn't match 'subway'.
    - Multi-word phrases: full boundaries on both ends so 'open issue'
      doesn't match 'open issues'.
    """
    if " " in phrase:
        return bool(re.search(r"\b" + re.escape(phrase) + r"\b", text))
    # Left-boundary only handles plurals/verb-forms
    return bool(re.search(r"\b" + re.escape(phrase), text))
