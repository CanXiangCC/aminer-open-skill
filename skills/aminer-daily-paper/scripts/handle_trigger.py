#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


FIELD_LABELS = {
    "aminer_author_id": ["aminer_author_id"],
    "topics": ["topics", "topic"],
    "scholar_name": ["scholar", "author", "name"],
    "scholar_org": ["org", "organization", "affiliation"],
    "paper_titles": ["paper", "papers"],
    "papers_file": ["papers_file", "source_file", "profile_file"],
    "language_sort": ["language_sort"],
    "size": ["size"],
}

ALLOWED_QUERY_MODES = {"personalized", "topic", "scholar", "author"}
ALLOWED_LANGUAGE_SORT = {"zh", "en"}
ALLOWED_PAPERS_FILE_SUFFIXES = {".json"}
MAX_TOPICS = 8
MAX_TOPIC_LENGTH = 80
MAX_PAPER_TITLES = 8
MAX_PAPER_TITLE_LENGTH = 300
MAX_SCHOLAR_NAME_LENGTH = 80
MAX_SCHOLAR_ORG_LENGTH = 160


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_topics(text: str) -> list[str]:
    pieces = re.split(r"[,，;/；、\n]+", text)
    topics: list[str] = []
    for piece in pieces:
        topic = _clean_text(piece)
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _split_papers(text: str) -> list[str]:
    pieces = re.split(r"[|\n;；]+", text)
    papers: list[str] = []
    for piece in pieces:
        paper = _clean_text(piece)
        if paper and paper not in papers:
            papers.append(paper)
    return papers


def _extract_command_text(raw_text: str) -> str:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        match = re.search(r"(/(?:skill\s+)?aminer[-_]dp\b.*)$", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return str(raw_text or "")


def _capture_field(command_body: str, field_name: str) -> str:
    labels = FIELD_LABELS[field_name]
    all_labels = [re.escape(label) for values in FIELD_LABELS.values() for label in values]
    pattern = rf"(?:{'|'.join(re.escape(label) for label in labels)})\s*[:：]\s*(.+?)(?=\s*(?:{'|'.join(all_labels)})\s*[:：]|$)"
    match = re.search(pattern, command_body, flags=re.IGNORECASE | re.S)
    return _clean_text(match.group(1)) if match else ""


def _truncate_text(value: Any, max_length: int) -> str:
    cleaned = _clean_text(value)
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length].strip()


def _normalize_topics(values: list[Any]) -> list[str]:
    topics: list[str] = []
    for value in list(values or []):
        topic = _truncate_text(value, MAX_TOPIC_LENGTH)
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) >= MAX_TOPICS:
            break
    return topics


def _normalize_paper_titles(values: list[Any]) -> list[str]:
    paper_titles: list[str] = []
    for value in list(values or []):
        paper_title = _truncate_text(value, MAX_PAPER_TITLE_LENGTH)
        if paper_title and paper_title not in paper_titles:
            paper_titles.append(paper_title)
        if len(paper_titles) >= MAX_PAPER_TITLES:
            break
    return paper_titles


def _resolve_papers_file(base_dir: Path, path_text: str) -> str:
    cleaned = _clean_text(path_text)
    if not cleaned:
        return ""

    candidate = Path(cleaned).expanduser()
    resolved_base_dir = base_dir.resolve()
    resolved_candidate = (resolved_base_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_base_dir)
    except ValueError as exc:
        raise ValueError("papers_file_outside_base_dir") from exc

    if resolved_candidate.suffix.lower() not in ALLOWED_PAPERS_FILE_SUFFIXES:
        raise ValueError("unsupported_papers_file")
    return str(resolved_candidate)


def _parse_size(raw_size: Any) -> int:
    cleaned = _clean_text(raw_size)
    if not cleaned:
        return 0
    try:
        return max(1, min(int(cleaned), 20))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid_size") from exc


def _normalize_payload(payload: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    query_mode = _clean_text(payload.get("query_mode")).lower()
    if query_mode not in ALLOWED_QUERY_MODES:
        raise ValueError("invalid_query_mode")

    raw_uid = _clean_text(payload.get("aminer_author_id"))
    if raw_uid and not re.fullmatch(r"[0-9a-fA-F]{24}", raw_uid):
        raise ValueError("invalid_aminer_author_id")

    language_sort = _clean_text(payload.get("language_sort"))
    if language_sort and language_sort not in ALLOWED_LANGUAGE_SORT:
        raise ValueError("invalid_language_sort")

    normalized = {
        "query_mode": query_mode,
        "aminer_author_id": raw_uid,
        "topics": _normalize_topics(list(payload.get("topics") or [])),
        "scholar_name": _truncate_text(payload.get("scholar_name"), MAX_SCHOLAR_NAME_LENGTH),
        "scholar_org": _truncate_text(payload.get("scholar_org"), MAX_SCHOLAR_ORG_LENGTH),
        "paper_titles": _normalize_paper_titles(list(payload.get("paper_titles") or [])),
        "papers_file": _resolve_papers_file(base_dir, str(payload.get("papers_file") or "")),
        "language_sort": language_sort,
        "size": _parse_size(payload.get("size")),
    }

    if query_mode == "personalized":
        if any(
            [
                normalized["aminer_author_id"],
                normalized["topics"],
                normalized["scholar_name"],
                normalized["scholar_org"],
                normalized["paper_titles"],
                normalized["papers_file"],
            ]
        ):
            raise ValueError("personalized_mode_conflict")
        return normalized

    if query_mode == "topic" and not (normalized["topics"] or normalized["paper_titles"]):
        raise ValueError("topic_mode_requires_topics")

    if query_mode == "scholar" and not normalized["scholar_name"]:
        raise ValueError("scholar_mode_requires_name")

    if query_mode == "author" and not normalized["aminer_author_id"]:
        raise ValueError("author_mode_requires_aminer_author_id")

    return normalized


def _payload_from_structured_text(text: str) -> dict[str, Any]:
    command_text = _extract_command_text(text)
    normalized = _clean_text(command_text)
    is_trigger = bool(re.search(r"^/(skill\s+)?aminer[-_]dp\b", normalized, flags=re.IGNORECASE))
    if not is_trigger:
        raise ValueError("raw_natural_language_not_supported")

    body = re.sub(r"^/(skill\s+)?aminer[-_]dp\b", "", command_text, flags=re.IGNORECASE).strip()
    payload = {
        "query_mode": "personalized",
        "aminer_author_id": _capture_field(body, "aminer_author_id"),
        "topics": _split_topics(_capture_field(body, "topics")),
        "scholar_name": _capture_field(body, "scholar_name"),
        "scholar_org": _capture_field(body, "scholar_org"),
        "paper_titles": _split_papers(_capture_field(body, "paper_titles")),
        "papers_file": _capture_field(body, "papers_file"),
        "language_sort": _capture_field(body, "language_sort"),
        "size": _capture_field(body, "size"),
    }

    if payload["aminer_author_id"]:
        payload["query_mode"] = "author"
    elif payload["scholar_name"]:
        payload["query_mode"] = "scholar"
    elif payload["topics"] or payload["paper_titles"]:
        payload["query_mode"] = "topic"

    return payload


def _load_payload_from_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_config(base_dir: Path, config_path: Path | None) -> dict[str, Any]:
    if config_path and config_path.exists():
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    default_path = base_dir / "config.yaml"
    if default_path.exists():
        return yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
    return {}


def _run_pipeline(
    *,
    base_dir: Path,
    output_dir: Path,
    config_path: Path | None,
    aminer_author_id: str,
    topics: list[str],
    scholar_name: str,
    scholar_org: str,
    paper_titles: list[str],
    papers_file: str,
    language_sort: str,
    size: int,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(base_dir / "scripts" / "run_pipeline.py"),
        "--base-dir",
        str(base_dir),
        "--output-dir",
        str(output_dir),
    ]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    if aminer_author_id:
        command.extend(["--aminer-author-id", aminer_author_id])
    if language_sort:
        command.extend(["--language-sort", language_sort])
    if size > 0:
        command.extend(["--size", str(size)])
    if topics:
        command.extend(["--topics", *topics])
    if scholar_name:
        command.extend(["--scholar-name", scholar_name])
    if scholar_org:
        command.extend(["--scholar-org", scholar_org])
    for paper_title in paper_titles:
        command.extend(["--paper-title", paper_title])
    if papers_file:
        command.extend(["--papers-file", papers_file])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "run_pipeline failed"
        raise RuntimeError(detail)
    return json.loads(completed.stdout)


def _compact_pipeline_error(detail: str) -> str:
    text = _clean_text(detail)
    if not text:
        return "unknown_error"
    if "Traceback" not in text:
        return text
    lines = [line.strip() for line in str(detail or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("RuntimeError:"):
            return _clean_text(line.split("RuntimeError:", 1)[1])
    return _clean_text(lines[-1]) if lines else text


def _invalid_input_reply(detail: str) -> str:
    if detail == "invalid_query_mode":
        return "结构化 payload 缺少合法的 `query_mode`。允许值：`personalized`、`topic`、`scholar`、`author`。"
    if detail == "invalid_aminer_author_id":
        return "输入里的 `aminer_author_id` 不合法。请提供 24 位十六进制字符串。"
    if detail == "invalid_language_sort":
        return "`language_sort` 只能是 `zh` 或 `en`。"
    if detail == "invalid_size":
        return "`size` 必须是 1 到 20 的整数。"
    if detail == "papers_file_outside_base_dir":
        return "出于安全限制，`papers_file` 只能指向当前 skill 目录内的 JSON 文件。"
    if detail == "unsupported_papers_file":
        return "`papers_file` 目前只支持 `.json` 文件。"
    if detail == "personalized_mode_conflict":
        return "`query_mode=personalized` 时不应再传 `topics`、`scholar_name`、`scholar_org` 或 `aminer_author_id`。"
    if detail == "topic_mode_requires_topics":
        return "`query_mode=topic` 时必须提供非空 `topics`，或至少提供 `paper_titles`。"
    if detail == "scholar_mode_requires_name":
        return "`query_mode=scholar` 时必须提供 `scholar_name`。"
    if detail == "author_mode_requires_aminer_author_id":
        return "`query_mode=author` 时必须提供 `aminer_author_id`。"
    if detail == "raw_natural_language_not_supported":
        return (
            "脚本不再直接解析原始自然语言。请先由上层模型提取结构化 payload，"
            "再通过 `--payload-json` 或 `--payload-file` 调用；"
            "如果仍使用 `--text`，请传入显式命令，例如 `/aminer-dp topics: multimodal agents, tool-use`。"
        )
    return f"输入不符合接口约束：{detail}"


def handle_trigger(
    *,
    base_dir: Path,
    payload: dict[str, Any],
    config_path: Path | None = None,
) -> dict[str, Any]:
    try:
        parsed = _normalize_payload(payload, base_dir=base_dir)
    except ValueError as exc:
        detail = _clean_text(str(exc))
        return {
            "status": "success",
            "mode": "invalid_input",
            "final_response": "TEXT",
            "reply_text": _invalid_input_reply(detail),
        }

    output_dir = base_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    loaded_config = _load_config(base_dir, config_path)
    runtime_config_path = output_dir / "runtime_config.yaml"
    runtime_config_path.write_text(yaml.safe_dump(loaded_config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    try:
        pipeline_result = _run_pipeline(
            base_dir=base_dir,
            output_dir=output_dir,
            config_path=runtime_config_path,
            aminer_author_id=parsed["aminer_author_id"],
            topics=parsed["topics"],
            scholar_name=parsed["scholar_name"],
            scholar_org=parsed["scholar_org"],
            paper_titles=parsed["paper_titles"],
            papers_file=parsed["papers_file"],
            language_sort=parsed["language_sort"],
            size=parsed["size"],
        )
    except Exception as exc:
        detail = _compact_pipeline_error(str(exc).strip())
        return {
            "status": "success",
            "mode": "error",
            "final_response": "TEXT",
            "reply_text": f"推荐流程执行失败，出错阶段：{detail}",
        }

    result: dict[str, Any] = {
        "status": "success",
        "mode": pipeline_result.get("mode", "success"),
        "parsed_input": parsed,
        "artifacts": {
            "runtime_config": str(runtime_config_path),
            "output_dir": str(output_dir),
        },
        "pipeline": pipeline_result,
        "final_response": pipeline_result.get("final_response", "TEXT"),
    }
    reply_text = pipeline_result.get("reply_text", "")
    if reply_text:
        result["reply_text"] = reply_text
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run aminer-daily-paper from structured payload.")
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--payload-json", help="Structured payload JSON string.")
    parser.add_argument("--payload-file", type=Path, help="Path to structured payload JSON file.")
    parser.add_argument("--text", help="Legacy explicit command text such as '/aminer-dp topics: ...'.")
    args = parser.parse_args()

    provided = [bool(args.payload_json), bool(args.payload_file), bool(args.text)]
    if sum(provided) != 1:
        parser.error("exactly one of --payload-json, --payload-file, or --text is required")

    if args.payload_json:
        payload = json.loads(args.payload_json)
    elif args.payload_file:
        payload = _load_payload_from_file(args.payload_file.resolve())
    else:
        try:
            payload = _payload_from_structured_text(args.text or "")
        except ValueError as exc:
            result = {
                "status": "success",
                "mode": "invalid_input",
                "final_response": "TEXT",
                "reply_text": _invalid_input_reply(_clean_text(str(exc))),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

    result = handle_trigger(
        base_dir=args.base_dir.resolve(),
        payload=payload,
        config_path=args.config.resolve() if args.config else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
