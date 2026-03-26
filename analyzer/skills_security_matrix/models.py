from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MatrixCategory:
    category_id: str
    major_category: str
    subcategory: str
    security_definition: str
    data_level: str
    primary_risks: list[str]
    control_requirements: list[str]


@dataclass(slots=True)
class SkillStructureProfile:
    has_skill_md: bool
    has_frontmatter: bool
    has_references_dir: bool
    has_scripts_dir: bool
    has_assets_dir: bool
    has_templates_dir: bool
    top_level_files: list[str] = field(default_factory=list)
    top_level_dirs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillArtifact:
    skill_id: str
    root_path: Path
    structure: SkillStructureProfile
    file_paths: list[Path]
    source_files: list[Path]


@dataclass(slots=True)
class EvidenceItem:
    category_id: str
    category_name: str
    source_path: str
    layer: str
    evidence_type: str
    matched_text: str
    line_start: int | None
    line_end: int | None
    confidence: str
    rule_id: str
    source_kind: str | None = None
    support_reference_mode: str | None = None


@dataclass(slots=True)
class CategoryClassification:
    category_id: str
    category_name: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: str = "unknown"


@dataclass(slots=True)
class CategoryDiscrepancy:
    category_id: str
    category_name: str
    status: str
    declaration_present: bool
    implementation_present: bool
    risks: list[str]
    controls: list[str]


@dataclass(slots=True)
class AnalysisResult:
    skill_id: str
    root_path: str
    structure_profile: SkillStructureProfile
    declaration_classifications: list[CategoryClassification] = field(default_factory=list)
    implementation_classifications: list[CategoryClassification] = field(default_factory=list)
    skill_level_discrepancy: str = "insufficient_implementation_evidence"
    category_discrepancies: list[CategoryDiscrepancy] = field(default_factory=list)
    risk_mappings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunConfig:
    skills_dir: str
    output_dir: str
    requested_formats: list[str]
    limit: int | None
    case_study_skill: str | None
    include_hidden: bool
    fail_on_unknown_matrix: bool


@dataclass(slots=True)
class RunSummary:
    run_id: str
    output_dir: str
    analyzed_skills: int
    skipped_skills: int
    errored_skills: int
    config: RunConfig
    skill_errors: list[dict[str, str]] = field(default_factory=list)


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return value
