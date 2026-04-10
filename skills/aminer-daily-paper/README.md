# aminer-daily-paper

Personalized academic paper recommendation via the AMiner rec5 API. Works as an OpenClaw skill, dispatching results as Feishu interactive cards or returning Markdown text when no Feishu target is available.

## Requirements

- Python 3.10+
- `AMINER_API_KEY` environment variable — obtain at https://open.aminer.cn/open/board?tab=control

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```
/aminer-dp
/aminer-dp topics: multimodal agents, tool-use
/aminer-dp scholar: Jie Tang org: Tsinghua
/aminer-dp aminer_user_id: 696259801cb939bc391d3a37 topics: RAG, LLM
recommend me recent papers on multimodal agents
```

The model (running the skill) extracts `topics`, `author_name`, `author_org`, or `aminer_user_id` from natural language input before calling the script.

## How It Works

1. `handle_trigger.py` parses the trigger text and infers the Feishu delivery route.
2. `run_pipeline.py` calls the AMiner rec5 API with the extracted parameters.
3. If a Feishu target is available, paper cards are dispatched via `openclaw message send`. Otherwise, results are returned as Markdown text.

## API

```
POST https://datacenter.aminer.cn/gateway/open_platform/api/v3/paper/rec5
Authorization: <AMINER_API_KEY>
```

Key request fields: `aminer_author_id`, `author_name`, `author_org`, `topics`, `size`.  
At least one of `aminer_author_id`, `author_name`, or `topics` is required.
