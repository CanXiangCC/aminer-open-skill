from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def render_author_markdown(
    author_entries: list[dict[str, Any]],
    fallback_authors: list[str],
    aminer_author_profiles: list[dict[str, Any]],
    *,
    max_entries: int = 20,
) -> str:
    rendered: list[str] = []
    seen: set[str] = set()
    if author_entries:
        for entry in author_entries:
            display_name = _clean_text(entry.get("display_name"))
            if not display_name or display_name in seen:
                continue
            seen.add(display_name)
            profile_url = _clean_text(entry.get("profile_url"))
            rendered.append(f"[{display_name}]({profile_url})" if profile_url else display_name)
    if not rendered:
        linked_by_name = {
            _clean_text(profile.get("name")): profile
            for profile in aminer_author_profiles
            if _clean_text(profile.get("name"))
        }
        for author in fallback_authors:
            name = _clean_text(author)
            if not name or name in seen:
                continue
            seen.add(name)
            profile = linked_by_name.get(name, {})
            profile_url = _clean_text(profile.get("profile_url"))
            rendered.append(f"[{name}]({profile_url})" if profile_url else name)
    if not rendered:
        return "暂无"
    limited = rendered[:max_entries]
    result = "、".join(limited)
    return f"{result}、et al." if len(rendered) > max_entries else result
