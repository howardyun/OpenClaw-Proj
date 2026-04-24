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
from analyzer.skills_security_matrix.review.providers.prompting import build_skill_risk_system_prompt


DEFAULT_INPUT_DIR = Path("outputs/gold")
DEFAULT_OUTPUT_FILE = Path("outputs/datasets/skill_has_risk_alpaca.json")
ALPACA_INSTRUCTION = build_skill_risk_system_prompt()
PAYLOAD_TASK = "Decide whether this skill should be marked yes or no for skill_has_risk."
SKIP_INVALID_JSON = "invalid_json"
SKIP_INVALID_LABEL = "invalid_skill_has_risk"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert outputs/gold skill_has_risk annotations into a LLaMA-Factory Alpaca dataset."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing gold case JSON files.",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Output Alpaca JSON file path.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the output JSON with indentation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for debugging.",
    )
    return parser


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


def build_skill_risk_input_payload(case_data: dict[str, Any]) -> dict[str, Any]:
    retained_decisions = [
        item for item in case_data.get("final_decisions", []) if item.get("decision_status") != "rejected_by_llm"
    ]
    return {
        "task": PAYLOAD_TASK,
        "skill_id": case_data.get("skill_id", ""),
        "description": extract_description_from_root(Path(case_data.get("root_path", ""))),
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
            _decision_item(item) for item in retained_decisions if item.get("layer") == "declaration"
        ],
        "implementation_decisions": [
            _decision_item(item) for item in retained_decisions if item.get("layer") == "implementation"
        ],
    }


def _decision_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_id": item.get("category_id", ""),
        "category_name": item.get("category_name", ""),
        "decision_status": item.get("decision_status", ""),
        "confidence": item.get("confidence", ""),
        "confidence_score": item.get("confidence_score", 0.0),
    }


def convert_case_to_alpaca(case_data: dict[str, Any]) -> dict[str, str] | None:
    label = case_data.get("skill_has_risk")
    if label not in {"yes", "no"}:
        return None
    payload = build_skill_risk_input_payload(case_data)
    return {
        "instruction": ALPACA_INSTRUCTION,
        "input": json.dumps(payload, ensure_ascii=False),
        "output": str(label),
    }


def convert_gold_directory(input_dir: Path, *, limit: int | None = None) -> tuple[list[dict[str, str]], Counter[str]]:
    records: list[dict[str, str]] = []
    stats: Counter[str] = Counter()
    paths = sorted(input_dir.glob("*.json"))
    if limit is not None:
        paths = paths[:limit]

    for path in paths:
        try:
            case_data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            stats[SKIP_INVALID_JSON] += 1
            continue

        alpaca_record = convert_case_to_alpaca(case_data)
        if alpaca_record is None:
            stats[SKIP_INVALID_LABEL] += 1
            continue

        records.append(alpaca_record)
        stats[f"label_{alpaca_record['output']}"] += 1

    stats["exported"] = len(records)
    return records, stats


def main() -> int:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_file = Path(args.output_file).expanduser().resolve()
    records, stats = convert_gold_directory(input_dir, limit=args.limit)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
    )

    print(f"Output written to: {output_file}")
    print(f"Exported samples: {stats['exported']}")
    print(f"Label counts: yes={stats['label_yes']}, no={stats['label_no']}")
    print(f"Skipped invalid JSON: {stats[SKIP_INVALID_JSON]}")
    print(f"Skipped invalid skill_has_risk: {stats[SKIP_INVALID_LABEL]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
