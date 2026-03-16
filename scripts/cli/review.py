"""
Autoflow CLI - Review Commands

Manage review approval state for specifications.

Usage:
    from scripts.cli.review import add_subparser, approve_spec

    # Register review commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    approve_spec(args)
"""

from __future__ import annotations

import argparse
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    compute_spec_hash,
    load_review_state,
    now_stamp,
    print_json,
    record_event,
    review_status_summary,
    save_review_state,
)


def approve_spec(args: argparse.Namespace) -> None:
    """
    Approve a spec and record approval metadata.

    Marks the spec as approved, capturing the approver's identity, approval timestamp,
    and a hash of the spec content at the time of approval. Increments the review
    count and clears any previous invalidation status. Records the approval in the
    event log and displays the updated review status.

    The spec hash ensures that if the spec content changes after approval, the
    approval can be detected as invalid.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to approve
            - approved_by: Username or identifier of the approver

    Side Effects:
        - Updates review_state.json with approval information
        - Appends approval event to events.jsonl
        - Prints review status summary as JSON to stdout
    """
    state = load_review_state(args.spec)
    state["approved"] = True
    state["approved_by"] = args.approved_by
    state["approved_at"] = now_stamp()
    state["spec_hash"] = compute_spec_hash(args.spec)
    state["review_count"] = state.get("review_count", 0) + 1
    state["invalidated_at"] = ""
    state["invalidated_reason"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.approved", {"approved_by": args.approved_by})
    print_json(review_status_summary(args.spec))


def invalidate_review(args: argparse.Namespace) -> None:
    """
    Invalidate a spec's approval status.

    Marks a previously approved spec as no longer approved, recording the invalidation
    timestamp, reason for invalidation, and clearing the spec hash. This is typically
    used when the spec has changed in a way that requires re-review, or when an
    approval needs to be rescinded due to new information or requirements.

    The spec hash is cleared to ensure that the approval is no longer considered valid,
    even if the spec content happens to match the previous hash.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to invalidate
            - reason: Explanation for why the approval is being invalidated

    Side Effects:
        - Updates review_state.json with invalidation information
        - Appends invalidation event to events.jsonl
        - Prints review status summary as JSON to stdout
    """
    state = load_review_state(args.spec)
    state["approved"] = False
    state["invalidated_at"] = now_stamp()
    state["invalidated_reason"] = args.reason
    state["spec_hash"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.invalidated", {"reason": args.reason})
    print_json(review_status_summary(args.spec))


def show_review_status(args: argparse.Namespace) -> None:
    """
    Display the current review status for a spec.

    Outputs a comprehensive summary of the spec's review state, including approval
    status, validity, timestamps, reviewer information, and feedback counts. The
    status is synchronously computed to check for spec changes since approval.

    The output includes whether the spec is approved, whether the approval is still
    valid (i.e., the spec hasn't changed), the number of reviews completed, and
    the number of feedback items received.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to check

    Side Effects:
        - Prints review status summary as JSON to stdout

    Output Format:
        JSON object with the following keys:
            - approved: Whether the spec is currently approved
            - valid: Whether approval is still valid (approved and hash matches)
            - approved_by: Username of approver (if approved)
            - approved_at: Timestamp of approval (if approved)
            - review_count: Number of reviews completed
            - feedback_count: Number of feedback items
            - spec_changed: Whether spec has changed since approval
            - invalidated_at: Timestamp when approval was invalidated (if applicable)
            - invalidated_reason: Reason for invalidation (if applicable)
    """
    print_json(review_status_summary(args.spec))


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register review command subparsers with the argument parser.

    This function is called during CLI initialization to add all review-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    review_status_cmd = sub.add_parser("review-status", help="show hash-based review approval status")
    review_status_cmd.add_argument("--spec", required=True)
    review_status_cmd.set_defaults(func=show_review_status)

    approve_cmd = sub.add_parser("approve-spec", help="approve the current spec/task contract hash")
    approve_cmd.add_argument("--spec", required=True)
    approve_cmd.add_argument("--approved-by", default="user")
    approve_cmd.set_defaults(func=approve_spec)

    invalidate_cmd = sub.add_parser("invalidate-review", help="manually invalidate approval state")
    invalidate_cmd.add_argument("--spec", required=True)
    invalidate_cmd.add_argument("--reason", default="manual_invalidation")
    invalidate_cmd.set_defaults(func=invalidate_review)
