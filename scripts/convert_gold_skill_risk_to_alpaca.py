from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.skills_security_matrix.skill_structure import extract_frontmatter_and_body, parse_frontmatter


DEFAULT_INPUT_DIR = Path("outputs/gold")
DEFAULT_OUTPUT_FILE = Path("outputs/datasets/skill_has_risk_alpaca.json")
PAYLOAD_TASK = "Decide whether this skill should be marked yes or no for skill_has_risk."
VALID_LABELS = {"yes", "no"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert gold skill_has_risk annotations into a LLaMA Factory Alpaca dataset."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help=f"Directory containing gold case JSON files. Default: {DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--output",
        "--output-file",
        dest="output",
        default=str(DEFAULT_OUTPUT_FILE),
        help=f"Output Alpaca JSON file path. Default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print the output JSON with indentation. Enabled by default.",
    )
    parser.add_argument(
        "--skip-missing-description",
        action="store_true",
        help="Skip cases whose root_path/SKILL.md frontmatter description cannot be read.",
    )
    return parser


def build_skill_risk_label_instruction() -> str:
    return "\n".join(
        [
            "# Role: Skill Risk Adjudication Specialist",
            "",
            "## Profile",
            "- language: English",
            "- description: A specialist reviewer responsible for making the final binary adjudication for the `skill_has_risk` field by evaluating supplied skill description context together with retained declaration-layer and implementation-layer decisions. The role interprets upstream classification results as structured signals and decides whether any apparent mismatch reflects a meaningful least-privilege violation in context.",
            "- background: Developed for structured discrepancy review workflows in skill evaluation pipelines where upstream classification outputs provide important evidence, but final least-privilege judgment still requires contextual interpretation at the final decision stage.",
            "- personality: Precise, conservative, disciplined, evidence-bound, and highly consistent.",
            "- expertise: Least-privilege adjudication, contextual discrepancy interpretation, binary decision logic, evidence-constrained JSON output.",
            "- target_audience: Automated review pipelines, model evaluators, repository discrepancy assessment systems, and quality assurance teams requiring standardized `skill_has_risk` judgments.",
            "",
            "## Skills",
            "",
            "1. Core Adjudication Skills",
            "   - Final-Decision Evaluation: Determine whether any implementation-only capability is materially broader than what a reasonable reader would understand from the declared skill purpose.",
            "   - Evidence-Grounded Risk Judgment: Base the final `yes` or `no` decision on the supplied description plus retained declaration and implementation decisions, interpreting mismatches in context rather than by mechanical set comparison.",
            "   - Conservative Binary Classification: Resolve ambiguous evidence cautiously and prefer rule-based fallback behavior when signals are weak.",
            "   - Schema-Strict Output Generation: Produce the final answer as a JSON object containing only `skill_has_risk`.",
            "",
            "2. Supporting Review Skills",
            "   - Upstream Signal Interpretation: Respect upstream category decisions as structured evidence while evaluating whether any apparent mismatch is materially meaningful in context.",
            "   - Signal Prioritization: Compare retained implementation-layer decisions against retained declaration-layer decisions to identify apparent scope expansion for contextual review.",
            "   - Context Integration: Use the skill description and declared purpose to assess whether implementation-only capability is reasonably implied, necessary, incidental, or genuinely excessive.",
            "   - Constraint Adherence: Avoid external knowledge, repository assumptions, speculative inference, and unsupported extrapolation.",
            "",
            "## Rules",
            "",
            "1. Basic Principles:",
            "   - Evidence Scope: Use only the supplied skill description, retained declaration-layer decisions, and retained implementation-layer decisions as decision inputs.",
            "   - Upstream Decisions as Signals: Treat regex-derived declaration and implementation category decisions as structured signals, not as mechanically binding final judgments.",
            "   - Contextual Risk Standard: Mark `skill_has_risk` as `yes` only when the implementation shows materially broader, independent, or unnecessary capability beyond what is reasonably declared or implied by the skill purpose.",
            "   - No Mechanical Superset Rule: Do not mark `yes` solely because implementation categories are a strict superset of declaration categories. Use that mismatch as a trigger for contextual review.",
            "   - Reasonable-Use Allowance: If an implementation capability is a normal, necessary, or clearly implied part of fulfilling the declared skill purpose, do not treat it as risky merely because declaration regexes did not capture it.",
            "   - Materiality Requirement: Focus on meaningful privilege expansion. Minor helper behavior, formatting, validation, parsing, logging, or internal processing should not trigger risk unless it grants a distinct capability beyond the skill's declared purpose.",
            "   - Non-Risk Standard: Do not mark `yes` merely because a retained category appears operationally dangerous, sensitive, or high impact. The issue is whether implementation materially exceeds the reasonably declared skill scope.",
            "   - Conservative Resolution: If the mismatch appears caused by regex imprecision, category granularity, or ambiguity, default to `no` unless there is clear evidence of meaningful scope expansion.",
            "",
            "2. Behavioral Guidelines:",
            "   - Do Not Reclassify: Never change, replace, refine, merge, split, or invent categories beyond those already supplied.",
            "   - Do Not Mechanize Upstream Decisions: Do not casually discard upstream category decisions, but you may interpret their relevance, materiality, and relationship to the stated skill purpose when making the final risk judgment.",
            "   - Do Not Invent Categories from Description: Use description to evaluate mismatch materiality, not to add, remove, or rewrite retained categories.",
            "   - Remain Brief and Determinate: Return only the required label object without explanation, hedging, or narrative.",
            "   - It is allowed for the declared permissions to exceed the implementation, and the value of `skill_has_risk` is `no`.",
            "",
            "3. Constraints:",
            "   - No External Knowledge: Do not rely on domain knowledge, common repository patterns, or any unstated implementation behavior.",
            "   - No Speculation: Do not infer hidden capabilities, undocumented intent, unstated consequences, or undeclared scope expansion from incomplete evidence.",
            "   - No Description Reclassification: Never use description to add, remove, or rewrite retained declaration or implementation categories. However, description may be used to judge whether an implementation-only category is reasonably implied, necessary, incidental, or materially excessive.",
            "   - No Format Deviation: Return only the JSON object that matches the required schema exactly, with no markdown, labels, commentary, or additional keys.",
            "   - Fixed Output Values: `skill_has_risk` must be exactly `yes` or `no`.",
            "",
            "## Workflows",
            "",
            "- Goal: Determine whether the final field `skill_has_risk` should be `yes` or `no` using the supplied description context and retained layered decisions.",
            "- Step 1: Read the provided description to understand the stated skill purpose and workflow; do not derive new categories from it.",
            "- Step 2: Read the provided declaration and implementation decisions as structured evidence without changing the supplied classifications.",
            "- Step 3: Compare declaration-layer and implementation-layer decisions to identify any apparent implementation-only mismatches.",
            "- Step 4: For each apparent implementation-only category, assess whether it is reasonably implied by the declared purpose, necessary to execute the workflow, merely incidental helper behavior, likely caused by regex overmatching or category granularity, or a materially broader independent capability.",
            "- Step 5: Set `skill_has_risk` to `yes` only when at least one implementation-only capability is materially broader and not reasonably implied, necessary, or incidental.",
            "- Step 6: Set `skill_has_risk` to `no` when the mismatch is explainable as reasonable implementation detail, regex imprecision, non-material helper behavior, or when declaration already covers the broader scope.",
            "- Expected Result: Output a single JSON object with only `skill_has_risk` set to `yes` or `no`.",
            "",
            "## Initialization",
            "As Skill Risk Adjudication Specialist, you must follow the above Rules and execute the task according to the Workflows.",
        ]
    )


ALPACA_INSTRUCTION = build_skill_risk_label_instruction()


def extract_description_from_root(root_path: Path) -> str:
    skill_md = root_path / "SKILL.md"
    if not skill_md.exists():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    frontmatter, _body = extract_frontmatter_and_body(text)
    if not frontmatter:
        return ""
    return parse_frontmatter(frontmatter).get("description", "").strip()


def build_skill_risk_input_payload(case_data: dict[str, Any], description: str) -> dict[str, Any]:
    final_decisions = case_data["final_decisions"]
    retained_decisions = [item for item in final_decisions if item.get("decision_status") != "rejected_by_llm"]
    return {
        "task": PAYLOAD_TASK,
        "skill_id": case_data["skill_id"],
        "description": description,
        "decision_policy": {
            "allowed_statuses": ["yes", "no"],
            "description_role": (
                "Use the description together with retained declaration and implementation decisions to judge "
                "whether any apparent mismatch is reasonably implied, necessary, incidental, or materially broader "
                "in context."
            ),
            "focus": (
                "Treat retained declaration and implementation decisions as structured signals for contextual "
                "least-privilege review, not as mechanically binding set-membership rules."
            ),
            "forbidden_actions": [
                "changing category decisions",
                "inventing categories",
                "deriving retained categories from description alone",
                "using evidence not present in the payload",
            ],
        },
        "declaration_decisions": [
            decision_payload(item) for item in retained_decisions if item.get("layer") == "declaration"
        ],
        "implementation_decisions": [
            decision_payload(item) for item in retained_decisions if item.get("layer") == "implementation"
        ],
    }


def decision_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_id": item.get("category_id", ""),
        "category_name": item.get("category_name", ""),
        "decision_status": item.get("decision_status", ""),
        "confidence": item.get("confidence", ""),
        "confidence_score": item.get("confidence_score", 0.0),
    }


def validate_case(path: Path, case_data: dict[str, Any]) -> None:
    if not case_data.get("skill_id"):
        raise ValueError(f"{path}: missing required skill_id")
    if case_data.get("skill_has_risk") not in VALID_LABELS:
        raise ValueError(f"{path}: skill_has_risk must be one of {sorted(VALID_LABELS)}")
    if not isinstance(case_data.get("final_decisions"), list):
        raise ValueError(f"{path}: missing required final_decisions array")


def convert_case_to_alpaca(case_data: dict[str, Any], description: str) -> dict[str, str]:
    payload = build_skill_risk_input_payload(case_data, description)
    output = {"skill_has_risk": case_data["skill_has_risk"]}
    return {
        "instruction": ALPACA_INSTRUCTION,
        "input": json.dumps(payload, ensure_ascii=False),
        "output": json.dumps(output, ensure_ascii=False, separators=(",", ":")),
    }


def convert_gold_directory(
    input_dir: Path,
    *,
    skip_missing_description: bool = False,
) -> tuple[list[dict[str, str]], Counter[str], list[str]]:
    records: list[dict[str, str]] = []
    stats: Counter[str] = Counter()
    warnings: list[str] = []

    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No gold JSON files found in {input_dir}")

    for path in paths:
        case_data = json.loads(path.read_text(encoding="utf-8"))
        validate_case(path, case_data)

        root_path = Path(case_data.get("root_path", ""))
        description = extract_description_from_root(root_path)
        if not description:
            stats["missing_description"] += 1
            warning = f"{path.name}: missing description from {root_path / 'SKILL.md'}"
            warnings.append(warning)
            if skip_missing_description:
                stats["skipped_missing_description"] += 1
                continue

        record = convert_case_to_alpaca(case_data, description)
        records.append(record)
        stats[f"label_{case_data['skill_has_risk']}"] += 1

    stats["exported"] = len(records)
    return records, stats, warnings


def main() -> int:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_file = Path(args.output).expanduser().resolve()

    records, stats, warnings = convert_gold_directory(
        input_dir,
        skip_missing_description=args.skip_missing_description,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
    )

    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    print(f"Output written to: {output_file}")
    print(f"Total samples: {stats['exported']}")
    print(f"Label counts: yes={stats['label_yes']}, no={stats['label_no']}")
    print(f"Missing descriptions: {stats['missing_description']}")
    if args.skip_missing_description:
        print(f"Skipped missing descriptions: {stats['skipped_missing_description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
