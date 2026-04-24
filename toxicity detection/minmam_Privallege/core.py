from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


ATOM_FAMILY_MAX = {
    "R": 10,
    "Q": 4,
    "S": 7,
    "W": 4,
    "U": 4,
    "C": 5,
    "X": 8,
    "G": 5,
    "O": 5,
    "K": 6,
    "A": 7,
    "I": 7,
}

TOKEN_RE = re.compile(r"\b([A-Z])(\d+)\b")
RANGE_RE = re.compile(r"\b([A-Z])(\d+)\s*-\s*(?:([A-Z]))?(\d+)\b")
PLUS_RE = re.compile(r"\b([A-Z])(\d+)\+\b")


@dataclass
class PermissionSetSpec:
    raw: str = ""
    atoms: List[str] = field(default_factory=list)


@dataclass
class PermissionCombinationSpec:
    raw: str = ""
    all_of: List[str] = field(default_factory=list)
    one_of: List[List[str]] = field(default_factory=list)


@dataclass
class AtomConstraintSpec:
    raw: str = ""
    atoms: List[str] = field(default_factory=list)


@dataclass
class DomainRule:
    id: str
    name: str
    examples: List[str]
    max_tier_whitelist: str
    minimum_permission_set: PermissionSetSpec
    minimum_permission_combinations: PermissionCombinationSpec
    forbidden_atoms: AtomConstraintSpec
    out_of_scope_atoms: AtomConstraintSpec


# ---------- basic utils ----------

def normalize_text(text: str) -> str:
    return (
        text.replace("<br/>", " ")
        .replace("<br>", " ")
        .replace("，", ",")
        .replace("、", ",")
        .replace("；", ";")
        .replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
        .strip()
    )


def split_examples(text: str) -> List[str]:
    parts = re.split(r"[、,，]\s*", normalize_text(text))
    return [part for part in parts if part]


def dedupe_keep_order(items: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def sort_atoms(atoms: List[str]) -> List[str]:
    def atom_key(atom: str) -> tuple[str, int]:
        m = re.fullmatch(r"([A-Z])(\d+)", atom)
        if not m:
            return ("~", 9999)
        return (m.group(1), int(m.group(2)))

    return sorted(dedupe_keep_order(atoms), key=atom_key)


def extract_atom_tokens(text: str) -> List[str]:
    return dedupe_keep_order([f"{prefix}{index}" for prefix, index in TOKEN_RE.findall(text)])


def unwrap_parentheses(text: str) -> str:
    value = text.strip()
    if value.startswith("(") and value.endswith(")"):
        return value[1:-1].strip()
    return value


def split_top_level_plus(expr: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    buffer: List[str] = []
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)

        if ch == "+" and depth == 0:
            part = "".join(buffer).strip()
            if part:
                parts.append(part)
            buffer = []
            continue
        buffer.append(ch)

    tail = "".join(buffer).strip()
    if tail:
        parts.append(tail)
    return parts


# ---------- parsing ----------

def parse_permission_set(text: str) -> PermissionSetSpec:
    raw = text.strip()
    normalized = normalize_text(text)
    atoms = extract_atom_tokens(normalized)
    return PermissionSetSpec(raw=raw, atoms=sort_atoms(atoms))


def parse_permission_combination(expr: str) -> PermissionCombinationSpec:
    raw = expr.strip()
    normalized = normalize_text(expr)
    parts = split_top_level_plus(normalized)

    spec = PermissionCombinationSpec(raw=raw)
    for part in parts:
        item = part.strip()
        if not item:
            continue

        candidate = unwrap_parentheses(item)
        if any(keyword in candidate for keyword in ["或", "其一", "/"]):
            options = extract_atom_tokens(candidate)
            if options:
                spec.one_of.append(sort_atoms(options))
                continue

        atoms = extract_atom_tokens(candidate)
        if atoms:
            spec.all_of.extend(atoms)

    spec.all_of = sort_atoms(spec.all_of)
    spec.one_of = [sort_atoms(group) for group in spec.one_of]
    return spec


def expand_atom_specs(text: str) -> List[str]:
    normalized = normalize_text(text)
    found: List[str] = []
    occupied_spans: List[tuple[int, int]] = []

    for match in RANGE_RE.finditer(normalized):
        prefix1, start, prefix2, end = match.groups()
        prefix2 = prefix2 or prefix1
        if prefix1 != prefix2:
            continue
        start_i, end_i = int(start), int(end)
        step = 1 if end_i >= start_i else -1
        found.extend([f"{prefix1}{i}" for i in range(start_i, end_i + step, step)])
        occupied_spans.append(match.span())

    for match in PLUS_RE.finditer(normalized):
        prefix, start = match.groups()
        max_index = ATOM_FAMILY_MAX.get(prefix)
        if not max_index:
            continue
        start_i = int(start)
        found.extend([f"{prefix}{i}" for i in range(start_i, max_index + 1)])
        occupied_spans.append(match.span())

    chars = list(normalized)
    for start, end in occupied_spans:
        for idx in range(start, end):
            chars[idx] = " "
    remaining = "".join(chars)

    found.extend(extract_atom_tokens(remaining))
    return sort_atoms(found)


def parse_atom_constraint(text: str) -> AtomConstraintSpec:
    raw = text.strip()
    atoms = expand_atom_specs(text)
    return AtomConstraintSpec(raw=raw, atoms=atoms)


# ---------- markdown <-> yaml ----------

def parse_markdown_table(markdown: str) -> List[Dict[str, str]]:
    lines = [line.rstrip() for line in markdown.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|")]
    if len(table_lines) < 3:
        raise ValueError("Markdown 中未找到有效表格。")

    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: List[Dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def _pick(row: Dict[str, str], *candidates: str) -> str:
    for key in candidates:
        if key in row:
            return row[key]
    raise KeyError(f"缺少字段，候选列名: {candidates}")


def build_domains_from_markdown(markdown_path: str | Path) -> List[DomainRule]:
    markdown = Path(markdown_path).read_text(encoding="utf-8")
    rows = parse_markdown_table(markdown)
    domains: List[DomainRule] = []

    for row in rows:
        domain = DomainRule(
            id=_pick(row, "功能域编号"),
            name=_pick(row, "功能域 (Domain)", "能域 (Domain)", "Domain", "功能域"),
            examples=split_examples(_pick(row, "典型示例")),
            max_tier_whitelist=_pick(row, "允许的最高 Tier (白名单)"),
            minimum_permission_set=parse_permission_set(_pick(row, "最小权限集", "最小权限（原子操作）")),
            minimum_permission_combinations=parse_permission_combination(_pick(row, "最小权限组合", "最小权限（原子操作）")),
            forbidden_atoms=parse_atom_constraint(_pick(row, "明确禁止的原子")),
            out_of_scope_atoms=parse_atom_constraint(_pick(row, "一旦出现就越界的原子")),
        )
        domains.append(domain)

    return domains


def dump_domains_to_yaml(domains: List[DomainRule], yaml_path: str | Path) -> None:
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，无法导出 YAML 文件。")

    payload = {
        "version": 4,
        "atom_family_max": ATOM_FAMILY_MAX,
        "domains": [
            {
                "id": domain.id,
                "name": domain.name,
                "examples": domain.examples,
                "max_tier_whitelist": domain.max_tier_whitelist,
                "minimum_permission_set": asdict(domain.minimum_permission_set),
                "minimum_permission_combinations": asdict(domain.minimum_permission_combinations),
                "forbidden_atoms": asdict(domain.forbidden_atoms),
                "out_of_scope_atoms": asdict(domain.out_of_scope_atoms),
            }
            for domain in domains
        ],
    }

    Path(yaml_path).write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_domains_from_yaml(yaml_path: str | Path) -> List[DomainRule]:
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，无法读取 YAML 文件。")

    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    domains: List[DomainRule] = []
    for item in data.get("domains", []):
        domains.append(
            DomainRule(
                id=item["id"],
                name=item["name"],
                examples=item.get("examples", []),
                max_tier_whitelist=item.get("max_tier_whitelist", ""),
                minimum_permission_set=PermissionSetSpec(**item.get("minimum_permission_set", {})),
                minimum_permission_combinations=PermissionCombinationSpec(
                    **item.get("minimum_permission_combinations", {})
                ),
                forbidden_atoms=AtomConstraintSpec(**item.get("forbidden_atoms", {})),
                out_of_scope_atoms=AtomConstraintSpec(**item.get("out_of_scope_atoms", {})),
            )
        )
    return domains
