#!/usr/bin/env python3
"""Render a stable single-file Paper Source Trace HTML graph."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any


I18N = {
    "en": {
        "page_title": "Paper Source Trace Map",
        "subtitle": "Unified interactive graph generated from citation_graph.json",
        "controls": "Controls",
        "layout": "Layout",
        "radial": "Radial",
        "chain": "Chain",
        "search": "Search",
        "search_placeholder": "Search citations, references, evidence",
        "filter": "Filter",
        "zoom": "Zoom",
        "zoom_in": "Zoom in",
        "zoom_out": "Zoom out",
        "fit": "Fit screen",
        "reset": "Reset layout",
        "export_svg": "Export SVG",
        "node_details": "Node details",
        "empty_detail": "Select a node to inspect citation context, reference metadata, and source traces.",
        "source_traces": "Source traces",
        "evidence": "Evidence",
        "reference": "Reference",
        "aminer": "AMiner metadata",
        "metadata": "Metadata",
        "citations": "citations",
        "traces": "traces",
        "year": "Year",
        "aminer_on": "AMiner metadata available",
        "aminer_off": "No AMiner metadata",
        "target": "Target paper",
        "confidence": "Confidence",
        "section": "Section",
        "marker": "Marker",
        "intent": "Intent",
        "role": "Role",
        "context": "Context",
        "summary": "Summary",
        "steps": "Steps",
        "no_items": "No records available.",
        "shown": "shown",
        "all_groups": "All groups",
        "instructions": "Wheel to zoom, drag empty canvas to pan, drag nodes to adjust, double-click a node to reset it.",
        "download_name": "citation_map_view.svg",
        "uncertain": "Uncertain",
    },
    "zh": {
        "page_title": "论文来源追踪图谱",
        "subtitle": "由 citation_graph.json 生成的统一交互图谱",
        "controls": "控制",
        "layout": "布局",
        "radial": "径向图",
        "chain": "溯源链图",
        "search": "搜索",
        "search_placeholder": "搜索引用、参考文献、证据",
        "filter": "筛选",
        "zoom": "缩放",
        "zoom_in": "放大",
        "zoom_out": "缩小",
        "fit": "适配屏幕",
        "reset": "重置布局",
        "export_svg": "导出当前 SVG",
        "node_details": "节点详情",
        "empty_detail": "选择节点后查看引用上下文、参考文献元数据和来源追踪。",
        "source_traces": "来源追踪",
        "evidence": "证据",
        "reference": "参考文献",
        "aminer": "AMiner 元数据",
        "metadata": "元数据",
        "citations": "条引用",
        "traces": "条追踪",
        "year": "年份",
        "aminer_on": "已包含 AMiner 元数据",
        "aminer_off": "无 AMiner 元数据",
        "target": "目标论文",
        "confidence": "置信度",
        "section": "章节",
        "marker": "标记",
        "intent": "意图",
        "role": "角色",
        "context": "上下文",
        "summary": "总结",
        "steps": "步骤",
        "no_items": "暂无记录。",
        "shown": "已显示",
        "all_groups": "全部分组",
        "instructions": "滚轮缩放，拖动画布平移，拖动节点调整位置，双击节点恢复自动布局。",
        "download_name": "citation_map_view.svg",
        "uncertain": "不确定",
    },
}


CANONICAL_GROUPS = [
    {
        "group_id": "problem-background",
        "intents": ["background", "problem", "theory"],
        "color": "#cf6f6f",
        "label_en": "Problem/background",
        "label_zh": "问题/背景",
        "chain_en": "Problem chain",
        "chain_zh": "问题链",
    },
    {
        "group_id": "method-core",
        "intents": ["core-method", "supporting-method", "tool-resource"],
        "color": "#ef6c2f",
        "label_en": "Methods/tools",
        "label_zh": "方法/工具",
        "chain_en": "Method chain",
        "chain_zh": "方法链",
    },
    {
        "group_id": "data-eval",
        "intents": ["dataset", "metric"],
        "color": "#8a5cf6",
        "label_en": "Data/evaluation",
        "label_zh": "数据/评估",
        "chain_en": "Data chain",
        "chain_zh": "数据链",
    },
    {
        "group_id": "baseline-result",
        "intents": ["baseline", "result-evidence"],
        "color": "#d18a19",
        "label_en": "Baselines/results",
        "label_zh": "基线/结果",
        "chain_en": "Baseline chain",
        "chain_zh": "基线链",
    },
    {
        "group_id": "limits-future",
        "intents": ["limitation", "future-work"],
        "color": "#4f9c56",
        "label_en": "Limits/resources",
        "label_zh": "局限/资源",
        "chain_en": "Limits/resources chain",
        "chain_zh": "局限/资源链",
    },
]


RADIAL_MAX_PER_GROUP = 6
CHAIN_MAX_PER_GROUP = 8


HTML_TEMPLATE = r"""<!doctype html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --bg: #f6f8fb;
  --panel: #ffffff;
  --ink: #172033;
  --muted: #64748b;
  --line: #d9e2ee;
  --accent: #1f5f99;
  --accent-2: #0f766e;
  --shadow: 0 12px 28px rgba(24, 38, 63, 0.10);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Arial, "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  background: var(--bg);
  color: var(--ink);
}}
header {{
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  border-bottom: 1px solid var(--line);
  padding: 18px 24px 14px;
}}
h1 {{ margin: 0 0 6px; font-size: 22px; line-height: 1.25; }}
h2 {{ margin: 0 0 12px; font-size: 16px; }}
h3 {{ margin: 18px 0 10px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
p {{ margin: 8px 0; line-height: 1.5; }}
.topline {{ color: var(--muted); font-size: 13px; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
.stat, .badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  color: #334155;
  font-size: 12px;
}}
main {{
  display: grid;
  grid-template-columns: 300px minmax(480px, 1fr) 360px;
  gap: 14px;
  padding: 14px;
  min-height: calc(100vh - 112px);
}}
.panel, .stage {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}}
.panel {{ padding: 14px; overflow: auto; max-height: calc(100vh - 136px); }}
.stage {{ display: flex; flex-direction: column; min-width: 0; overflow: hidden; }}
.toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  background: #fbfdff;
}}
.canvas-wrap {{
  position: relative;
  flex: 1;
  min-height: 720px;
  overflow: hidden;
  cursor: grab;
}}
.canvas-wrap.dragging {{ cursor: grabbing; }}
svg {{ display: block; width: 100%; height: 100%; background: #fbfcff; user-select: none; }}
button, .seg button {{
  min-height: 34px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  border-radius: 7px;
  padding: 7px 10px;
  font-size: 13px;
  cursor: pointer;
}}
button:hover {{ border-color: #9bb3ce; }}
button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.seg {{ display: inline-flex; gap: 6px; flex-wrap: wrap; }}
input[type="search"] {{
  width: 100%;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--ink);
  font-size: 13px;
}}
.group-list {{ display: grid; gap: 8px; }}
.toggle {{
  display: grid;
  grid-template-columns: 18px 16px 1fr auto;
  align-items: center;
  gap: 7px;
  font-size: 13px;
}}
.swatch {{ width: 14px; height: 14px; border-radius: 4px; border: 1px solid #0002; }}
.muted {{ color: var(--muted); font-size: 12px; }}
.detail-card {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  margin: 10px 0;
  background: #fbfdff;
}}
.detail-card strong {{ display: inline-block; margin-bottom: 4px; }}
.kv {{
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 6px 8px;
  font-size: 13px;
  line-height: 1.35;
}}
.pill {{
  display: inline-block;
  padding: 2px 7px;
  border-radius: 999px;
  background: #eef2f7;
  color: #334155;
  font-size: 12px;
  margin: 2px 4px 2px 0;
}}
.trace-item {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 9px;
  margin-bottom: 8px;
  background: #fff;
  cursor: pointer;
}}
.trace-item:hover {{ border-color: #9bb3ce; }}
.count-line {{ font-size: 12px; color: var(--muted); }}
.node rect {{ filter: drop-shadow(0 4px 8px rgba(15, 23, 42, .13)); }}
.node text {{ pointer-events: none; }}
.node {{ cursor: pointer; }}
.node.draggable {{ cursor: move; }}
.node.selected rect {{ stroke-width: 3; }}
.edge {{ pointer-events: none; }}
.legend-row {{ display: flex; align-items: center; gap: 7px; margin: 6px 0; font-size: 12px; }}
@media (max-width: 1100px) {{
  main {{ grid-template-columns: 1fr; }}
  .panel {{ max-height: none; }}
  .canvas-wrap {{ min-height: 620px; }}
}}
</style>
</head>
<body>
<header>
  <h1 id="paper-title"></h1>
  <div class="topline">{subtitle}</div>
  <div class="stats" id="stats"></div>
</header>
<main>
  <aside class="panel">
    <h2>{controls}</h2>
    <h3>{layout}</h3>
    <div class="seg">
      <button id="layout-radial" class="active" type="button">{radial}</button>
      <button id="layout-chain" type="button">{chain}</button>
    </div>
    <h3>{search}</h3>
    <input id="search" type="search" placeholder="{search_placeholder}">
    <h3>{filter}</h3>
    <label class="toggle"><input id="all-groups" type="checkbox" checked><span></span><span>{all_groups}</span><span></span></label>
    <div class="group-list" id="group-list"></div>
    <h3>{zoom}</h3>
    <div class="seg">
      <button id="zoom-out" type="button">{zoom_out}</button>
      <button id="zoom-in" type="button">{zoom_in}</button>
      <button id="fit" type="button">{fit}</button>
    </div>
    <div style="margin-top:8px" class="seg">
      <button id="reset" type="button">{reset}</button>
      <button id="export-svg" type="button">{export_svg}</button>
    </div>
    <p class="muted">{instructions}</p>
  </aside>
  <section class="stage">
    <div class="toolbar">
      <div id="shown-count" class="count-line"></div>
      <div class="count-line" id="zoom-label"></div>
    </div>
    <div id="canvas-wrap" class="canvas-wrap">
      <svg id="graph" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{page_title}">
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
            <path d="M1,1 L9,5 L1,9 Z" fill="#8aa0b6"></path>
          </marker>
        </defs>
        <g id="viewport"></g>
      </svg>
    </div>
  </section>
  <aside class="panel">
    <h2>{node_details}</h2>
    <div id="details" class="muted">{empty_detail}</div>
    <h3>{source_traces}</h3>
    <div id="traces"></div>
  </aside>
</main>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
const UI = {ui_json};
const GRAPH = JSON.parse(document.getElementById("graph-data").textContent);
const svg = document.getElementById("graph");
const viewport = document.getElementById("viewport");
const wrap = document.getElementById("canvas-wrap");
const groupList = document.getElementById("group-list");
const allGroups = document.getElementById("all-groups");
const search = document.getElementById("search");
const details = document.getElementById("details");
const tracesEl = document.getElementById("traces");
const shownCount = document.getElementById("shown-count");
const zoomLabel = document.getElementById("zoom-label");
const layoutButtons = {{
  radial: document.getElementById("layout-radial"),
  chain: document.getElementById("layout-chain")
}};
const refs = new Map((GRAPH.references || []).map(r => [r.reference_id, r]));
const traces = new Map((GRAPH.source_traces || []).map(t => [t.trace_id, t]));
const GROUPS = {groups_json};
const RADIAL_MAX_PER_GROUP = {radial_max_per_group};
const CHAIN_MAX_PER_GROUP = {chain_max_per_group};
let layout = "radial";
let scale = 1;
let pan = {{x: 0, y: 0}};
let activeGroups = new Set(GROUPS.map(g => g.group_id));
let nodePositions = new Map();
let defaultPositions = new Map();
let selectedNodeId = null;
let canvasDrag = null;
let nodeDrag = null;
let currentNodes = [];
let canvasSize = {{width: 1400, height: 900}};

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, ch => {{
    if (ch === "&") return "&amp;";
    if (ch === "<") return "&lt;";
    if (ch === ">") return "&gt;";
    if (ch === '"') return "&quot;";
    return "&#39;";
  }});
}}
function clamp(n, min, max) {{ return Math.max(min, Math.min(max, n)); }}
function byId(id) {{ return document.getElementById(id); }}
function textParts(value, maxChars, maxLines) {{
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  if (!raw) return [""];
  const words = raw.includes(" ") ? raw.split(" ") : Array.from(raw);
  const lines = [];
  let line = "";
  for (const word of words) {{
    const joiner = raw.includes(" ") ? " " : "";
    const next = line ? line + joiner + word : word;
    if (next.length > maxChars && line) {{
      lines.push(line);
      line = word;
    }} else {{
      line = next;
    }}
    if (lines.length >= maxLines) break;
  }}
  if (lines.length < maxLines && line) lines.push(line);
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) {{
    lines[maxLines - 1] = lines[maxLines - 1].replace(/[,.，。;；:：]$/, "") + "...";
  }}
  return lines.length ? lines : [raw.slice(0, maxChars)];
}}
function citationPriority(citation) {{
  const hasTrace = (citation.trace_ids || []).length > 0 ? 100 : 0;
  const confidence = Number(citation.confidence || 0) * 10;
  const visible = citation.show_on_map === false ? -100 : 0;
  return hasTrace + confidence + visible;
}}
function sortedCitations(items) {{
  return [...items].sort((a, b) => citationPriority(b) - citationPriority(a) || String(a.citation_id || "").localeCompare(String(b.citation_id || "")));
}}
function limitedCitations(items, limit) {{
  const sorted = sortedCitations(items.filter(c => c.show_on_map !== false));
  return {{
    shown: sorted.slice(0, limit),
    overflow: Math.max(0, sorted.length - limit)
  }};
}}
function svgText(lines, x, y, size, color, anchor, weight) {{
  return lines.map((line, idx) =>
    `<text x="${{x}}" y="${{y + idx * (size + 5)}}" fill="${{color}}" font-size="${{size}}" text-anchor="${{anchor || "start"}}" font-weight="${{weight || 400}}">${{esc(line)}}</text>`
  ).join("");
}}
function groupForCitation(citation) {{
  return GROUPS.find(g => (g.intent_filters || []).includes(citation.intent)) ||
    {{group_id: "uncertain", label: UI.uncertain, color: "#94a3b8", intent_filters: []}};
}}
function matchesSearch(citation) {{
  const q = search.value.trim().toLowerCase();
  if (!q) return true;
  const ref = refs.get(citation.reference_id);
  const haystack = [
    citation.citation_id,
    citation.marker,
    citation.intent,
    citation.evidence,
    citation.context,
    citation.target_claim,
    citation.cited_work_role,
    ref && ref.title,
    ref && (ref.authors || []).join(" ")
  ].join(" ").toLowerCase();
  return haystack.includes(q);
}}
function filteredCitations() {{
  const activeIntents = new Set(GROUPS
    .filter(g => activeGroups.has(g.group_id))
    .flatMap(g => g.intent_filters || []));
  return (GRAPH.citations || [])
    .filter(c => activeIntents.has(c.intent) || activeGroups.size === 0)
    .filter(matchesSearch);
}}
function hasAminer() {{
  const meta = GRAPH.metadata && GRAPH.metadata.aminer_enrichment;
  return !!(meta && meta.enabled) || (GRAPH.references || []).some(r => r.aminer_paper_id) || !!(GRAPH.paper && GRAPH.paper.aminer_paper_id);
}}
function setTransform() {{
  viewport.setAttribute("transform", `translate(${{pan.x}} ${{pan.y}}) scale(${{scale}})`);
  zoomLabel.textContent = `${{Math.round(scale * 100)}}%`;
}}
function graphBounds() {{
  if (!currentNodes.length) return {{x: 0, y: 0, width: canvasSize.width, height: canvasSize.height}};
  const padding = 110;
  const minX = Math.min(...currentNodes.map(n => n.x)) - padding;
  const minY = Math.min(...currentNodes.map(n => n.y)) - padding;
  const maxX = Math.max(...currentNodes.map(n => n.x + n.w)) + padding;
  const maxY = Math.max(...currentNodes.map(n => n.y + n.h)) + padding;
  return {{x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY)}};
}}
function graphFocus(bounds) {{
  return {{x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2}};
}}
function fitToScreen(options) {{
  const readable = !!(options && options.readable);
  const rect = wrap.getBoundingClientRect();
  const bounds = graphBounds();
  const sx = rect.width / bounds.width;
  const sy = rect.height / bounds.height;
  const fitted = Math.min(sx, sy) * 0.92;
  if (readable) {{
    const minReadable = layout === "chain" ? 0.18 : 0.32;
    const maxReadable = layout === "chain" ? 0.74 : 0.58;
    const maxOverflow = layout === "chain" ? 0.96 : 1.80;
    const maxByOverflow = Math.min(rect.width * maxOverflow / bounds.width, rect.height * maxOverflow / bounds.height);
    scale = clamp(Math.max(fitted, minReadable), 0.18, Math.min(maxReadable, maxByOverflow));
  }} else {{
    scale = clamp(fitted, 0.18, 1.35);
  }}
  const focus = readable ? graphFocus(bounds) : {{x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2}};
  pan = {{
    x: rect.width / 2 - focus.x * scale,
    y: rect.height / 2 - focus.y * scale
  }};
  setTransform();
}}
function focusReadable() {{
  fitToScreen({{readable: true}});
}}
function resetLayout() {{
  nodePositions = new Map(defaultPositions);
  render();
  focusReadable();
}}
function zoomBy(delta, center) {{
  const old = scale;
  const next = clamp(scale * delta, 0.22, 2.8);
  const rect = wrap.getBoundingClientRect();
  const cx = center ? center.x - rect.left : rect.width / 2;
  const cy = center ? center.y - rect.top : rect.height / 2;
  pan.x = cx - (cx - pan.x) * (next / old);
  pan.y = cy - (cy - pan.y) * (next / old);
  scale = next;
  setTransform();
}}
function screenToWorld(evt) {{
  const rect = wrap.getBoundingClientRect();
  return {{
    x: (evt.clientX - rect.left - pan.x) / scale,
    y: (evt.clientY - rect.top - pan.y) / scale
  }};
}}
function radialLayout(citations) {{
  const groups = GROUPS.filter(g => activeGroups.has(g.group_id));
  canvasSize = {{width: 4000, height: 2700}};
  const cx = canvasSize.width / 2;
  const cy = canvasSize.height / 2;
  const colStep = 318;
  const rowStep = 146;
  const slots = {{
    "problem-background": {{gx: cx, gy: cy - 760, side: "top"}},
    "method-core": {{gx: cx + 760, gy: cy - 350, side: "right"}},
    "data-eval": {{gx: cx + 680, gy: cy + 570, side: "right"}},
    "baseline-result": {{gx: cx - 680, gy: cy + 570, side: "left"}},
    "limits-future": {{gx: cx - 760, gy: cy - 350, side: "left"}}
  }};
  const nodes = [{{id: "target-paper", kind: "target", x: cx - 150, y: cy - 72, w: 300, h: 144, color: "#0f172a", data: GRAPH.paper || {{}}}}];
  groups.forEach((group) => {{
    const slot = slots[group.group_id] || {{gx: cx, gy: cy - 760, side: "top"}};
    const gx = slot.gx;
    const gy = slot.gy;
    nodes.push({{id: `group:${{group.group_id}}`, kind: "group", x: gx - 86, y: gy - 46, w: 172, h: 92, color: group.color || "#64748b", data: group}});
    const limited = limitedCitations(citations.filter(c => (group.intent_filters || []).includes(c.intent)), RADIAL_MAX_PER_GROUP);
    const items = limited.shown;
    const cols = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(items.length))));
    const rows = Math.ceil(items.length / cols);
    const gridHeight = (rows - 1) * rowStep + 80;
    let startX = gx - (cols - 1) * colStep / 2 - 118;
    let startY = gy - 320 - (rows - 1) * rowStep;
    if (slot.side === "right") {{
      startX = gx + 300;
      startY = gy - gridHeight / 2;
    }} else if (slot.side === "left") {{
      startX = gx - 300 - (cols - 1) * colStep - 236;
      startY = gy - gridHeight / 2;
    }}
    items.forEach((citation, i) => {{
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = startX + col * colStep;
      const y = startY + row * rowStep;
      nodes.push({{id: citation.citation_id, kind: "citation", x, y, w: 236, h: 80, color: group.color || "#64748b", data: citation, group_id: group.group_id}});
    }});
    if (limited.overflow > 0) {{
      const x = startX + (cols - 1) * colStep / 2 + 46;
      const y = startY + rows * rowStep + 20;
      nodes.push({{id: `overflow:${{group.group_id}}`, kind: "overflow", x, y, w: 144, h: 44, color: group.color || "#64748b", data: {{label: `+${{limited.overflow}} ${{UI.citations}}`}}, group_id: group.group_id}});
    }}
  }});
  return nodes;
}}
function chainLayout(citations) {{
  const groups = GROUPS.filter(g => activeGroups.has(g.group_id));
  const laneHeight = 220;
  const maxItems = Math.max(1, ...groups.map(g => limitedCitations(citations.filter(c => (g.intent_filters || []).includes(c.intent)), CHAIN_MAX_PER_GROUP).shown.length));
  canvasSize = {{
    width: Math.max(2200, 780 + Math.ceil(maxItems / 2) * 330),
    height: Math.max(1200, groups.length * laneHeight + 340)
  }};
  const targetX = canvasSize.width - 360;
  const targetY = canvasSize.height / 2 - 76;
  const nodes = [{{id: "target-paper", kind: "target", x: targetX, y: targetY, w: 300, h: 152, color: "#0f172a", data: GRAPH.paper || {{}}}}];
  groups.forEach((group, gi) => {{
    const y = 150 + gi * laneHeight;
    nodes.push({{id: `group:${{group.group_id}}`, kind: "group", x: 70, y: y - 46, w: 196, h: 92, color: group.color || "#64748b", data: {{...group, label: group.chain_label || group.label}}}});
    const limited = limitedCitations(citations.filter(c => (group.intent_filters || []).includes(c.intent)), CHAIN_MAX_PER_GROUP);
    const items = limited.shown;
    items.forEach((citation, i) => {{
      const col = Math.floor(i / 2);
      const row = i % 2;
      const x = 330 + col * 330;
      const yy = y - 76 + row * 96;
      nodes.push({{id: citation.citation_id, kind: "citation", x, y: yy, w: 270, h: 82, color: group.color || "#64748b", data: citation, group_id: group.group_id}});
    }});
    if (limited.overflow > 0) {{
      const x = 330 + Math.ceil(items.length / 2) * 330;
      nodes.push({{id: `overflow:${{group.group_id}}`, kind: "overflow", x, y: y - 24, w: 150, h: 48, color: group.color || "#64748b", data: {{label: `+${{limited.overflow}} ${{UI.citations}}`}}, group_id: group.group_id}});
    }}
  }});
  return nodes;
}}
function establishDefaults(nodes) {{
  defaultPositions = new Map(nodes.map(n => [n.id, {{x: n.x, y: n.y}}]));
  for (const n of nodes) {{
    if (nodePositions.has(n.id)) {{
      const p = nodePositions.get(n.id);
      n.x = p.x;
      n.y = p.y;
    }}
  }}
}}
function nodeHtml(n) {{
  const selected = n.id === selectedNodeId ? " selected" : "";
  const dragClass = n.kind === "citation" ? " draggable" : "";
  if (n.kind === "target") {{
    const paper = n.data || {{}};
    const title = textParts(paper.title || UI.target, 30, 3);
    const sub = [paper.year ? `${{UI.year}}: ${{paper.year}}` : "", (paper.authors || []).slice(0, 2).join(", ")].filter(Boolean).join(" · ");
    return `<g class="node${{selected}}${{dragClass}}" data-id="${{esc(n.id)}}" data-kind="${{n.kind}}">
      <rect x="${{n.x}}" y="${{n.y}}" width="${{n.w}}" height="${{n.h}}" rx="14" fill="#ffffff" stroke="${{n.color}}" stroke-width="2"></rect>
      ${{svgText([UI.target], n.x + n.w / 2, n.y + 28, 13, "#64748b", "middle", 700)}}
      ${{svgText(title, n.x + n.w / 2, n.y + 58, 16, "#0f172a", "middle", 800)}}
      ${{svgText(textParts(sub, 34, 1), n.x + n.w / 2, n.y + n.h - 26, 12, "#64748b", "middle", 400)}}
    </g>`;
  }}
  if (n.kind === "group") {{
    const label = textParts(n.data.label || n.data.group_id, 15, 2);
    return `<g class="node${{selected}}" data-id="${{esc(n.id)}}" data-kind="${{n.kind}}">
      <rect x="${{n.x}}" y="${{n.y}}" width="${{n.w}}" height="${{n.h}}" rx="14" fill="${{n.color}}" stroke="${{n.color}}" stroke-width="2"></rect>
      ${{svgText(label, n.x + n.w / 2, n.y + 34, 15, "#ffffff", "middle", 800)}}
    </g>`;
  }}
  if (n.kind === "overflow") {{
    return `<g class="node" data-id="${{esc(n.id)}}" data-kind="${{n.kind}}">
      <rect x="${{n.x}}" y="${{n.y}}" width="${{n.w}}" height="${{n.h}}" rx="999" fill="#ffffff" stroke="${{n.color}}" stroke-width="1.5" stroke-dasharray="5 5"></rect>
      ${{svgText(textParts(n.data.label, 18, 1), n.x + n.w / 2, n.y + 28, 13, n.color, "middle", 800)}}
    </g>`;
  }}
  const c = n.data;
  const ref = refs.get(c.reference_id);
  const title = c.target_claim || c.evidence || (ref && ref.title) || c.marker || c.citation_id;
  const marker = [c.marker || c.citation_id, c.intent].filter(Boolean).join(" · ");
  const aminer = ref && ref.aminer_paper_id ? `<circle cx="${{n.x + n.w - 17}}" cy="${{n.y + 17}}" r="7" fill="#0ea5e9"><title>${{esc(UI.aminer)}}</title></circle>` : "";
  return `<g class="node${{selected}}${{dragClass}}" data-id="${{esc(n.id)}}" data-kind="${{n.kind}}">
    <rect x="${{n.x}}" y="${{n.y}}" width="${{n.w}}" height="${{n.h}}" rx="10" fill="#ffffff" stroke="${{n.color}}" stroke-width="1.7"></rect>
    ${{svgText(textParts(marker, 28, 1), n.x + 12, n.y + 21, 12, n.color, "start", 800)}}
    ${{svgText(textParts(title, 30, 2), n.x + 12, n.y + 43, 12, "#172033", "start", 400)}}
    ${{aminer}}
  </g>`;
}}
function edgeHtml(nodes) {{
  const target = nodes.find(n => n.id === "target-paper");
  let html = "";
  const groupNodes = new Map(nodes.filter(n => n.kind === "group").map(n => [n.data.group_id, n]));
  if (layout === "radial") {{
    for (const g of groupNodes.values()) {{
      html += `<path class="edge" d="M${{g.x + g.w}},${{g.y + g.h / 2}} C${{g.x + g.w + 150}},${{g.y + g.h / 2}} ${{target.x - 150}},${{target.y + target.h / 2}} ${{target.x}},${{target.y + target.h / 2}}" fill="none" stroke="#8aa0b6" stroke-width="1.6" opacity=".55" marker-end="url(#arrow)"></path>`;
    }}
  }} else {{
    for (const g of groupNodes.values()) {{
      html += `<path class="edge" d="M${{g.x + g.w}},${{g.y + g.h / 2}} C${{g.x + g.w + 240}},${{g.y + g.h / 2}} ${{target.x - 180}},${{target.y + target.h / 2}} ${{target.x}},${{target.y + target.h / 2}}" fill="none" stroke="#8aa0b6" stroke-width="1.1" opacity=".16" marker-end="url(#arrow)"></path>`;
    }}
  }}
  for (const n of nodes.filter(n => n.kind === "citation")) {{
    const g = groupNodes.get(n.group_id);
    if (!g) continue;
    html += `<path class="edge" d="M${{g.x + g.w}},${{g.y + g.h / 2}} C${{g.x + g.w + 60}},${{g.y + g.h / 2}} ${{n.x - 60}},${{n.y + n.h / 2}} ${{n.x}},${{n.y + n.h / 2}}" fill="none" stroke="${{n.color}}" stroke-width="1.2" opacity=".26"></path>`;
  }}
  return html;
}}
function render() {{
  const citations = filteredCitations();
  currentNodes = layout === "chain" ? chainLayout(citations) : radialLayout(citations);
  establishDefaults(currentNodes);
  svg.removeAttribute("viewBox");
  viewport.innerHTML = `<rect x="0" y="0" width="${{canvasSize.width}}" height="${{canvasSize.height}}" fill="#fbfcff"></rect>${{edgeHtml(currentNodes)}}${{currentNodes.map(nodeHtml).join("")}}`;
  shownCount.textContent = `${{citations.length}} / ${{(GRAPH.citations || []).length}} ${{UI.citations}} ${{UI.shown}}`;
  setTransform();
}}
function setLayout(next) {{
  layout = next;
  layoutButtons.radial.classList.toggle("active", layout === "radial");
  layoutButtons.chain.classList.toggle("active", layout === "chain");
  nodePositions = new Map();
  selectedNodeId = null;
  render();
  focusReadable();
}}
function detailRows(rows) {{
  return `<div class="kv">${{rows.map(([k, v]) => `<div class="muted">${{esc(k)}}</div><div>${{esc(v || "")}}</div>`).join("")}}</div>`;
}}
function showCitation(c) {{
  const ref = refs.get(c.reference_id);
  const traceBadges = (c.trace_ids || []).map(id => `<span class="pill">${{esc(id)}}</span>`).join("");
  let out = `<div class="detail-card">${{detailRows([
    [UI.marker, c.marker || c.citation_id],
    [UI.intent, c.intent],
    [UI.section, c.section],
    [UI.confidence, c.confidence],
    [UI.role, c.cited_work_role || ""]
  ])}}${{traceBadges}}</div>`;
  out += `<div class="detail-card"><strong>${{esc(UI.evidence)}}</strong><p>${{esc(c.evidence || "")}}</p><strong>${{esc(UI.context)}}</strong><p>${{esc(c.context || c.citation_sentence || "")}}</p></div>`;
  if (ref) {{
    out += `<div class="detail-card"><strong>${{esc(UI.reference)}}</strong><p>${{esc(ref.title || ref.marker || ref.reference_id)}}</p><p class="muted">${{esc((ref.authors || []).slice(0, 5).join(", "))}} ${{esc(ref.year || "")}}</p>${{ref.aminer_paper_id ? `<span class="badge">${{esc(UI.aminer)}}: ${{esc(ref.aminer_paper_id)}}</span>` : ""}}</div>`;
  }}
  details.innerHTML = out;
}}
function showTrace(trace) {{
  const steps = (trace.source_steps || []).map(s => `<div class="detail-card"><span class="pill">${{esc(s.citation_id)}}</span><span class="pill">${{esc(s.source_role || "")}}</span><p>${{esc(s.evidence || "")}}</p></div>`).join("");
  details.innerHTML = `<div class="detail-card">${{detailRows([
    [UI.source_traces, trace.trace_id],
    [UI.intent, trace.claim_type],
    [UI.confidence, trace.confidence]
  ])}}</div><div class="detail-card"><strong>${{esc(UI.summary)}}</strong><p>${{esc(trace.summary || trace.target_claim || "")}}</p></div><h3>${{esc(UI.steps)}}</h3>${{steps || `<p class="muted">${{esc(UI.no_items)}}</p>`}}`;
}}
function showTarget() {{
  const p = GRAPH.paper || {{}};
  details.innerHTML = `<div class="detail-card">${{detailRows([
    [UI.target, p.title],
    [UI.year, p.year],
    [UI.aminer, p.aminer_paper_id || ""]
  ])}}</div><div class="detail-card"><strong>${{esc(UI.summary)}}</strong><p>${{esc(p.abstract || "")}}</p></div>`;
}}
function handleNodeClick(id) {{
  selectedNodeId = id;
  if (id === "target-paper") showTarget();
  else if (id.startsWith("group:")) {{
    const group = GROUPS.find(g => `group:${{g.group_id}}` === id);
    details.innerHTML = `<div class="detail-card"><strong>${{esc(group ? group.label : id)}}</strong><p>${{esc((group && group.intent_filters || []).join(", "))}}</p></div>`;
  }} else {{
    const c = (GRAPH.citations || []).find(c => c.citation_id === id);
    if (c) showCitation(c);
  }}
  render();
}}
function renderGroups() {{
  groupList.innerHTML = GROUPS.map(g => `<label class="toggle"><input type="checkbox" checked data-group="${{esc(g.group_id)}}"><span class="swatch" style="background:${{esc(g.color || "#94a3b8")}}"></span><span>${{esc(g.label || g.group_id)}}</span><span class="muted">${{(GRAPH.citations || []).filter(c => (g.intent_filters || []).includes(c.intent)).length}}</span></label>`).join("");
  groupList.querySelectorAll("input[data-group]").forEach(input => {{
    input.addEventListener("change", () => {{
      if (input.checked) activeGroups.add(input.dataset.group); else activeGroups.delete(input.dataset.group);
      allGroups.checked = activeGroups.size === GROUPS.length;
      nodePositions = new Map();
      render();
      focusReadable();
    }});
  }});
}}
function renderTraces() {{
  const items = GRAPH.source_traces || [];
  tracesEl.innerHTML = items.length ? items.map(t => `<div class="trace-item" data-trace="${{esc(t.trace_id)}}"><strong>${{esc(t.claim_id || t.trace_id)}}</strong><p class="muted">${{esc(t.target_claim || t.summary || "")}}</p><span class="pill">${{esc(t.claim_type || "")}}</span><span class="pill">${{(t.source_steps || []).length}} ${{esc(UI.steps)}}</span></div>`).join("") : `<p class="muted">${{esc(UI.no_items)}}</p>`;
  tracesEl.querySelectorAll("[data-trace]").forEach(el => el.addEventListener("click", () => {{
    const trace = traces.get(el.dataset.trace);
    if (trace) showTrace(trace);
  }}));
}}
function initHeader() {{
  const p = GRAPH.paper || {{}};
  document.getElementById("paper-title").textContent = p.title || UI.page_title;
  const stats = [
    `${{(GRAPH.citations || []).length}} ${{UI.citations}}`,
    `${{(GRAPH.source_traces || []).length}} ${{UI.traces}}`,
    p.year ? `${{UI.year}}: ${{p.year}}` : "",
    hasAminer() ? UI.aminer_on : UI.aminer_off
  ].filter(Boolean);
  document.getElementById("stats").innerHTML = stats.map(s => `<span class="stat">${{esc(s)}}</span>`).join("");
}}
function exportSvg() {{
  const clone = svg.cloneNode(true);
  clone.setAttribute("width", canvasSize.width);
  clone.setAttribute("height", canvasSize.height);
  clone.setAttribute("viewBox", `0 0 ${{canvasSize.width}} ${{canvasSize.height}}`);
  clone.querySelector("#viewport").setAttribute("transform", "");
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], {{type: "image/svg+xml"}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = UI.download_name;
  a.click();
  URL.revokeObjectURL(url);
}}
layoutButtons.radial.addEventListener("click", () => setLayout("radial"));
layoutButtons.chain.addEventListener("click", () => setLayout("chain"));
search.addEventListener("input", () => {{ nodePositions = new Map(); render(); focusReadable(); }});
allGroups.addEventListener("change", () => {{
  activeGroups = allGroups.checked ? new Set(GROUPS.map(g => g.group_id)) : new Set();
  groupList.querySelectorAll("input[data-group]").forEach(i => i.checked = allGroups.checked);
  nodePositions = new Map();
  render();
  focusReadable();
}});
document.getElementById("zoom-in").addEventListener("click", () => zoomBy(1.18));
document.getElementById("zoom-out").addEventListener("click", () => zoomBy(0.84));
document.getElementById("fit").addEventListener("click", () => fitToScreen({{readable: false}}));
document.getElementById("reset").addEventListener("click", resetLayout);
document.getElementById("export-svg").addEventListener("click", exportSvg);
wrap.addEventListener("wheel", evt => {{ evt.preventDefault(); zoomBy(evt.deltaY < 0 ? 1.10 : 0.90, evt); }}, {{passive: false}});
svg.addEventListener("mousedown", evt => {{
  const node = evt.target.closest && evt.target.closest(".node");
  if (node && node.dataset.kind === "citation") {{
    const pos = screenToWorld(evt);
    const id = node.dataset.id;
    const base = nodePositions.get(id) || defaultPositions.get(id);
    nodeDrag = {{id, dx: pos.x - base.x, dy: pos.y - base.y}};
    evt.preventDefault();
    return;
  }}
  canvasDrag = {{x: evt.clientX, y: evt.clientY, pan: {{...pan}}}};
  wrap.classList.add("dragging");
}});
window.addEventListener("mousemove", evt => {{
  if (nodeDrag) {{
    const pos = screenToWorld(evt);
    nodePositions.set(nodeDrag.id, {{x: pos.x - nodeDrag.dx, y: pos.y - nodeDrag.dy}});
    render();
    return;
  }}
  if (canvasDrag) {{
    pan.x = canvasDrag.pan.x + evt.clientX - canvasDrag.x;
    pan.y = canvasDrag.pan.y + evt.clientY - canvasDrag.y;
    setTransform();
  }}
}});
window.addEventListener("mouseup", () => {{ nodeDrag = null; canvasDrag = null; wrap.classList.remove("dragging"); }});
svg.addEventListener("click", evt => {{
  const node = evt.target.closest && evt.target.closest(".node");
  if (node) handleNodeClick(node.dataset.id);
}});
svg.addEventListener("dblclick", evt => {{
  const node = evt.target.closest && evt.target.closest(".node");
  if (node && nodePositions.has(node.dataset.id)) {{
    nodePositions.delete(node.dataset.id);
    render();
  }}
}});
window.addEventListener("resize", fitToScreen);
initHeader();
renderGroups();
renderTraces();
render();
focusReadable();
</script>
</body>
</html>
"""


def read_graph(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Graph JSON must contain an object at the top level.")
    return data


def infer_language(graph: dict[str, Any], requested: str) -> str:
    if requested in {"zh", "en"}:
        return requested
    value = str(graph.get("metadata", {}).get("output_language", "")).lower()
    if value.startswith("zh") or value in {"cn", "chinese"}:
        return "zh"
    return "en"


def localized_groups(language: str) -> list[dict[str, Any]]:
    label_key = "label_zh" if language == "zh" else "label_en"
    chain_key = "chain_zh" if language == "zh" else "chain_en"
    return [
        {
            "group_id": group["group_id"],
            "label": group[label_key],
            "chain_label": group[chain_key],
            "intent_filters": group["intents"],
            "color": group["color"],
        }
        for group in CANONICAL_GROUPS
    ]


def citation_priority(citation: dict[str, Any]) -> float:
    trace_score = 100.0 if citation.get("trace_ids") else 0.0
    try:
        confidence = float(citation.get("confidence") or 0) * 10.0
    except (TypeError, ValueError):
        confidence = 0.0
    visible = -100.0 if citation.get("show_on_map") is False else 0.0
    return trace_score + confidence + visible


def sorted_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in items if item.get("show_on_map") is not False],
        key=lambda item: (-citation_priority(item), str(item.get("citation_id") or "")),
    )


def limited_citations(items: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    sorted_items = sorted_citations(items)
    return sorted_items[:limit], max(0, len(sorted_items) - limit)


def group_citations(graph: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    citations = graph.get("citations") if isinstance(graph.get("citations"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = {group["group_id"]: [] for group in groups}
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        for group in groups:
            if citation.get("intent") in group["intent_filters"]:
                grouped[group["group_id"]].append(citation)
                break
    return grouped


def text_parts(value: Any, max_chars: int, max_lines: int) -> list[str]:
    raw = " ".join(str(value or "").split())
    if not raw:
        return [""]
    has_spaces = " " in raw
    words = raw.split(" ") if has_spaces else list(raw)
    joiner = " " if has_spaces else ""
    lines: list[str] = []
    line = ""
    for word in words:
        next_line = f"{line}{joiner}{word}" if line else word
        if len(next_line) > max_chars and line:
            lines.append(line)
            line = word
        else:
            line = next_line
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and line:
        lines.append(line)
    if len(lines) == max_lines and len("".join(words)) > len("".join(lines)):
        lines[-1] = lines[-1].rstrip(",.，。;；:：") + "..."
    return lines or [raw[:max_chars]]


def svg_text(lines: list[str], x: float, y: float, size: int, color: str, anchor: str = "start", weight: int = 400) -> str:
    return "\n".join(
        f'<text x="{x:.1f}" y="{y + idx * (size + 5):.1f}" fill="{html.escape(color, quote=True)}" '
        f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{html.escape(line)}</text>'
        for idx, line in enumerate(lines)
    )


def radial_nodes(graph: dict[str, Any], language: str) -> tuple[list[dict[str, Any]], dict[str, float]]:
    groups = localized_groups(language)
    grouped = group_citations(graph, groups)
    canvas = {
        "width": 4000,
        "height": 2700,
    }
    cx = canvas["width"] / 2
    cy = canvas["height"] / 2
    col_step = 318
    row_step = 146
    slots = {
        "problem-background": {"gx": cx, "gy": cy - 760, "side": "top"},
        "method-core": {"gx": cx + 760, "gy": cy - 350, "side": "right"},
        "data-eval": {"gx": cx + 680, "gy": cy + 570, "side": "right"},
        "baseline-result": {"gx": cx - 680, "gy": cy + 570, "side": "left"},
        "limits-future": {"gx": cx - 760, "gy": cy - 350, "side": "left"},
    }
    nodes = [
        {
            "id": "target-paper",
            "kind": "target",
            "x": cx - 150,
            "y": cy - 72,
            "w": 300,
            "h": 144,
            "color": "#0f172a",
            "data": graph.get("paper") if isinstance(graph.get("paper"), dict) else {},
        }
    ]
    for group in groups:
        slot = slots.get(group["group_id"], {"gx": cx, "gy": cy - 760, "side": "top"})
        gx = slot["gx"]
        gy = slot["gy"]
        group_node = dict(group)
        group_node["label"] = group["label"]
        nodes.append({"id": f"group:{group['group_id']}", "kind": "group", "x": gx - 86, "y": gy - 46, "w": 172, "h": 92, "color": group["color"], "data": group_node})
        shown, overflow = limited_citations(grouped[group["group_id"]], RADIAL_MAX_PER_GROUP)
        cols = max(1, min(3, math.ceil(math.sqrt(len(shown) or 1))))
        rows = math.ceil(len(shown) / cols) if shown else 1
        grid_height = (rows - 1) * row_step + 80
        start_x = gx - (cols - 1) * col_step / 2 - 118
        start_y = gy - 320 - (rows - 1) * row_step
        if slot["side"] == "right":
            start_x = gx + 300
            start_y = gy - grid_height / 2
        elif slot["side"] == "left":
            start_x = gx - 300 - (cols - 1) * col_step - 236
            start_y = gy - grid_height / 2
        for item_index, citation in enumerate(shown):
            col = item_index % cols
            row = item_index // cols
            x = start_x + col * col_step
            y = start_y + row * row_step
            nodes.append({"id": citation.get("citation_id"), "kind": "citation", "x": x, "y": y, "w": 236, "h": 80, "color": group["color"], "data": citation, "group_id": group["group_id"]})
        if overflow:
            x = start_x + (cols - 1) * col_step / 2 + 46
            y = start_y + rows * row_step + 20
            nodes.append({"id": f"overflow:{group['group_id']}", "kind": "overflow", "x": x, "y": y, "w": 144, "h": 44, "color": group["color"], "data": {"label": f"+{overflow}"}, "group_id": group["group_id"]})
    return nodes, canvas


def chain_nodes(graph: dict[str, Any], language: str) -> tuple[list[dict[str, Any]], dict[str, float]]:
    groups = localized_groups(language)
    grouped = group_citations(graph, groups)
    lane_height = 220
    max_items = max(1, *(len(limited_citations(grouped[group["group_id"]], CHAIN_MAX_PER_GROUP)[0]) for group in groups))
    canvas = {
        "width": max(2200, 780 + math.ceil(max_items / 2) * 330),
        "height": max(1200, len(groups) * lane_height + 340),
    }
    target_x = canvas["width"] - 360
    target_y = canvas["height"] / 2 - 76
    nodes = [
        {
            "id": "target-paper",
            "kind": "target",
            "x": target_x,
            "y": target_y,
            "w": 300,
            "h": 152,
            "color": "#0f172a",
            "data": graph.get("paper") if isinstance(graph.get("paper"), dict) else {},
        }
    ]
    for index, group in enumerate(groups):
        y = 150 + index * lane_height
        group_node = dict(group)
        group_node["label"] = group["chain_label"]
        nodes.append({"id": f"group:{group['group_id']}", "kind": "group", "x": 70, "y": y - 46, "w": 196, "h": 92, "color": group["color"], "data": group_node})
        shown, overflow = limited_citations(grouped[group["group_id"]], CHAIN_MAX_PER_GROUP)
        for item_index, citation in enumerate(shown):
            col = item_index // 2
            row = item_index % 2
            x = 330 + col * 330
            yy = y - 76 + row * 96
            nodes.append({"id": citation.get("citation_id"), "kind": "citation", "x": x, "y": yy, "w": 270, "h": 82, "color": group["color"], "data": citation, "group_id": group["group_id"]})
        if overflow:
            x = 330 + math.ceil(len(shown) / 2) * 330
            nodes.append({"id": f"overflow:{group['group_id']}", "kind": "overflow", "x": x, "y": y - 24, "w": 150, "h": 48, "color": group["color"], "data": {"label": f"+{overflow}"}, "group_id": group["group_id"]})
    return nodes, canvas


def render_node_svg(node: dict[str, Any], graph: dict[str, Any], language: str) -> str:
    ui = I18N[language]
    x, y, w, h = (float(node["x"]), float(node["y"]), float(node["w"]), float(node["h"]))
    color = str(node.get("color") or "#64748b")
    kind = node.get("kind")
    if kind == "target":
        paper = node.get("data") if isinstance(node.get("data"), dict) else {}
        title = text_parts(paper.get("title") or ui["target"], 30, 3)
        authors = paper.get("authors") if isinstance(paper.get("authors"), list) else []
        sub = " · ".join(str(part) for part in [f"{ui['year']}: {paper.get('year')}" if paper.get("year") else "", ", ".join(str(author) for author in authors[:2])] if part)
        return "\n".join(
            [
                f'<g class="node target"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="#ffffff" stroke="{color}" stroke-width="2"/>',
                svg_text([ui["target"]], x + w / 2, y + 28, 13, "#64748b", "middle", 700),
                svg_text(title, x + w / 2, y + 58, 16, "#0f172a", "middle", 800),
                svg_text(text_parts(sub, 34, 1), x + w / 2, y + h - 26, 12, "#64748b", "middle", 400),
                "</g>",
            ]
        )
    if kind == "group":
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        label = text_parts(data.get("label") or data.get("group_id"), 16, 2)
        return "\n".join(
            [
                f'<g class="node group"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="14" fill="{color}" stroke="{color}" stroke-width="2"/>',
                svg_text(label, x + w / 2, y + 36, 15, "#ffffff", "middle", 800),
                "</g>",
            ]
        )
    if kind == "overflow":
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        return "\n".join(
            [
                f'<g class="node overflow"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="999" fill="#ffffff" stroke="{color}" stroke-width="1.5" stroke-dasharray="5 5"/>',
                svg_text(text_parts(data.get("label"), 18, 1), x + w / 2, y + 28, 13, color, "middle", 800),
                "</g>",
            ]
        )
    citation = node.get("data") if isinstance(node.get("data"), dict) else {}
    refs = {ref.get("reference_id"): ref for ref in graph.get("references", []) if isinstance(ref, dict)}
    ref = refs.get(citation.get("reference_id"), {})
    title = citation.get("target_claim") or citation.get("evidence") or ref.get("title") or citation.get("marker") or citation.get("citation_id")
    marker = " · ".join(str(part) for part in [citation.get("marker") or citation.get("citation_id"), citation.get("intent")] if part)
    aminer = ""
    if ref.get("aminer_paper_id"):
        aminer = f'<circle cx="{x + w - 17:.1f}" cy="{y + 17:.1f}" r="7" fill="#0ea5e9"><title>{html.escape(ui["aminer"])}</title></circle>'
    return "\n".join(
        [
            f'<g class="node citation"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="#ffffff" stroke="{color}" stroke-width="1.7"/>',
            svg_text(text_parts(marker, 28, 1), x + 12, y + 21, 12, color, "start", 800),
            svg_text(text_parts(title, 32, 2), x + 12, y + 44, 12, "#172033", "start", 400),
            aminer,
            "</g>",
        ]
    )


def render_edges_svg(nodes: list[dict[str, Any]]) -> str:
    target = next((node for node in nodes if node.get("id") == "target-paper"), None)
    if not target:
        return ""
    groups = {node["data"]["group_id"]: node for node in nodes if node.get("kind") == "group" and isinstance(node.get("data"), dict)}
    edges: list[str] = []
    tx = float(target["x"])
    ty = float(target["y"]) + float(target["h"]) / 2
    is_chain = any(group.get("x") == 70 for group in groups.values())
    if not is_chain:
        for group in groups.values():
            gx = float(group["x"]) + float(group["w"])
            gy = float(group["y"]) + float(group["h"]) / 2
            edges.append(f'<path class="edge" d="M{gx:.1f},{gy:.1f} C{gx + 150:.1f},{gy:.1f} {tx - 150:.1f},{ty:.1f} {tx:.1f},{ty:.1f}" fill="none" stroke="#8aa0b6" stroke-width="1.6" opacity=".55" marker-end="url(#arrow)"/>')
    else:
        for group in groups.values():
            gx = float(group["x"]) + float(group["w"])
            gy = float(group["y"]) + float(group["h"]) / 2
            edges.append(f'<path class="edge" d="M{gx:.1f},{gy:.1f} C{gx + 240:.1f},{gy:.1f} {tx - 180:.1f},{ty:.1f} {tx:.1f},{ty:.1f}" fill="none" stroke="#8aa0b6" stroke-width="1.1" opacity=".16" marker-end="url(#arrow)"/>')
    for node in nodes:
        if node.get("kind") != "citation":
            continue
        group = groups.get(node.get("group_id"))
        if not group:
            continue
        gx = float(group["x"]) + float(group["w"])
        gy = float(group["y"]) + float(group["h"]) / 2
        nx = float(node["x"])
        ny = float(node["y"]) + float(node["h"]) / 2
        color = html.escape(str(node.get("color") or "#64748b"), quote=True)
        edges.append(f'<path class="edge" d="M{gx:.1f},{gy:.1f} C{gx + 60:.1f},{gy:.1f} {nx - 60:.1f},{ny:.1f} {nx:.1f},{ny:.1f}" fill="none" stroke="{color}" stroke-width="1.2" opacity=".26"/>')
    return "\n".join(edges)


def render_svg(graph: dict[str, Any], language: str, layout: str) -> str:
    nodes, canvas = chain_nodes(graph, language) if layout == "chain" else radial_nodes(graph, language)
    title = graph.get("paper", {}).get("title") if isinstance(graph.get("paper"), dict) else I18N[language]["page_title"]
    body = "\n".join([render_edges_svg(nodes)] + [render_node_svg(node, graph, language) for node in nodes])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{canvas["width"]:.0f}" height="{canvas["height"]:.0f}" viewBox="0 0 {canvas["width"]:.0f} {canvas["height"]:.0f}" role="img" aria-label="{html.escape(str(title), quote=True)}">
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
    <path d="M1,1 L9,5 L1,9 Z" fill="#8aa0b6"/>
  </marker>
  <filter id="nodeShadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.13"/>
  </filter>
</defs>
<style>
  svg {{ background: #fbfcff; font-family: Arial, "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }}
  .node rect {{ filter: url(#nodeShadow); }}
  .edge {{ pointer-events: none; }}
</style>
<rect x="0" y="0" width="{canvas["width"]:.0f}" height="{canvas["height"]:.0f}" fill="#fbfcff"/>
{body}
</svg>
'''


def default_output_path(graph_path: Path) -> Path:
    if graph_path.name == "citation_graph.json" and graph_path.parent.name == "graph" and graph_path.parent.parent.name == "json":
        return graph_path.parent.parent.parent / "citation_map.html"
    return graph_path.with_name("citation_map.html")


def default_svg_output_path(html_output_path: Path) -> Path:
    return html_output_path.with_name("citation_map.svg")


def default_chain_output_path(html_output_path: Path) -> Path:
    return html_output_path.with_name("citation_map_chain.svg")


def render_html(graph: dict[str, Any], language: str) -> str:
    ui = I18N[language]
    paper = graph.get("paper") if isinstance(graph.get("paper"), dict) else {}
    title = html.escape(str(paper.get("title") or ui["page_title"]), quote=True)
    graph_json = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    ui_json = json.dumps(ui, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    groups_json = json.dumps(localized_groups(language), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html_lang = "zh-CN" if language == "zh" else "en"
    return HTML_TEMPLATE.format(
        html_lang=html_lang,
        title=title,
        graph_json=graph_json,
        ui_json=ui_json,
        groups_json=groups_json,
        radial_max_per_group=RADIAL_MAX_PER_GROUP,
        chain_max_per_group=CHAIN_MAX_PER_GROUP,
        **{key: html.escape(value, quote=True) for key, value in ui.items()},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Paper Source Trace citation_map.html and static SVG maps from citation_graph.json.")
    parser.add_argument("--graph", required=True, type=Path, help="Path to json/graph/citation_graph.json.")
    parser.add_argument("--output", type=Path, help="Output citation_map.html path. Defaults to the Paper Source Trace output root.")
    parser.add_argument("--language", choices=["zh", "en", "auto"], default="auto", help="Visible UI language.")
    parser.add_argument("--svg", choices=["radial", "chain", "both", "none"], default="none", help="Optional static SVG output mode.")
    parser.add_argument("--svg-output", type=Path, help="Output path for radial SVG, or chain SVG when --svg chain is used.")
    parser.add_argument("--chain-output", type=Path, help="Output path for chain SVG when --svg both is used.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = args.graph.resolve()
    graph = read_graph(graph_path)
    language = infer_language(graph, args.language)
    output_path = (args.output.resolve() if args.output else default_output_path(graph_path).resolve())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_html(graph, language))
    print(f"Rendered {output_path}")

    if args.svg != "none":
        svg_output = (args.svg_output.resolve() if args.svg_output else default_svg_output_path(output_path).resolve())
        svg_output.parent.mkdir(parents=True, exist_ok=True)

        if args.svg == "chain":
            with svg_output.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_svg(graph, language, "chain"))
            print(f"Rendered {svg_output}")
        else:
            with svg_output.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_svg(graph, language, "radial"))
            print(f"Rendered {svg_output}")

        if args.svg == "both":
            chain_output = (args.chain_output.resolve() if args.chain_output else default_chain_output_path(output_path).resolve())
            chain_output.parent.mkdir(parents=True, exist_ok=True)
            with chain_output.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(render_svg(graph, language, "chain"))
            print(f"Rendered {chain_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
