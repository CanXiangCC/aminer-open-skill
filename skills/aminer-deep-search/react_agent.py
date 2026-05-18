from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_client import APIClient
from citation import get_reference_papers
from paper_set import PaperSet, paper_id_of
from prompt import REACT_SYSTEM_PROMPT
from search import search_papers


CURRENT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = CURRENT_DIR / "outputs"


def default_llm_api_key() -> str | None:
    return os.getenv("llm.api_key")


def default_llm_base_url() -> str | None:
    return os.getenv("llm.base_url")


def extract_tool_call(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    candidates = [stripped]
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    candidates.extend(fenced)

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "tool" in parsed:
            return parsed
    return None


def is_tool_call_json(text: str) -> bool:
    return extract_tool_call(text) is not None


def compact_papers_for_model(papers: list[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for paper in papers[:limit]:
        compact.append(
            {
                "id": paper.get("id"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "n_citation": paper.get("n_citation"),
                "score": paper.get("score"),
            }
        )
    return compact


class ReactPaperCollector:
    def __init__(
        self,
        *,
        topic: str,
        api_key: str | None,
        base_url: str | None = None,
        models: list[str] | None = None,
        timeout: float = 300,
        max_rounds: int = 50,
        max_tool_calls: int = 20,
        target_size: int = 400,
        include_abstracts: bool = False,
    ) -> None:
        self.topic = topic.strip()
        if not self.topic:
            raise ValueError("Topic must be non-empty.")
        self.models = models
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls
        self.target_size = target_size
        self.include_abstracts = include_abstracts
        self.client = APIClient(api_key=api_key, base_url=base_url, timeout=timeout)
        self.paper_set = PaperSet()
        self.paper_cache: dict[str, dict[str, Any]] = {}
        self.messages: list[dict[str, str]] = [
            {"role": "system", "content": REACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Research topic: {self.topic}\n"
                    f"Current collection size: 0. Begin collection now."
                ),
            },
        ]
        self.tool_calls = 0

    def _remember_papers(self, papers: list[dict[str, Any]]) -> None:
        for paper in papers:
            paper_id = paper_id_of(paper).strip()
            if paper_id:
                self.paper_cache[paper_id] = paper

    def _tool_result_message(self, tool: str, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "role": "user",
            "content": (
                f"Tool `{tool}` result:\n"
                f"{json.dumps(payload, ensure_ascii=False)}\n"
                "Continue with exactly one valid tool-call JSON object."
            ),
        }

    def execute_tool(self, call: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        tool = str(call.get("tool") or "").strip()
        params = call.get("params") if isinstance(call.get("params"), dict) else {}

        if tool == "search":
            query = str(params.get("query") or "").strip()
            size = int(params.get("size") or 20)
            papers = search_papers(query, size=size)
            self._remember_papers(papers)
            self.tool_calls += 1
            return False, {
                "query": query,
                "count": len(papers),
                "papers": compact_papers_for_model(papers),
            }

        if tool == "get_reference":
            ids = params.get("aminer_ids") or params.get("ids") or []
            if not isinstance(ids, list):
                ids = []
            size_per_paper = int(params.get("size_per_paper") or 20)
            papers = get_reference_papers(ids, topic=self.topic, size_per_paper=size_per_paper)
            self._remember_papers(papers)
            self.tool_calls += 1
            return False, {
                "seed_ids": ids,
                "count": len(papers),
                "papers": compact_papers_for_model(papers),
            }

        if tool == "add_to_paper_set":
            papers_or_ids = params.get("papers", call.get("papers", []))
            if not isinstance(papers_or_ids, list):
                papers_or_ids = []
            dict_papers = [item for item in papers_or_ids if isinstance(item, dict)]
            id_items = [str(item) for item in papers_or_ids if not isinstance(item, dict)]
            if dict_papers:
                self._remember_papers(dict_papers)
                self.paper_set.add_papers(dict_papers)
            if id_items:
                self.paper_set.add_ids(id_items, self.paper_cache)
            self.tool_calls += 1
            all_papers = self.paper_set.all_papers()
            return False, {
                "collection_size": len(self.paper_set),
                "papers": compact_papers_for_model(all_papers),
                "target_size": self.target_size,
            }

        if tool == "END":
            return True, {
                "collection_size": len(self.paper_set),
                "papers": self.paper_set.output(include_abstracts=self.include_abstracts),
            }

        return False, {
            "error": f"Unknown tool `{tool}`.",
            "valid_tools": ["search", "get_reference", "add_to_paper_set", "END"],
        }

    def run(self) -> list[dict[str, Any]]:
        for round_index in range(1, self.max_rounds + 1):
            if self.tool_calls >= self.max_tool_calls:
                print(
                    f"Ordinary tool-call budget ({self.max_tool_calls}) reached; "
                    "returning collected papers."
                )
                break

            response, ok = self.client.call_messages(
                self.messages,
                model_list=self.models,
                validator=is_tool_call_json,
            )
            if not ok:
                break

            self.messages.append({"role": "assistant", "content": response.content})
            call = extract_tool_call(response.content)
            if call is None:
                self.messages.append(
                    {
                        "role": "user",
                        "content": "Your output was not valid tool-call JSON. Return exactly one valid JSON object.",
                    }
                )
                continue

            done, result = self.execute_tool(call)
            print(f"Round {round_index}: tool={call.get('tool')} collection={len(self.paper_set)}")
            if done:
                return self.paper_set.output(include_abstracts=self.include_abstracts)
            self.messages.append(self._tool_result_message(str(call.get("tool")), result))

        return self.paper_set.output(include_abstracts=self.include_abstracts)

    def save_output(self, papers: list[dict[str, Any]]) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_topic = re.sub(r"[^A-Za-z0-9._-]+", "_", self.topic).strip("_")[:80] or "topic"
        output_path = OUTPUT_DIR / f"{timestamp}_{safe_topic}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(papers, file, ensure_ascii=False, indent=2)
        return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect survey papers with an LLM-driven ReAct loop.")
    parser.add_argument("--topic", required=True, help="Research topic to collect papers for.")
    parser.add_argument(
        "--api-key",
        default=default_llm_api_key(),
        help="OpenAI-compatible LLM API key. Defaults to llm.api_key.",
    )
    parser.add_argument(
        "--base-url",
        default=default_llm_base_url(),
        help="OpenAI-compatible LLM base URL. Defaults to llm.base_url.",
    )
    parser.add_argument("--models", nargs="*", default=None, help="Required model fallback list unless llm.model is configured.")
    parser.add_argument("--timeout", type=float, default=300, help="Per-request model timeout in seconds.")
    parser.add_argument("--max-rounds", type=int, default=50)
    parser.add_argument("--max-tool-calls", type=int, default=20)
    parser.add_argument("--target-size", type=int, default=400)
    parser.add_argument("--include-abstracts", action="store_true")
    args = parser.parse_args()
    if args.models is None:
        model = os.getenv("llm.model")
        if model:
            args.models = [item.strip() for item in model.split(",") if item.strip()]
    return args


def main() -> None:
    args = parse_args()
    collector = ReactPaperCollector(
        topic=args.topic,
        api_key=args.api_key,
        base_url=args.base_url,
        models=args.models,
        timeout=args.timeout,
        max_rounds=args.max_rounds,
        max_tool_calls=args.max_tool_calls,
        target_size=args.target_size,
        include_abstracts=args.include_abstracts,
    )
    papers = collector.run()
    output_path = collector.save_output(papers)
    print(json.dumps(papers, ensure_ascii=False))
    print(f"\nSaved {len(papers)} papers to {output_path}")


if __name__ == "__main__":
    main()
