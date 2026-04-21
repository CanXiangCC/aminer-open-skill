#!/usr/bin/env python3
"""Render and dispatch enriched papers as Feishu cards.

Called by the claw after paper enrichment. Reads papers_summarized.json,
renders Feishu card messages, and dispatches them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import write_json
from scripts.render_feishu_messages import render_feishu_messages
from scripts.dispatch_feishu_messages import dispatch_messages


def dispatch_papers(
    *,
    base_dir: Path,
    papers_path: Path,
    target: str,
    account_id: str = "default",
) -> dict[str, Any]:
    if not papers_path.exists():
        raise FileNotFoundError(f"papers_summarized.json not found: {papers_path}")

    payload = json.loads(papers_path.read_text(encoding="utf-8"))
    output_dir = papers_path.parent

    # Write manual reply route for dispatch
    if target.strip() and account_id.strip():
        write_json(output_dir / "manual_reply_route.json", {
            "target": target.strip(),
            "accountId": account_id.strip(),
        })

    # Render Feishu card messages
    messages_payload = render_feishu_messages(payload)
    messages_path = output_dir / "feishu_messages.json"
    write_json(messages_path, messages_payload)

    # Dispatch
    result = dispatch_messages(
        messages_path=messages_path,
        target=target.strip(),
        account_id=account_id,
    )

    return {
        "status": "success",
        "messages_path": str(messages_path),
        "final_response": "NO_REPLY",
        "paper_count": len(payload.get("papers") or []),
        "dispatch": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render and dispatch enriched papers as Feishu cards.")
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--papers-path", type=Path, required=True, help="Path to papers_summarized.json")
    parser.add_argument("--target", required=True, help="Feishu delivery target (e.g. user:ou_xxx)")
    parser.add_argument("--account", default="default", help="Feishu account ID")
    args = parser.parse_args()

    result = dispatch_papers(
        base_dir=args.base_dir.resolve(),
        papers_path=args.papers_path.resolve(),
        target=args.target,
        account_id=args.account,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
