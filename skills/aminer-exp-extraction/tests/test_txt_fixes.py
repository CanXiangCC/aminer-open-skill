"""TODO-TXT-01 / TODO-TXT-02: name-field citation-marker stripping + wrapped-title join.

TXT-01: LLM-extracted name-class fields (experiment_name, methods[].name/aliases,
datasets[].name/aliases, research_problem(_aliases)) may carry paper citation
markers ("Checkpoint Merging [113]"). The markers are noise in labels and are
stripped there only — description / key_results prose keeps its citation style.

TXT-02: paper titles wrapped across several markdown lines were truncated at the
first line (``extract_paper_title`` H1 regex does not match newlines). The fix
joins continuation lines back, re-glues hyphen breaks, and keeps a sanity
fallback to the first line when the join looks like body text.
"""

from pipeline.benchmark.workflows.wf1_merged import extract_paper_title
from pipeline.production.adapters.wf4_normalize import (
    coerce_wf4_llm_parsed,
    normalize_llm_datasets,
    normalize_methods,
    strip_citation_markers,
    strip_citation_markers_list,
)


# ---------------------------------------------------------------- TXT-01 ----

class TestStripCitationMarkers:
    def test_examples_from_todo(self):
        assert strip_citation_markers("Checkpoint Merging [113]") == "Checkpoint Merging"
        assert strip_citation_markers("Fusion [23]") == "Fusion"

    def test_marker_shapes(self):
        # plain, list, range, en-dash range, multiple markers
        assert strip_citation_markers("A [1]") == "A"
        assert strip_citation_markers("A [1,2]") == "A"
        assert strip_citation_markers("A [1-3]") == "A"
        assert strip_citation_markers("A [1\u20133]") == "A"
        assert strip_citation_markers("A [1] [2]") == "A"
        assert strip_citation_markers("Mid [7] Word") == "Mid Word"

    def test_no_marker_untouched_and_empty(self):
        assert strip_citation_markers("LoRA") == "LoRA"
        assert strip_citation_markers("") == ""
        # non-digit brackets are NOT citation markers — keep them
        assert strip_citation_markers("BERT [base]") == "BERT [base]"

    def test_marker_only_name_empties(self):
        assert strip_citation_markers("[42]") == ""
        assert strip_citation_markers_list(["A [9]", "[7]", "B"]) == ["A", "B"]


class TestCoerceStripsNameFields:
    def _coerce(self, parsed):
        return coerce_wf4_llm_parsed(parsed)

    def test_experiment_name_and_research_problem(self):
        out = self._coerce(
            {
                "research_problem": "Study fusion [3]",
                "research_problem_aliases": ["Model merging [9]", "Fusion"],
                "experiments": [
                    {"experiment_name": "Checkpoint Merging [113]"},
                    {"experiment_name": "Fusion [23]"},
                ],
            }
        )
        assert out["research_problem"] == "Study fusion"
        assert out["research_problem_aliases"] == ["Model merging", "Fusion"]
        names = [e["experiment_name"] for e in out["experiments"]]
        assert names == ["Checkpoint Merging", "Fusion"]

    def test_methods_object_and_alias_paths(self):
        out = self._coerce(
            {
                "experiments": [
                    {
                        "experiment_name": "Ablation [4]",
                        "methods": [
                            {
                                "name": "LoRA [12]",
                                "description": "Uses adapters described in [12].",
                                "aliases": ["IA\u00b3 [7]", "[5]"],
                            }
                        ],
                    }
                ]
            }
        )
        m = out["experiments"][0]["methods"][0]
        assert m["name"] == "LoRA"
        assert m["aliases"] == ["IA\u00b3"]  # marker-only alias dropped
        # prose citation style untouched
        assert m["description"] == "Uses adapters described in [12]."

    def test_methods_string_list_and_legacy_paths(self):
        out = self._coerce(
            {"experiments": [{"experiment_name": "E", "methods": ["Attention [1]", "MoE [2,3]"]}]}
        )
        names = [m["name"] for m in out["experiments"][0]["methods"]]
        assert names == ["Attention", "MoE"]
        legacy = normalize_methods(None, legacy_method="Adapters [8]")
        assert [m["name"] for m in legacy] == ["Adapters"]

    def test_datasets_name_and_aliases(self):
        ds = normalize_llm_datasets(
            [
                {"name": "SQuAD [5]", "aliases": ["Stanford QA [6]"]},
                {"name": "[42]"},  # marker-only → dropped
            ]
        )
        assert [d["name"] for d in ds] == ["SQuAD"]
        assert ds[0]["aliases"] == ["Stanford QA"]

    def test_prose_fields_keep_citation_style(self):
        out = self._coerce(
            {
                "research_problem": "P",
                "research_problem_description": "Prior work [1] showed gains. See [2].",
                "experiments": [
                    {
                        "experiment_name": "E [3]",
                        "key_results": ["Gains reported in [4]."],
                        "research_goal": "Goal follows [5].",
                        "metrics": ["Accuracy [6]"],
                    }
                ],
            }
        )
        assert out["research_problem_description"] == "Prior work [1] showed gains. See [2]."
        e = out["experiments"][0]
        assert e["experiment_name"] == "E"
        assert e["key_results"] == ["Gains reported in [4]."]
        assert e["research_goal"] == "Goal follows [5]."
        assert e["metrics"] == ["Accuracy [6]"]

    def test_clean_names_byte_identical(self):
        parsed = {
            "research_problem": "Clean problem",
            "research_problem_aliases": ["alias-a"],
            "experiments": [
                {
                    "experiment_name": "Clean experiment",
                    "key_results": ["r1"],
                    "methods": [{"name": "Clean method", "description": "d", "aliases": ["m1"]}],
                    "research_goal": "g",
                    "experiment_subject": ["s"],
                    "metrics": ["m"],
                    "datasets": [{"name": "CleanDS", "aliases": ["cd"]}],
                }
            ],
        }
        out = self._coerce(parsed)
        e = out["experiments"][0]
        assert e["experiment_name"] == "Clean experiment"
        assert e["methods"][0]["name"] == "Clean method"
        assert e["methods"][0]["aliases"] == ["m1"]
        assert e["datasets"][0]["name"] == "CleanDS"
        assert e["datasets"][0]["aliases"] == ["cd"]


# ---------------------------------------------------------------- TXT-02 ----

class TestExtractPaperTitle:
    def test_todo_example_hyphen_break(self):
        md = (
            "# LLMs Know More Than They Show: On the IN-\n"
            "context Reasoning of LLMs\n"
            "\n"
            "Alice Smith, Bob Jones\n"
        )
        assert extract_paper_title(md) == (
            "LLMs Know More Than They Show: On the IN-context Reasoning of LLMs"
        )

    def test_plain_wrap_no_hyphen(self):
        md = "# A Very Long Title That\nWraps At The Margin\n\nAuthors Here\n"
        assert extract_paper_title(md) == "A Very Long Title That Wraps At The Margin"

    def test_stops_at_blank_line_and_block_structure(self):
        # blank line ends the title block
        assert extract_paper_title("# Title\n\nAuthor Line\n") == "Title"
        # list / heading / table / image lines are not title continuation
        assert extract_paper_title("# Title\n- not part\n") == "Title"
        assert extract_paper_title("# Title\n## Sub\n") == "Title"
        assert extract_paper_title("# Title\n| a | b |\n") == "Title"
        assert extract_paper_title("# Title\n![fig](x.png)\n") == "Title"

    def test_single_line_title_unchanged(self):
        assert extract_paper_title("# Plain Title\n\nbody text\n") == "Plain Title"
        assert extract_paper_title("no heading at all\n") == ""

    def test_sanity_fallback_on_body_swallow(self):
        # a huge run-on right after the H1 (no blank line) must not become the title
        md = "# Title\n" + ("word " * 200).strip() + "\n"
        assert extract_paper_title(md) == "Title"

    def test_math_and_latex_still_stripped_across_join(self):
        md = "# Title With $x^2$ Math\nand \\\\emph{LaTeX} Tail\n\nnext\n"
        title = extract_paper_title(md)
        assert "$" not in title
        assert "Title With" in title and "Math" in title
        assert "Tail" in title
