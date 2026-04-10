#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import write_json
from scripts.constants import DEFAULT_TOP_K
from scripts.rec5_api import (
    build_api_request,
    call_rec5_api,
    normalize_rec5_paper,
    resolve_rec5_url,
    resolve_token,
)
from scripts.render_feishu_messages import render_feishu_messages


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _stage_error(stage: str, detail: Any) -> RuntimeError:
    compact = _clean_text(str(detail)) or "unknown_error"
    return RuntimeError(f"{stage}_failed:{compact}")


def _format_papers_as_markdown(papers: list[dict[str, Any]], profile_topics: list[str]) -> str:
    """Render recommended papers as Markdown text for non-Feishu channels."""
    lines: list[str] = []
    topic_hint = " / ".join(profile_topics[:5]) if profile_topics else ""
    header = f"为你推荐 {len(papers)} 篇相关论文"
    if topic_hint:
        header += f"（研究方向：{topic_hint}）"
    lines.append(header)

    for idx, paper in enumerate(papers, start=1):
        lines.append("")
        lines.append("---")
        lines.append("")
        title = _clean_text(paper.get("title") or "")
        url = _clean_text(paper.get("aminer_paper_url") or paper.get("abs_url") or "")
        title_line = f"**{idx}. [{title}]({url})**" if url else f"**{idx}. {title}**"
        lines.append(title_line)

        year = paper.get("year")
        keywords = paper.get("keywords") or []
        authors = paper.get("authors") or []
        summary = _clean_text(paper.get("summary") or "")

        meta_parts: list[str] = []
        if year:
            meta_parts.append(f"年份：{year}")
        if keywords:
            meta_parts.append(f"关键词：{' / '.join(str(k) for k in keywords[:5])}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))

        if authors:
            author_str = "、".join(str(a) for a in authors[:6])
            if len(authors) > 6:
                author_str += " et al."
            lines.append(f"作者：{author_str}")

        if summary:
            truncated = summary if len(summary) <= 300 else summary[:300].rstrip() + "…"
            lines.append("")
            lines.append(truncated)

    return "\n".join(lines)


def _topics_from_paper_titles(paper_titles: list[str]) -> list[str]:
    """Extract simple topic hints from paper titles when no explicit topics provided."""
    topics: list[str] = []
    seen: set[str] = set()
    for title in paper_titles:
        cleaned = _clean_text(title)
        if not cleaned:
            continue
        candidate = cleaned.split(":")[0].strip() if ":" in cleaned else cleaned
        if candidate and candidate.casefold() not in seen and len(candidate) <= 80:
            seen.add(candidate.casefold())
            topics.append(candidate)
    return topics[:5]


def _run_python(script_path: Path, args: list[str]) -> None:
    completed = subprocess.run([sys.executable, str(script_path), *args], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"{script_path.name} failed"
        raise RuntimeError(detail)


def run_pipeline(
    *,
    base_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
    aminer_user_id: str,
    topics: list[str],
    scholar_name: str,
    scholar_org: str,
    paper_titles: list[str],
    papers_file: str,
    free_text: str,
    target: str,
    account_id: str,
    skip_dispatch: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    if target.strip() and account_id.strip():
        write_json(output_dir / "manual_reply_route.json", {"target": target.strip(), "accountId": account_id.strip()})

    token = resolve_token(config)
    if not token:
        raise _stage_error("auth", "AMINER_API_KEY is not set")

    # Derive topics from paper_titles when no other topics or author signal provided
    all_topics = list(topics)
    if paper_titles and not all_topics and not scholar_name and not aminer_user_id:
        all_topics = _topics_from_paper_titles(paper_titles)

    search_config = config.get("search") if isinstance(config.get("search"), dict) else {}
    size = max(1, min(int(search_config.get("top_k") or DEFAULT_TOP_K), 20))

    api_request = build_api_request(
        aminer_author_id=aminer_user_id,
        author_name=scholar_name,
        author_org=scholar_org,
        topics=all_topics,
        size=size,
    )

    try:
        raw_papers = call_rec5_api(api_request, token=token, url=resolve_rec5_url(config))
    except Exception as exc:
        raise _stage_error("recall", exc) from exc

    if not raw_papers:
        raise _stage_error("recall", "no_papers_returned")

    papers = [normalize_rec5_paper(p) for p in raw_papers]

    profile_topics = all_topics or ([scholar_name] if scholar_name else [])
    summarized_payload = {
        "status": "success",
        "profile_topics": profile_topics,
        "profile_name": scholar_name or "",
        "profile_source": "scholar_path" if (aminer_user_id or scholar_name) else "topic_path",
        "papers": papers,
    }

    mode = "scholar_path" if (aminer_user_id or scholar_name) else "topic_path"

    write_json(output_dir / "request_context.json", {
        "aminer_user_id": aminer_user_id,
        "topics": topics,
        "scholar_name": scholar_name,
        "scholar_org": scholar_org,
        "paper_titles": paper_titles,
        "papers_file": papers_file,
        "free_text": free_text,
        "api_request": api_request,
    })

    summarized_path = output_dir / "papers_summarized.json"
    write_json(summarized_path, summarized_payload)

    # Non-Feishu channels (WeChat, Telegram, pure OpenClaw conversation, etc.):
    # target is empty → skip card dispatch and return Markdown text instead.
    has_feishu_target = bool(target.strip()) and not skip_dispatch
    if not has_feishu_target:
        markdown_text = _format_papers_as_markdown(papers, profile_topics)
        return {
            "status": "success",
            "summarized_path": str(summarized_path),
            "final_response": "TEXT",
            "reply_text": markdown_text,
            "mode": mode,
            "paper_count": len(papers),
        }

    messages_path = output_dir / "feishu_messages.json"
    try:
        messages_payload = render_feishu_messages(summarized_payload)
    except Exception as exc:
        raise _stage_error("render", exc) from exc
    write_json(messages_path, messages_payload)

    dispatch_args = ["--messages", str(messages_path), "--account-id", account_id, "--target", target.strip()]
    try:
        _run_python(base_dir / "scripts" / "dispatch_feishu_messages.py", dispatch_args)
    except Exception as exc:
        raise _stage_error("dispatch", exc) from exc

    return {
        "status": "success",
        "summarized_path": str(summarized_path),
        "messages_path": str(messages_path),
        "final_response": "NO_REPLY",
        "mode": mode,
        "paper_count": len(papers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run aminer-daily-paper pipeline via rec5 API.")
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "outputs")
    parser.add_argument("--aminer-user-id", default="")
    parser.add_argument("--topics", nargs="*", default=[])
    parser.add_argument("--scholar-name", default="")
    parser.add_argument("--scholar-org", default="")
    parser.add_argument("--paper-title", action="append", dest="paper_titles", default=[])
    parser.add_argument("--papers-file", default="")
    parser.add_argument("--free-text", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--account", default="main")
    parser.add_argument("--skip-dispatch", action="store_true")
    args = parser.parse_args()

    resolved_base_dir = args.base_dir.resolve()
    resolved_config = args.config.resolve() if args.config else None
    config = _load_yaml(resolved_config)

    result = run_pipeline(
        base_dir=resolved_base_dir,
        output_dir=args.output_dir.resolve(),
        config=config,
        aminer_user_id=args.aminer_user_id,
        topics=list(args.topics or []),
        scholar_name=args.scholar_name,
        scholar_org=args.scholar_org,
        paper_titles=list(args.paper_titles or []),
        papers_file=args.papers_file,
        free_text=args.free_text,
        target=args.target,
        account_id=args.account,
        skip_dispatch=args.skip_dispatch,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
