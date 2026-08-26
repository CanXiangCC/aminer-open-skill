# Research Loop

You are the controller. Round 0 scouts the question and induces the report's outline from what came back; every later round fills that outline. Nothing enters the report that is not in the ledger, and no section exists that `evidence.py render` did not print.

## Round 0 — scout, then induce

Do not decide the report's topics before retrieval. Find out what the literature actually contains, then let the outline follow.

1. Write down the research object, time window, audience, and output language. State assumptions instead of asking about optional constraints.

2. Create the ledger. Pick the genre from the task framing — it drives `check`'s figures-expected rule, so set it here, not later: `academic` (default — literature reviews, research landscapes, entity investigations) or `industry` (industry / market surveys: "行业调研", "市场格局", "竞争格局"). An industry topic initialised as `academic` will **not** warn when it ships without figures, so the genre must be set at `init` and cannot be added to an existing ledger without re-init.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" init --topic "LLM agent long-term memory"
# industry / market survey:
# python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" init --topic "中国大模型行业调研" --genre industry
```

3. **Scout with 3–4 topic probes.** `paper_qa_search_pro` is the search of record: ¥0.70 per call, about ¥2.80 for the whole scout. Register each probe before you run it — the ledger uses the registration to measure whether the probe earned its keep.

**Send the query in `query_type: "auto"` — query mode — unless you need literal term matching.** `auto` runs a server-side LLM over your text and parses it into topic, filters, translation and sort intent. Measured: about 5 s per call against about 0.4 s for the non-LLM modes — slower, but comfortably inside the uniform 30 s timeout. You pay that latency for recall, and the recall is the point.

`query_type: "topic"` skips the LLM and matches `title` / `title_zh` / `keywords` / `abstract` **literally** — which means a multi-concept phrase gets pulled toward whichever term dominates the index. Measured on the same subject:

| Query | Mode | Result |
| --- | --- | --- |
| `"efficient large language model architecture mixture of experts long context"` | `topic` | ten long-context inference papers, **zero** on mixture-of-experts |
| `"mixture of experts sparse activation in large language models"` | `auto` | ten MoE-on-LLM papers including two dedicated surveys |
| `"sparse expert routing in language model backbones"` + `all_terms:["mixture of experts"]` | `topic` | ten MoE routing papers; `total` narrowed from `gte 10000` to `eq 1058` |

Query mode recovered a subfield that literal matching had silently dropped. `topic` recovers it too — but only once `all_terms` pins the concept, which is the point of that field.

**Separate probes by object and filter, not by wording.** What makes a second probe worth ¥0.70 is a different topic phrase, a different entity, or a different structured filter — `all_terms` / `any_terms` / `venues` / `year_from` / `min_citations`. The two MoE probes above differ that way and returned 19 distinct papers out of 20, overlapping on one. Two probes that differ only in phrasing do the opposite: `auto` normalises differently-worded questions down to the same parsed topic, so "how is long-term memory implemented in LLM agents" and "how is long-term memory in LLM agents evaluated" came back with 8 of the same 10 papers. Rephrasing is not a second probe; `gaps` reports it as `low_yield_probes`.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis topic --via paper_qa_search_pro \
  --query "long-term memory for LLM agents"
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro \
  --params '{"query":"long-term memory for LLM agents","query_type":"auto","year_from":2024,"sort":"balanced"}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --probe p1

python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis topic --via paper_qa_search_pro \
  --query "memory poisoning and privacy in agents"
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro \
  --params '{"query":"agent memory security","query_type":"auto","any_terms":["poisoning","privacy","injection"],"year_from":2024}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --probe p2
```

Three properties of this endpoint shape the scout:

- **Page size is fixed at 10.** Do not send `size`. Four probes give about forty results — enough to induce an outline, not enough to be the whole evidence base. Paginating with `cursor` costs another ¥0.70 per page, and a cursor request may carry nothing but the cursor.
- **Search results carry no abstract** — only `paper_id`, `title`, `title_zh`, `authors[].name`, `year`. Step 4 is not optional.
- **Read `warnings` and `total`.** `aminer_open.py` hoists both onto the result. A warning such as `QUERY_CONDITION_IGNORED` means the query that ran is not the query you sent.

`total` tells you how thin your slice is, and it has a required response:

| `total` | What it means | What to do |
| --- | --- | --- |
| `{"relation":"gte","value":10000}` | your ten results are under 0.1% of the field | narrow with `all_terms` / `venues` / `min_citations` / a tighter `year_from`, or spend one ¥0.70 `cursor` page — and say in Limitations that the slice was thin |
| `{"relation":"eq","value":9666}` | still a broad field, same treatment | as above |
| `{"relation":"eq","value":34}` | you have nearly all of it | move on; no more spending on this axis |

**If the request is in Chinese, run at least one probe against the Chinese corpus** — `language_preference` or `has_chinese_title` — or record in Limitations that only English-language literature was retrieved. English topic phrases against an English index silently exclude the Chinese half of the corpus.

Add one or two `WebSearch` / `WebFetch` probes for framing that papers do not carry (vendor positions, standards, leaderboards). Register them like any other probe:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis web --via WebFetch --query "AI Index 2026 technical performance"
```

**Industry-report genre (when the task framing is an industry / market survey — "行业调研", "industry report", "市场格局").** The spine of evidence is the web, not papers. Run **3–5 web probes in Round 0**, one per industry dimension: market size and growth (IDC / 艾瑞 / 亿欧 / Statita), the player set and their funding or valuation (company filings, IT 桔子 / Crunchbase-style data, news), supply chain and compute (US export controls, H800 / H100, domestic chips such as 华为昇腾, 智算中心 capacity), and the policy frame. Put every number you will cite or plot into the ledger as a **datum** — a first-class data point, not free text in a `note` — the moment you read the page: `evidence.py datum add --source N --metric "市场规模" --value 410 --unit 亿元 --year 2024 --entity 中国`. Datums are addressable by id (`d1`, `d2`…), so `gaps` can enumerate exactly which numbers you have and which you lack, and `check` warns (`industry_web_sources_without_datums`) when a web source was fetched but no number was extracted from it — the page is in the ledger but its quantitative content evaporated, which is the precise failure mode that starves figures. The web source's `note` may still hold the surrounding sentence for context, but the number itself must be a datum. Capture at retrieval time, not at wrap-up: a number left in context is, by figure time, gone. `paper_qa_search_pro` is still the search of record for the academic slices of an industry report (technology evolution, evaluation) and patents are the IP channel, but they are de-emphasised, not displaced. Induce the outline from what came back: the Genre B skeleton in `references/report-format.md` is the expected shape, but drop a section the evidence does not support rather than pad it — an industry report that silently omits market size, players, or supply chain is incomplete. The ledger was initialised with `--genre industry` in step 2; that is what makes `check` warn `figures_industry_expected` if the report ships without a figure — the figures-expected rule is enforced by `check`, not just advised here.

Scout hits go in untagged — the outline does not exist yet. They land in `untagged_sources` until you tag or drop them.

4. **Triage free, then read the keepers properly.** Retire the drift first:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" drop --source 21 23 --reason "domain application, memory not the object of study"
```

A dropped source keeps its number — renumbering would repoint every citation — but leaves the reference list and every coverage count. (The ledger itself never renumbers; the delivered report's dense ascending numbers are assigned by `render --renumber` from the draft, and citing a dropped source in a draft is a hard error.) `drop` refuses a source a claim already relies on, and re-adding a source later revives it.

**Watch what the drop rate says about the probe.** A probe can return ten brand-new papers and still have failed: if triage throws eight of them away, the query matched a vocabulary that belongs to another field. `gaps` reports this as `drifting_probes`, separately from `low_yield_probes` — duplication and drift are different failures and have different fixes.

The fix for drift is to pin the concept, not to reword:

```bash
# 8 of 10 hits were retinopathy / wave-segmentation uses of Mamba, not LLM backbones
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro --params '{
  "query":"sparse expert routing in language model backbones",
  "query_type":"topic",
  "all_terms":["mixture of experts"],
  "exclude_terms":["segmentation","retinopathy","forecasting"],
  "year_from":2025}'
```

`all_terms` forces every result to contain the concept you actually meant; `exclude_terms` kills the domain vocabulary that hijacked the probe. That is what "change the retrieval axis" means in practice — reaching for a synonym instead buys the same ten papers again.

Then read in two steps, cheapest first:

```bash
# free, truncated abstract slices — enough to sort papers into clusters
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_info --params '{"ids":["...","..."]}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer

# ¥0.01 each, full abstract and keywords — required for anything a claim will cite
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_detail --params '{"id":"..."}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer
```

The ledger records how deeply each source was read as `depth`: `search` from a search response, `slice` from `paper_info`, `detail` from `paper_detail`. A slice is truncated mid-sentence — about 190 characters against roughly 1,400 in the full abstract — so it tells you what a paper is about but not what it found. `check` warns with `cited_sources_without_detail` for any non-web source a claim leans on that never reached `detail`. At ¥0.01 a call there is no cost argument for leaving one there.

5. **Induce the outline from what survived.** Group the remaining titles and abstracts into 2–4 top-level sections, each with 2–4 subsections. Every top-level section carries exactly one `"kind":"disagreement"` subsection — that is where counter-evidence and unresolved tension go, and it is what replaces the old practice of picking opposing angles up front. Each section cites the probes it was induced from.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" outline set --json '[
  {"title":"Memory architectures","from_probes":["p1","p2"],"children":[
    {"title":"Hierarchical and multi-store designs"},
    {"title":"Write-time consolidation policies"},
    {"title":"Disagreement: explicit memory vs long context","kind":"disagreement"}]},
  {"title":"Evaluation","from_probes":["p3"],"children":[
    {"title":"Benchmarks in use"},
    {"title":"Disagreement: contested benchmark validity","kind":"disagreement"}]}]'
```

Section ids are assigned by the script, never by you. `outline set` refuses a section with no `from_probes`; if you genuinely could not scout, pass `--allow-unscouted` and the report must disclose it.

6. `--dry-run` the paid chain for the rounds ahead and check the total against the budget.

## Patents (industry-report tasks only)

Apply this section only when the task framing identifies an industry report. Literature reviews and other genres skip it entirely — patents are not mandatory there. The task framing comes from the prompt that started the run; if it does not say "industry report", do not run patent probes.

An industry report treats patents as a second evidence channel alongside papers, not as a standalone chapter. Patents are mandatory for an industry report — wherever they strengthen the analysis (technology ownership, enterprise portfolios, filing trends, or anywhere else a claim leans on technical reality), retrieve and cite them. Do not decide in advance which sections will use patents; scout the field first and let the outline follow where the patent evidence actually lands, the same rule as paper probes.

- **Round 0 scout.** In addition to the 3–4 paper probes, run 1–4 `patent_search` probes (free, no budget impact) — at least one is mandatory, and more are warranted when the field splits along distinct technology lines or applicant camps. `patent_search` exposes only `query`/`page`/`size`, so unlike paper probes you cannot steer it with structured filters — the only honest way to make a second patent probe worth running is a different technology line or applicant direction, not a reworded query. One probe with `size: 20` on the core technology term is the floor; split into 2–4 only when the scout reveals genuinely distinct technology branches. Register each like any probe:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis patent --via patent_search \
  --query "autonomous driving lidar"
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api patent_search \
  --params '{"query":"autonomous driving lidar","size":20}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --probe p4
```

A `patent_search` result carries `paper_id`-style `id`, `title`, `title_zh`, `inventor_name`, `app_year`, `pub_year` — enough to triage, not enough to cite a finding. Page size defaults to 8; raise `size` (max 100) for a landscape probe since the call is free.

- **Each round, retrieve.** Run `patent_search` (free) as a dual source alongside `paper_qa_search_pro` on any axis where patent evidence is relevant — do not pre-assign patents to fixed sections; let each section's evidence needs decide. Separate patent probes by technology term or applicant, not by rewording — the same rule as paper probes.

- **Read what you cite.** `patent_info` (free) triages a batch of IDs; `patent_detail` (¥0.01) gives the full abstract, assignee, IPC/CPC, and dates. A claim that leans on a patent must reach `patent_detail`, the same way a paper claim must reach `paper_detail` — `check` warns with `cited_sources_without_detail` for either.

- **Enterprise portfolios.** A `patent_detail` call persists each patent's `assignee` / applicant (the primary rights holder), so a per-assignee corpus chart assembles straight from the ledger — `figure add --from-source-metadata --field assignee --sources … --type hbar` — once the detail calls have run. For a *named* organization's full portfolio, `org_search` (free) → `org_patent_relation` (¥0.10) still retrieves its patent set with the org dimension intact:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api org_search --params '{"orgs":["华为"]}'
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api org_patent_relation \
  --params '{"id":"<org_id>","page":1,"page_size":100}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer
```

Otherwise record the assignee in the claim `--text` or a web-source `note` at retrieval time; never reconstruct it from memory.

- **Filing trends.** `evidence.py` coerces a patent's `app_year` / `pub_year` string and `app_date` / `pub_date` epoch into an integer `year`, so a filings-per-year chart assembles from the ledger — `figure add --from-source-metadata --field year --sources … --type bar`. A patent added by `patent_search` alone (scout, no detail call) ships a year only when its `app_year` is present; reach `patent_detail` for any patent you intend to chart.

## Each round (default budget: 4 rounds)

### 1. Retrieve

Per round, run at most **2 paid `paper_qa_search_pro` calls** plus any number of ¥0.01 `paper_search_pro` calls, and at most 3 native web calls, spread across sections that still need evidence.

The cap sits on the ¥0.70 endpoint because that is where the money goes. A real run spent ¥6.09: ¥5.60 on eight searches and ¥0.49 on forty-nine full abstracts. Rationing abstracts protects pennies while an unnecessary search costs seventy times as much.

**Two searches in the same round must be semantically distant: a different outline section *and* a different retrieval axis** — time window, subfield, named entity, venue, or method-versus-critique framing. Rewording the same question is not a second search.

This is not a style rule. In a real run, two near-synonym `paper_qa_search_pro` queries at ¥0.70 each ("architectures for X" and "benchmarks for X") returned 10 results of which 9 were identical: ¥0.70 bought one new source. `gaps` reports this as `low_yield_probes`. When it fires, change the axis — do not retry the phrasing.

Route by query shape, not by habit:

- **Topic or multi-filter search** → `paper_qa_search_pro` at ¥0.70, the default. Send the query in `query_type: "auto"`; drop to `"topic"` only for literal term matching, and pin the concept with `all_terms` when you do. Page size is fixed at 10 and search results carry no abstract, so pair it with `paper_info`, then `paper_detail` for whatever a claim will cite.
- **Structured filter** (author / org / venue / keyword, with citation or year ordering) → `paper_search_pro` at ¥0.01, when you already know exactly what you are filtering on. **After the scout you usually do know** — establishing the field's controlled vocabulary is what the scout was for, so later axes should reach for the ¥0.01 endpoint first and escalate to Pro only when a single filter cannot express the query. It matches terms, not questions: a single controlled term for `keyword`, a two- or three-word phrase for `title` / `abstract`. A sentence answers 200 with `"msg": "no data"` and still bills — `add --aminer` reports that as `paid_calls_without_hits`.
  Short is not the same as precise. Use a term only the target literature uses: in a real run `keyword=agent memory` returned 2004–2014 multi-agent traffic simulation because that phrase predates LLM agents, while `keyword=agentic memory` returned the intended work. A drifting probe tells you about the field's vocabulary; it is not a reason to spend again.
- Free discovery endpoints first for entities; see `references/api-reference.md`.
- Native `WebSearch` and `WebFetch` are the source of record for anything AMiner does not hold: first-party project pages, model or standard documentation, release notes, benchmark leaderboards, current news. Use `WebFetch` on the specific page rather than trusting a search snippet. If native web tools are unavailable, continue AMiner-only and record that limitation now, not at the end.

### 2. Record

**Pipe results in untagged, then tag the keepers by number.** A search returns relevance and noise together; `add --aminer --section 3.2` would tag the whole batch, and noise tagged into a section inflates that section's coverage with papers no claim will ever cite.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro \
  --params '{"query":"how is agent memory evaluated","sort":"balanced","year_from":2024}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --probe p3

# read the titles, then place only what belongs
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --section 2.1 --json '[{"kind":"paper","id":"<id>","title":"..."}]'
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" drop --source 49 61 --reason "off topic for this question"
```

Re-adding a source that is already in the ledger merges the new section tag onto it — that is the intended way to place a hit after the fact. If a bulk add over-tagged, `evidence.py untag --source N --section 3.2` removes just that tag.

Web evidence is recorded the same way — and **put the figures you are going to cite into `note`**. A web source stores only what you record; a number lifted from a fetched page and never written down cannot be checked by anything afterwards, and `check` will flag the claim as `claims_with_unsourced_numbers`:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --via WebFetch --section 2.2 --probe p5 --json \
  '[{"kind":"web","title":"Benchmark documentation — metric definitions","url":"https://...",
     "note":"opened 2026-08-06; reports 66.3% on OSWorld, 89.4% on RLBench, 12% on real household tasks"}]'
```

`add --aminer` reads the paid cost out of the response and accumulates it, so the running total is always in the ledger. A search that returned nothing usable still cost money — it shows up as `paid_calls_without_hits`, and a paid call you never piped through `add` needs `evidence.py spend --api <name> --cny <price>`.

A ledger full of padding is worse than a short one.

### 3. Read

- Free `paper_info` gives a truncated abstract slice for a batch of IDs; use it to triage before paying.
- Then buy `paper_detail` at ¥0.01 for every item the report will lean on (default: at most 50 across the whole task — an outline of four sections needs at least twenty-four, so a tighter cap just forces an overrun). A slice is roughly 190 characters and stops mid-sentence; the full abstract is around 1,400 and is where the actual findings are. `check` warns with `cited_sources_without_detail` for anything you cite without it.
- Both calls store their text in the ledger, so `evidence.py source show --source 12` gives you the abstract back later without a second purchase, and the citation checks have something to compare against.
- Record what each source actually supports:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" claim --section 2.1 --supports 3 7 \
  --text "Reference-free LLM-judge metrics are the dominant reported evaluation method since 2024"
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" claim --section 2.2 --type interpretation --supports 3 \
  --conflict "source 9 reports the opposite trend" \
  --text "Judge agreement with humans is likely overstated on long-form answers"
```

A section's claims are the natural unit of work, so record them together rather than one subprocess at a time:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" claim --batch --json '[
  {"section":"2.1","supports":[3,7],"text":"..."},
  {"section":"2.2","supports":[3],"type":"interpretation","conflict":"source 9 disagrees","text":"..."}]'
```

`--batch` records what validates and reports the rest under `failed`; it exits 1 if anything failed, so nothing is silently skipped.

Mark analysis as `--type interpretation`. Never state an interpretation as an observation. A claim must name a section — a claim that belongs nowhere in the outline cannot be written anywhere in the report.

**Check the figures.** `gaps` reports `claims_with_unsourced_numbers` for any decimal or 3-plus-digit number in a claim that appears in none of the sources it cites. This is the one error that used to be invisible: in a real run two claims carried benchmark figures from a web page while citing papers, and only a manual reread caught it. Unit and language conversions land here too ("4 million" written as "400 万"), so read the finding before acting — but read it.

When a citation is wrong, withdraw the claim and record it again — the id stays reserved, so nothing renumbers:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" retract --claim c4 --reason "cited source 30, meant 32"
```

### 3b. Figure

A figure is **expected for an industry report (Genre B)** and **optional for an academic review (Genre A)**. `check` warns (`figures_industry_expected`) when a Genre B report ships with zero figures, (`figures_industry_quantitative_expected`) when a Genre B report ships no quantitative chart — a `timeline` alone does not satisfy it, the thin-web case this section exists to head off — and (`figures_thin_data`) when a registered figure has too few points to plot meaningfully — a one-bar bar chart, a one-point line, a one-event timeline is a defect, not a figure. **Pick the figure from the data you actually have.** A quantitative chart (`bar` / `hbar` / `line` / `pie` / `heatmap`) runs on numbers the ledger verified; a structural `timeline` runs on *dated events* (model releases, funding rounds, policy milestones) and leans on dates and labels, not on market-share percentages. When your web retrieval came back thin on numbers — no market shares, no funding totals — there are three fallbacks before you reach for the timeline, and you do **not** skip the figure or pad it with an unsourced number:

1. **A datum-backed chart** if you captured *any* numbers at all — even a few. `figure add --from-datums d1 d2 …` assembles a quantitative chart whose numbers are source-verified by construction.
2. **A corpus-aggregation chart** from the patent / paper metadata the ledger *does* hold. `figure add --from-source-metadata --field year --sources … --type bar` counts filings per year; `--field assignee` counts per rights holder; `--field venue` counts papers per venue. The counts are source-verified by construction (the sources *are* the data), so a thin-web run that still retrieved a patent or paper corpus ships a **real quantitative chart**, not a timeline stand-in — this is the fix for the data-thin run that used to force a structural fallback.
3. **A structural `timeline`** (or the player-comparison table) only when neither of the above has enough points — dated events from the entity-and-date data you *do* have.

A figure pictures a claim (or several) — it introduces no new data. Record it only after the claims it visualizes are in, because its `--data` must come from those claims' sources and `check` flags any number in `data` that no cited source carries. Years (1900–2099) and one- and two-digit counts are not checked, so a `timeline` of dated events passes the provenance gate cleanly.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure add \
  --section 2.1 --type bar --title "Reported evaluation methods, 2024–2026" \
  --sources 3 7 12 --claims c2 c5 \
  --data '[{"label":"LLM-judge","value":66},{"label":"Human eval","value":18},{"label":"Benchmark suite","value":16}]'
# structural fallback when numeric market data is thin — dates + events, no percentages:
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure add \
  --section 2.1 --type timeline --title "国产大模型发布与监管里程碑" \
  --sources 5 8 14 --claims c3 c9 \
  --data '[{"date":"2023-03","event":"智谱 GLM 系列开源","group":"模型"},{"date":"2023-08","event":"首批算法备案","group":"政策"},{"date":"2024-05","event":"DeepSeek-V2 发布","group":"模型"}]'
# corpus-aggregation quantitative chart — the thin-web fallback BEFORE the timeline:
# the web came back with no market numbers, but the patent corpus is in the ledger,
# so filings-per-year / per-assignee / per-venue assemble from source metadata.
# --data and --sources are assembled for you; counts are source-verified by
# construction (the sources ARE the data), so this is a real bar, not a timeline stand-in:
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure add \
  --section 4.1 --type bar --title "国产人形机器人专利逐年申请量" \
  --sources 19 20 21 22 23 24 25 26 27 28 29 --from-source-metadata --field year
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure add \
  --section 4.1 --type hbar --title "人形机器人专利主要申请人" \
  --sources 19 20 21 22 23 24 25 26 27 28 29 --from-source-metadata --field assignee
# build a figure from captured datums — --data and --sources are assembled for you,
# and the numbers are source-verified by construction (each datum already cites its source):
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" datum add --source 3 --metric 市场份额 --value 32 --unit % --year 2024 --entity 智谱
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" datum add --source 7 --metric 市场份额 --value 24 --unit % --year 2024 --entity 百度
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure add \
  --section 2.1 --type bar --title "国产大模型厂商市场份额" --from-datums d1 d2   # ids from `datum list`
```

`--sources` are the source numbers backing the chart's data (the same numbers a text claim would cite); `--claims` are the claim ids the chart pictures, for cross-reference. `--type` is one of `bar` / `hbar` / `line` / `pie` / `heatmap` (quantitative — numbers the ledger verified) or `timeline` (structural — a list of `{date, event, group?}` dated events, the fallback when numeric market data is thin). For a shape none of those cover, pass `--code <path>` to a host-written matplotlib script instead; `chartrender.py` runs it sandboxed (no network, locked cwd, 30 s timeout, forbidden-token scan, data on stdin) and falls back to the matching template if it crashes. Either way the numbers come from the ledger, so `check`'s data↔source gate holds regardless of which path rendered it. Prefer `--from-datums d1 d2 …` over hand-typed `--data` for any figure whose numbers you captured as datums: `--data` and `--sources` are then assembled for you, and a `from_datums` figure is exempt from `figures_with_unsourced_numbers` because each datum already cites its source — the closed loop (capture at retrieval → assemble at figure time) that makes "insufficient data" a visible gap in `gaps` rather than a silent absence at wrap-up. The same closed loop holds for `--from-source-metadata`: pass the source numbers and a `--field` (`year` / `venue` / `assignee` / `kind`) and `--data` is assembled as a count along that field — `--data` and `--sources` come for free, and a `from_metadata` figure is exempt from `figures_with_unsourced_numbers` because the counts come from the ledger's own source records. This is the chart to reach for when the web returned no market numbers but the patent or paper corpus is already in the ledger — the thin-web case that used to force a timeline.

Then render the PNG with the sibling tool. `evidence.py` never spawns a process or imports matplotlib, so the chart is rendered out-of-band and recorded back:

```bash
# prints JSON: {"ok": true, "id": "f1", "path": "knowledge/figures/f1.png",
#               "rendered_by": "template", "strategy": "auto", "fallback_reason": null}
python3 "${CLAUDE_SKILL_DIR}/scripts/chartrender.py" --id f1 --out knowledge/figures/f1.png

# record the result back into the ledger (use the rendered_by the step above returned)
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" figure mark-rendered --id f1 \
  --path knowledge/figures/f1.png --by template
```

`render --final` emits a `_[FIGURE f1] …_` placeholder in the section where the figure lives, carrying the figure id, its title and its source refs. Replace that placeholder with the image embed when you assemble the report (see `references/report-format.md`). Figures are capped at 6 per report and 2 per section; `gaps` reports over-budget as a warning. Optionally open the PNG and confirm it matches the `data` — a mismatch means the script or template is wrong, not the ledger; fix and re-render before you `mark-rendered`.

### 4. Find the gap

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" gaps
```

Read the output as a work list:

**Blocking:**

- `sections_below_two_sources` → a top-level section has no evidence. Fill it or merge it into a neighbour.
- `unsupported_claims` → cite it or drop it.
- `figures_with_no_sources` → a figure's `data` cites no source (directly or via its claims). Add `--sources`, or drop the figure.
- `figures_in_unrendered_section` → the figure's `--section` is not in the outline. Re-tag it or drop it; a figure with nowhere to live cannot appear in `render`.
- `spend_over_hard_limit` → stop and hand over what you have.

**Warnings, in rough order of what they cost you:**

- `drifting_probes` → the probe returned new work, but triage threw most of it away: the query matched another field's vocabulary. Pin the concept with `all_terms` and cut the noise with `exclude_terms`. Ignoring this is how a whole subfield ends up with no evidence.
- `low_yield_probes` → that probe rephrased an earlier one. Change the axis.
- `paid_calls_without_hits` (reported by `add --aminer`, not by `gaps`) → you paid for a query the API did not understand. Shorten the term; do not record the topic as empty.
- `sections_from_single_probe` → one query fed a whole section; its blind spots are the section's blind spots. Add a distant axis.
- `claims_with_unsourced_numbers` → a figure in the claim is in none of the sources it cites. Fix the citation, or record the figure in the web source's `note` where it came from.
- `figures_unsupported_numbers` → same check, applied to a figure's `data` blob: a number in the chart appears in none of its sources. Fix the `data` or the `--sources`; like the claim version, conversions can false-trip it, so read first.
- `figures_without_render` → a figure is registered but not yet `mark-rendered`. Run `chartrender.py`, then `figure mark-rendered`, or drop it before `--final`.
- `figures_over_budget` / `sections_over_figure_budget` → more than 6 figures, or more than 2 in one section. Drop the weakest; a report clotted with charts reads as padding.
- `figure_code_divergence` → a B script's `code_path` holds literals that look like data but are not in the registered `data`. Hardcoded values defeat the data↔source gate; pull them from `data` on stdin.
- `subsections_below_two_sources` → write it thin and say so, or merge it up. Do not pad it.
- `sections_without_claims` → you retrieved for it but concluded nothing.
- `untagged_sources` → Round 0 scout hits you never placed. Tag them into a section or `drop` them.
- `cited_sources_without_detail` → a claim leans on a paper you only saw the title or a slice of. Buy the ¥0.01 detail or narrow the claim.
- `sources_without_probe` → provenance is missing, so the overlap analytics are blind.
- `single_source_claims` → find an independent source or downgrade the claim.
- `unresolved_conflicts` → resolve with a third source or report the disagreement explicitly.
- `uncited_sources` → use them or drop them.
- `web_sources` of 0 on a question about current practice → the picture is probably stale.

### 5. Decide

- A search returned nothing useful → reformulate once **on a different axis**, then move on.
- A section stays empty after two attempts → merge it into a neighbour or declare it a gap. Do not buy more searches for symmetry.
- One entity is ambiguous → show the candidates and ask the user; never buy details for every candidate.
- Stop when `gaps` shows no blocking items, or after the round budget, or when a round added nothing new.

## Wrap-up

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" check           # exit 1 means not report-ready
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --final   # the ledger view: numbering, claims-per-section, ledger source numbers — NOT the report body
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --renumber --draft <draft.md> --out <report.md>   # delivers ascending [N] from your [@n] draft + cited-only bibliography + citation-map sidecar
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --appendix --out auto --citation-map <report-citation-map.json>   # writes Appendix A, B, C and D to a file; returns the line to quote
```

`check` fails on a missing outline, an unsupported claim, a **top-level** section with fewer than two sources, an empty ledger, or spend at the hard limit. A thin **subsection** is a warning, not a failure: write it thin and say it is thin, or merge it up — do not pad it and do not write around a failing check.

Then write the report per `references/report-format.md`. `render --final` is the ledger view — take from it the section numbers, the claim set per section in order, and the stable ledger source numbers; **write the analysis as prose from those claims, citing sources as `[@n]` placeholders — do not paste the `c1` claim ids, the `_来源：` source-pool lines, the `_（分歧）_` / `_（解读）_` tags, or the raw `冲突：` bullets into the body. Those are ledger scaffolding.** The delivered report's numbers are assigned by `render --renumber` from where each placeholder first appears in your draft — never hand-type them; a `[@n]` naming an unknown or dropped source is a hard error, and the references list carries only cited sources. The appendices stay in the file `--out auto` wrote (D maps report numbers back to ledger numbers); the report ends with the reference list plus the returned `pointer` line. For an industry report, also ship at least one figure (registered + `chartrender.py` + `figure mark-rendered`) and a player-comparison table before you call it done — a Genre B report with no charts or player table is a defect, not a complete report.

## Budgets

| Item | Default |
| --- | --- |
| Top-level sections | 2–4 |
| Subsections per section | 2–4, exactly one of them the disagreement subsection |
| Round 0 scout probes | 3–4 probes × ¥0.70 `paper_qa_search_pro` (~¥2.80) |
| Rounds | 4 |
| Paid `paper_qa_search_pro` calls per round | 2 |
| ¥0.01 `paper_search_pro` calls per round | unlimited |
| Native web calls per round | 3 |
| Candidates kept per top-level section | 8 |
| Paid detail calls, whole task | 50 |
| `paper_relation` seed expansions | 5 |
| Patent probes (industry-report only) | 1–4 `patent_search` in Round 0 (≥1 mandatory), free; split by technology line, not rewording; `patent_detail` ¥0.01 shares the 50-detail budget |
| Figures | Genre A (academic): optional. Genre B (industry): ≥1 expected (market-share / player / timeline) + a player-comparison table. Cap: ≤6 per report, ≤2 per section; `bar` / `hbar` / `line` / `pie` / `heatmap` (quantitative) or `timeline` (structural, dated events) templates, or a `--code` B script; no LLM cost, rendered by `chartrender.py` |
| Cost confirmation threshold | ¥10.00 estimated |
| Hard stop, whole task | ¥20.00 accumulated (`check` blocks) |

A typical run lands near ¥4–6, and the shape of the bill matters more than the total. A measured run came to ¥6.09: **¥5.60 for eight searches, ¥0.49 for forty-nine full abstracts.** Searches are 92% of the cost, so that is the line to ration — one avoided ¥0.70 search pays for seventy abstracts. Read everything you cite; think twice before every Pro search, and check whether ¥0.01 `paper_search_pro` can express the query first.

Raise a budget only when the user asks for broader coverage or a stated requirement cannot otherwise be met, and re-estimate cost first.
