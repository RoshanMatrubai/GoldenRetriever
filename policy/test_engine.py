import pytest

from policy.engine import (
    derive_scope,
    is_action_in_scope,
    list_service_actions,
    list_supported_services,
)


# ---------------------------------------------------------------------------
# Amazon — the flagship demo service
# ---------------------------------------------------------------------------

def test_price_compare_grants_read_and_search_only():
    """CLAUDE.md demo: 'compare prices' → [read, search], NO purchase."""
    scope = derive_scope("Amazon", "compare prices on these 3 items")
    assert "search" in scope
    assert "read" in scope
    assert "purchase" not in scope
    assert "checkout" not in scope
    assert "delete" not in scope


def test_explicit_buy_grants_purchase():
    scope = derive_scope("Amazon", "buy the cheapest laptop under $500")
    assert "purchase" in scope


def test_buy_also_grants_read_prerequisites():
    """Purchasing requires search + read (coherence prerequisites)."""
    scope = derive_scope("Amazon", "buy me a coffee maker")
    assert "purchase" in scope
    assert "search" in scope
    assert "read" in scope


def test_find_product_no_purchase():
    scope = derive_scope("Amazon", "find a good running shoe under $100")
    assert "search" in scope
    assert "purchase" not in scope


def test_order_grants_purchase():
    scope = derive_scope("Amazon", "order these groceries for delivery")
    assert "purchase" in scope


def test_checkout_grants_purchase():
    scope = derive_scope("Amazon", "checkout my cart")
    assert "purchase" in scope


def test_cancel_order_grants_delete():
    scope = derive_scope("Amazon", "cancel my order for the headphones")
    assert "delete" in scope


def test_browse_grants_browse():
    scope = derive_scope("Amazon", "browse the electronics section")
    assert "browse" in scope
    assert "purchase" not in scope


def test_write_review_grants_review():
    scope = derive_scope("Amazon", "write review for the keyboard I bought")
    assert "review" in scope


def test_compare_does_not_grant_write():
    scope = derive_scope("Amazon", "compare prices on these 3 items")
    assert "write" not in scope
    assert "review" not in scope
    assert "delete" not in scope


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

def test_check_email_grants_email_read_only():
    scope = derive_scope("Google", "check my email inbox")
    assert "email_read" in scope
    assert "email_send" not in scope


def test_send_email_grants_email_send_and_read():
    scope = derive_scope("Google", "send email to john@example.com about the report")
    assert "email_send" in scope
    assert "email_read" in scope  # prerequisite


def test_calendar_read_only():
    scope = derive_scope("Google", "what meetings do I have this week?")
    assert "calendar_read" in scope
    assert "calendar_write" not in scope


def test_schedule_meeting_grants_calendar_write_and_read():
    scope = derive_scope("Google", "schedule meeting with the design team tomorrow")
    assert "calendar_write" in scope
    assert "calendar_read" in scope  # prerequisite


def test_open_doc_grants_drive_read():
    scope = derive_scope("Google", "open the Q4 report doc from Drive")
    assert "drive_read" in scope
    assert "drive_write" not in scope


def test_create_doc_grants_drive_write_and_read():
    scope = derive_scope("Google", "create a new document for the project proposal")
    assert "drive_write" in scope
    assert "drive_read" in scope  # prerequisite


def test_google_search():
    scope = derive_scope("Google", "search for Python tutorials")
    assert "search" in scope
    assert "email_send" not in scope
    assert "calendar_write" not in scope


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def test_read_repo_no_write():
    scope = derive_scope("GitHub", "look at the open issues in this repo")
    assert "issue_read" in scope
    assert "issue_write" not in scope
    assert "repo_write" not in scope


def test_create_issue_grants_issue_write_and_read():
    scope = derive_scope("GitHub", "create issue for the login bug")
    assert "issue_write" in scope
    assert "issue_read" in scope  # prerequisite


def test_review_pr_read_only():
    scope = derive_scope("GitHub", "review the pull request diff")
    assert "pr_read" in scope
    assert "pr_write" not in scope


def test_open_pr_grants_pr_write_and_read():
    scope = derive_scope("GitHub", "open pr for the feature branch")
    assert "pr_write" in scope
    assert "pr_read" in scope   # prerequisite
    assert "repo_read" in scope  # prerequisite


def test_check_release_version():
    scope = derive_scope("GitHub", "check the latest release version")
    assert "release_read" in scope
    assert "repo_write" not in scope


def test_push_code_grants_repo_write():
    scope = derive_scope("GitHub", "push my changes to the main branch")
    assert "repo_write" in scope
    assert "repo_read" in scope  # prerequisite


def test_delete_branch():
    scope = derive_scope("GitHub", "drop branch old-feature after merge")
    assert "delete" in scope


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

def test_read_slack_channel():
    scope = derive_scope("Slack", "check the #general channel for announcements")
    assert "channel_read" in scope
    assert "send_message" not in scope


def test_send_slack_message():
    scope = derive_scope("Slack", "send a message to the team about the outage")
    assert "send_message" in scope
    assert "channel_read" in scope  # prerequisite


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------

def test_browse_jira_board():
    scope = derive_scope("Jira", "show me the sprint board")
    assert "issue_read" in scope
    assert "issue_write" not in scope


def test_create_jira_ticket():
    scope = derive_scope("Jira", "create issue for the auth regression")
    assert "issue_write" in scope
    assert "issue_read" in scope  # prerequisite


# ---------------------------------------------------------------------------
# Unknown / edge cases
# ---------------------------------------------------------------------------

def test_unknown_service_returns_empty():
    scope = derive_scope("Salesforce", "read the contacts list")
    assert scope == []


def test_empty_task_returns_empty():
    scope = derive_scope("Amazon", "")
    assert scope == []


def test_unrelated_task_returns_empty():
    scope = derive_scope("Amazon", "the quick brown fox jumps over the lazy dog")
    assert scope == []


def test_service_name_case_insensitive():
    scope1 = derive_scope("amazon", "compare prices")
    scope2 = derive_scope("AMAZON", "compare prices")
    scope3 = derive_scope("Amazon", "compare prices")
    assert scope1 == scope2 == scope3


def test_scope_is_sorted():
    scope = derive_scope("Amazon", "buy the cheapest item")
    assert scope == sorted(scope)


# ---------------------------------------------------------------------------
# is_action_in_scope
# ---------------------------------------------------------------------------

def test_action_in_scope():
    assert is_action_in_scope("search", ["read", "search"])
    assert not is_action_in_scope("purchase", ["read", "search"])


def test_action_not_in_empty_scope():
    assert not is_action_in_scope("search", [])


# ---------------------------------------------------------------------------
# list_service_actions / list_supported_services
# ---------------------------------------------------------------------------

def test_list_amazon_actions():
    actions = list_service_actions("Amazon")
    assert "search" in actions
    assert "purchase" in actions
    assert "delete" in actions


def test_list_actions_unknown_service():
    assert list_service_actions("FakeService") == []


def test_list_supported_services():
    services = list_supported_services()
    assert "amazon" in services
    assert "google" in services
    assert "github" in services
    assert "slack" in services
    assert "jira" in services


def test_word_boundary_no_false_positive():
    """'buy' must not match inside 'subway' or 'buying guide'... actually buying should match."""
    scope = derive_scope("Amazon", "I took the subway to work")
    assert "purchase" not in scope


def test_multi_word_trigger_matches():
    scope = derive_scope("Amazon", "add to cart and checkout later")
    assert "purchase" in scope


def test_send_email_multiword_trigger():
    scope = derive_scope("Google", "send email to the client")
    assert "email_send" in scope
