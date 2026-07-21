"""Render a pdf-citation-verifier result JSON into a self-contained HTML report card.

Usage:
    python3 render_report.py --input result.json --output report.html [--lang zh|en]

Input is the JSON written by verify_pdf.py --output (must contain `summary`;
`details.records` enables the per-record focus table). The generated HTML is a
single file with inline CSS, no external assets, suitable for opening directly
in a browser or sharing.

All numbers are taken verbatim from the input JSON — this script never
re-classifies or re-scores records.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

STATUS_ORDER = ["REAL", "LIKELY_REAL", "NEEDS_REVIEW", "LIKELY_FAKE", "FAKE"]

STATUS_COLORS = {
    "REAL": "#16a34a",
    "LIKELY_REAL": "#0d9488",
    "NEEDS_REVIEW": "#d97706",
    "LIKELY_FAKE": "#ea580c",
    "FAKE": "#dc2626",
}

LABELS = {
    "zh": {
        "REAL": "真的",
        "LIKELY_REAL": "大概率真",
        "NEEDS_REVIEW": "拿不准",
        "LIKELY_FAKE": "大概率假",
        "FAKE": "假的",
        "title": "查完之后，你会拿到这样一份结果",
        "subtitle": "一眼看懂哪些能放心用、哪些要当心",
        "overview": "总览",
        "checked_fmt": "这次一共查了 {total} 条参考文献",
        "flagged_fmt": "其中 {n} 条 大概率是编造的，需要重点当心",
        "flagged_none": "没有发现大概率编造的引用",
        "ratio_label": "假引用占比",
        "focus": "重点看这几条（可疑 / 需人工确认的）",
        "col_verdict": "结论",
        "col_citation": "这条引用写的是",
        "col_reason": "为什么这么判断",
        "confidence": "可信度",
        "conf_high": "很低",
        "conf_mid": "偏低",
        "conf_low": "一般",
        "author": "作者",
        "year_unknown": "年份不详",
        "footer": "完整清单里，每条还给出：原文、匹配到的真实文献、以及详细报告链接。",
        "brand": "AMiner · 参考文献真伪核验",
        "no_flagged": "所有引用都通过了核验，没有需要重点关注的条目 🎉",
        "matched": "库里最接近的是",
    },
    "en": {
        "REAL": "Real",
        "LIKELY_REAL": "Likely real",
        "NEEDS_REVIEW": "Unsure",
        "LIKELY_FAKE": "Likely fake",
        "FAKE": "Fake",
        "title": "Your citation verification report",
        "subtitle": "See at a glance which references are safe and which need attention",
        "overview": "Overview",
        "checked_fmt": "{total} references checked",
        "flagged_fmt": "{n} of them are probably fabricated — review carefully",
        "flagged_none": "No probably-fabricated citations found",
        "ratio_label": "fake ratio",
        "focus": "Review these (suspicious / needs human check)",
        "col_verdict": "Verdict",
        "col_citation": "The citation says",
        "col_reason": "Why we think so",
        "confidence": "Confidence",
        "conf_high": "very low",
        "conf_mid": "low",
        "conf_low": "moderate",
        "author": "by",
        "year_unknown": "year unknown",
        "footer": "The full list also includes: raw text, the matched real paper, and a detailed report link for each entry.",
        "brand": "AMiner · Citation Verifier",
        "no_flagged": "All citations passed verification — nothing needs special attention 🎉",
        "matched": "Closest match in the database",
    },
}

# Human-readable explanations for the most common key_reasons codes.
REASON_TEXT = {
    "zh": {
        "Aminer returned no reliable match for this citation.": "资料库里查不到这篇",
        "Only weak/partial Aminer match found.": "只找到弱匹配，标题或作者对不上",
        "AUTHOR_CHECK_NO_EVIDENCE": "没有可比对的作者信息",
        "AUTHOR_MISMATCH_STRICT": "作者对不上",
        "AUTHOR_LIST_MISMATCH_STRICT": "作者列表对不上",
        "AUTHOR_LIST_CONFLICT_STRICT": "作者列表冲突",
        "AUTHOR_TITLE_CONFLICT_STRICT": "作者与标题信息冲突",
        "AUTHOR_LIST_UNAVAILABLE_FALLBACK_FIRST_AUTHOR": "只能比对第一作者",
        "CANDIDATE_EXTRACTION_LOW_QUALITY: low-confidence candidate extraction.": "原文解析质量偏低",
        "CANDIDATE_REFERENCE_STRUCTURE_WEAK: missing typical citation structure signals.": "缺少典型引用结构",
    },
    "en": {
        "Aminer returned no reliable match for this citation.": "no reliable match in the database",
        "Only weak/partial Aminer match found.": "only a weak/partial match found",
        "AUTHOR_CHECK_NO_EVIDENCE": "no author evidence to compare",
        "AUTHOR_MISMATCH_STRICT": "author mismatch",
        "AUTHOR_LIST_MISMATCH_STRICT": "author list mismatch",
        "AUTHOR_LIST_CONFLICT_STRICT": "author list conflict",
        "AUTHOR_TITLE_CONFLICT_STRICT": "author/title conflict",
        "AUTHOR_LIST_UNAVAILABLE_FALLBACK_FIRST_AUTHOR": "compared first author only",
        "CANDIDATE_EXTRACTION_LOW_QUALITY: low-confidence candidate extraction.": "low-quality text extraction",
        "CANDIDATE_REFERENCE_STRUCTURE_WEAK: missing typical citation structure signals.": "weak citation structure",
    },
}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _humanize_reasons(key_reasons: list[str], lang: str, limit: int = 3) -> str:
    mapping = REASON_TEXT[lang]
    out: list[str] = []
    for code in key_reasons or []:
        text = mapping.get(code)
        if text is None:
            # Try prefix match for parameterized codes like "CANDIDATE_RAW_TOO_LONG: raw_text length=3926."
            for known, translated in mapping.items():
                if code.split(":")[0] == known.split(":")[0]:
                    text = translated
                    break
        if text is None:
            text = code.split(":")[0].replace("_", " ").lower()
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    joiner = "，" if lang == "zh" else "; "
    return joiner.join(out)


def _confidence_word(confidence: Any, status: str, lang: str) -> str:
    labels = LABELS[lang]
    if status == "FAKE":
        return labels["conf_high"]
    if status == "LIKELY_FAKE":
        return labels["conf_mid"]
    return labels["conf_low"]


def build_html(payload: dict[str, Any], lang: str) -> str:
    labels = LABELS[lang]
    summary = payload.get("summary") or {}
    overall = summary.get("overall") or {}
    counts: dict[str, int] = overall.get("counts_by_status") or {}
    total = summary.get("total") or sum(counts.values()) or 0
    ratio = overall.get("hallucination_ratio")
    if ratio is None and total:
        ratio = (counts.get("FAKE", 0) + counts.get("LIKELY_FAKE", 0)) / total
    ratio_pct = f"{(ratio or 0) * 100:.1f}%"
    flagged_n = counts.get("FAKE", 0) + counts.get("LIKELY_FAKE", 0)

    records = (payload.get("details") or {}).get("records") or []
    focus = [r for r in records if r.get("status") in ("FAKE", "LIKELY_FAKE", "NEEDS_REVIEW")]
    focus.sort(key=lambda r: STATUS_ORDER.index(r.get("status", "NEEDS_REVIEW")), reverse=True)

    # Stacked bar segments
    segments = []
    for status in STATUS_ORDER:
        n = counts.get(status, 0)
        if n <= 0 or not total:
            continue
        width = n / total * 100
        segments.append(
            f'<div class="seg" style="width:{width:.2f}%;background:{STATUS_COLORS[status]}"></div>'
        )
    legend = []
    for status in STATUS_ORDER:
        n = counts.get(status, 0)
        legend.append(
            f'<span class="leg"><i style="background:{STATUS_COLORS[status]}"></i>'
            f"{labels[status]} {n}</span>"
        )

    # Focus table rows
    rows = []
    for r in focus:
        status = r.get("status", "")
        color = STATUS_COLORS.get(status, "#666")
        title = _esc(r.get("title") or "(untitled)")
        author = _esc(r.get("first_author") or "?")
        year = _esc(r.get("year") or labels["year_unknown"])
        reason = _esc(_humanize_reasons(r.get("key_reasons") or [], lang))
        conf_word = labels["confidence"] + ": " + _confidence_word(r.get("confidence"), status, lang)
        top_match = (r.get("top_match") or {}).get("title")
        match_line = (
            f'<div class="match">{_esc(labels["matched"])}: “{_esc(top_match)}”</div>'
            if top_match
            else ""
        )
        rows.append(
            f"""
      <tr>
        <td class="verdict">
          <span class="badge" style="color:{color};border-color:{color};background:{color}14">{labels.get(status, status)}</span>
          <div class="conf">{_esc(conf_word)}</div>
        </td>
        <td class="cite">
          <div class="cite-title">“{title}”</div>
          <div class="cite-meta">{_esc(labels["author"])} {author} · {year}</div>
          {match_line}
        </td>
        <td class="reason">{reason}</td>
      </tr>"""
        )

    focus_block = (
        f"""
    <h2>🔎 {_esc(labels["focus"])}</h2>
    <table>
      <thead>
        <tr>
          <th>{_esc(labels["col_verdict"])}</th>
          <th>{_esc(labels["col_citation"])}</th>
          <th>{_esc(labels["col_reason"])}</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}
      </tbody>
    </table>"""
        if rows
        else f'<p class="allclear">{_esc(labels["no_flagged"])}</p>'
    )

    flagged_line = (
        labels["flagged_fmt"].format(n=flagged_n) if flagged_n else labels["flagged_none"]
    )
    job_id = _esc(payload.get("job_id") or "")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(labels["brand"])}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #f4f6f9; color: #1a2233; padding: 40px 16px; line-height: 1.55;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  header {{ border-left: 5px solid #e5484d; padding-left: 16px; margin-bottom: 26px; }}
  header h1 {{ font-size: 26px; }}
  header p {{ color: #667085; font-size: 14px; margin-top: 4px; }}
  .card {{
    background: #fff; border-radius: 16px; padding: 28px 32px;
    box-shadow: 0 1px 3px rgba(16,24,40,.08); margin-bottom: 24px;
  }}
  .kicker {{ letter-spacing: .35em; font-size: 12px; color: #98a2b3; margin-bottom: 8px; }}
  .ov {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; flex-wrap: wrap; }}
  .ov h2 {{ font-size: 24px; }}
  .ov .flag {{ margin-top: 6px; font-size: 15px; }}
  .ov .flag b {{ color: #dc2626; }}
  .ratio {{ text-align: right; }}
  .ratio .num {{ font-size: 46px; font-weight: 800; color: #dc2626; line-height: 1; }}
  .ratio .lbl {{ color: #98a2b3; font-size: 13px; margin-top: 4px; }}
  .bar {{ display: flex; height: 26px; border-radius: 8px; overflow: hidden; margin: 26px 0 14px; background: #eef0f3; }}
  .seg {{ height: 100%; }}
  .legend {{ display: flex; gap: 22px; flex-wrap: wrap; font-size: 14px; color: #344054; }}
  .leg i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
  h2 {{ font-size: 18px; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 13px; color: #98a2b3; font-weight: 500;
       padding: 8px 10px; border-bottom: 1px solid #eaecf0; }}
  td {{ padding: 16px 10px; border-bottom: 1px solid #f2f4f7; vertical-align: top; font-size: 14px; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{
    display: inline-block; padding: 5px 16px; border-radius: 8px;
    border: 1px solid; font-weight: 600; font-size: 14px; white-space: nowrap;
  }}
  .conf {{ color: #98a2b3; font-size: 12px; margin-top: 6px; }}
  .cite-title {{ font-weight: 600; }}
  .cite-meta {{ color: #667085; font-size: 13px; margin-top: 4px; }}
  .match {{ color: #0d9488; font-size: 13px; margin-top: 4px; }}
  .reason {{ color: #475467; max-width: 320px; }}
  .allclear {{ color: #16a34a; font-size: 15px; }}
  footer {{ color: #98a2b3; font-size: 13px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📋 {_esc(labels["title"])}</h1>
    <p>{_esc(labels["subtitle"])}</p>
  </header>

  <div class="card">
    <div class="kicker">{_esc(labels["overview"])}</div>
    <div class="ov">
      <div>
        <h2>{_esc(labels["checked_fmt"].format(total=total))}</h2>
        <div class="flag">{flagged_line.replace(str(flagged_n), f"<b>{flagged_n}</b>", 1) if flagged_n else _esc(flagged_line)}</div>
      </div>
      <div class="ratio">
        <div class="num">{_esc(ratio_pct)}</div>
        <div class="lbl">{_esc(labels["ratio_label"])}</div>
      </div>
    </div>
    <div class="bar">{''.join(segments)}</div>
    <div class="legend">{''.join(legend)}</div>
  </div>

  <div class="card">{focus_block}
  </div>

  <footer>
    <span>💡 {_esc(labels["footer"])}</span>
    <span>{_esc(labels["brand"])}{f' · {job_id}' if job_id else ''}</span>
  </footer>
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a verify_pdf.py output JSON into a self-contained HTML report."
    )
    parser.add_argument("--input", required=True, help="Path to the result JSON from verify_pdf.py --output.")
    parser.add_argument("--output", required=True, help="Path to write the HTML report.")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="Report language (default zh).")
    args = parser.parse_args()

    in_path = Path(args.input).expanduser()
    if not in_path.is_file():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: input is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict) or "summary" not in payload:
        print("ERROR: input JSON has no 'summary' field — is this a verify_pdf.py output?", file=sys.stderr)
        return 2

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(payload, args.lang), encoding="utf-8")
    print(f"[report] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
