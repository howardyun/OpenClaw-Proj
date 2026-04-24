from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Set, Tuple

import pandas as pd


CONFIG: Dict[str, Any] = {
    # ===== 输入输出 =====
    "input_csv": "/mnt/data/skills_with_minimum_permission_set.csv",
    "out_dir": "/mnt/data/pdei_final_outputs",
    "output_prefix": "pdei",

    # ===== PDEI 参数 =====
    "top_n": 100,
    "phi_mode": "set",          # "set" 更严谨；"count" 严格复现 md 原型
    "alpha": 2.0,

    # ===== 使用哪一列作为申领权限 =====
    # 可选: "declaration" / "implementation" / "union"
    "requested_atoms_mode": "declaration",

    # ===== 当前 CSV 的真实列名（不改 CSV，只在脚本里适配） =====
    "columns": {
        "skill_name": "name",
        "domain": "domain",
        "source_plat": "source_plat",  # 可选列
        "requested_declaration": "declaration_atomic_ids",
        "requested_implementation": "implementation_atomic_ids",
        "necessary_atoms": "minimum_permission_set",
        "skill_download_count": "skill_download_count",
        "skill_star_count": "skill_star_count",
        "skill_fork_count": "skill_fork_count",
        "developer_github_stars": "developer_github_stars",
        "developer_is_org": "developer_is_org",
    },
}


T1_BASELINE: Set[str] = {"R1", "R2", "Q1"}
T2_BASELINE: Set[str] = {"W1", "W2"}
T3_BASELINE: Set[str] = {"G1", "G2"}
T4_BASELINE: Set[str] = {"A1", "A2"}

BASELINES: Dict[int, Set[str]] = {
    1: T1_BASELINE,
    2: T2_BASELINE,
    3: T3_BASELINE,
    4: T4_BASELINE,
}

TIER_MAP: Dict[int, Set[str]] = {
    1: {
        "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
        "Q1", "Q2", "Q3", "Q4",
        "S1", "S2", "S3", "S4", "S5", "S6", "S7",
    },
    2: {
        "W1", "W2", "W3", "W4",
        "U1", "U2", "U3", "U4",
        "C1", "C2", "C3", "C4", "C5",
    },
    3: {
        "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8",
        "G1", "G2", "G3", "G4", "G5",
        "O1", "O2", "O3", "O4", "O5",
        "K1", "K2", "K3", "K4", "K5", "K6",
    },
    4: {
        "A1", "A2", "A3", "A4", "A5", "A6", "A7",
        "I1", "I2", "I3", "I4", "I5", "I6", "I7",
    },
}

WEIGHTS: Dict[int, float] = {
    1: 1.0,
    2: 2.0,
    3: 2.5,
    4: 4.0,
}

BETA: Dict[str, float] = {
    "A": 5.0,
    "B": 3.0,
    "C": 4.0,
    "D": 7.0,
    "E": 6.0,
}

ALL_ATOMS: Set[str] = set().union(*TIER_MAP.values())
_SPLIT_PATTERN = re.compile(r"[;,|，\s]+")


@dataclass(frozen=True)
class ReachResult:
    value: float
    n_eff: int
    lambda_dev: float


@dataclass(frozen=True)
class PhiResult:
    value: float
    deltas: Dict[int, int]
    extra_atoms: Dict[int, Set[str]]
    unknown_requested_atoms: Set[str]
    unknown_necessary_atoms: Set[str]


@dataclass(frozen=True)
class GammaResult:
    value: float
    paths: Dict[str, int]


def parse_atom_set(value: Any) -> Set[str]:
    """
    支持:
    - 'R1,R2,Q1'
    - '["R1", "R2", "Q1"]'
    - Python list / set
    """
    if value is None:
        return set()

    if isinstance(value, set):
        items = value
    elif isinstance(value, (list, tuple)):
        items = set(value)
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return set()

        # 先尝试按 JSON / Python 字面量解析
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    items = set(parsed)
                    return {str(item).strip().upper() for item in items if str(item).strip()}
            except Exception:
                pass

        items = {token for token in _SPLIT_PATTERN.split(text) if token}

    return {str(item).strip().upper() for item in items if str(item).strip()}


def stringify_atom_set(atoms: Set[str]) -> str:
    return ",".join(sorted(atoms)) if atoms else ""


def normalize_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return default
    try:
        return int(float(text))
    except Exception:
        return default


def normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f"}:
        return False
    return default


def load_input_csv(csv_path: str | Path) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def validate_input_columns(df: pd.DataFrame, config: Mapping[str, Any]) -> None:
    cols = config["columns"]
    required = [
        cols["skill_name"],
        cols["domain"],
        cols["necessary_atoms"],
        cols["skill_download_count"],
        cols["skill_star_count"],
        cols["skill_fork_count"],
        cols["developer_github_stars"],
        cols["developer_is_org"],
    ]

    mode = str(config["requested_atoms_mode"]).strip().lower()
    if mode == "declaration":
        required.append(cols["requested_declaration"])
    elif mode == "implementation":
        required.append(cols["requested_implementation"])
    elif mode == "union":
        required.extend([cols["requested_declaration"], cols["requested_implementation"]])
    else:
        raise ValueError("requested_atoms_mode 只能是 declaration / implementation / union")

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"输入 CSV 缺少这些列: {missing}")


def get_effective_atoms(atoms: Set[str], tier: int) -> Set[str]:
    return (atoms & TIER_MAP[tier]) - BASELINES[tier]


def compute_reach(
    skill_download_count: int,
    skill_star_count: int,
    skill_fork_count: int,
    developer_github_stars: int,
    developer_is_org: bool,
    alpha: float,
) -> ReachResult:
    n_eff = skill_download_count if skill_download_count > 0 else 10 * skill_star_count
    if developer_github_stars >= 1000:
        lambda_dev = 1.8
    elif developer_is_org:
        lambda_dev = 1.5
    else:
        lambda_dev = 1.0

    reach = math.log10(n_eff + alpha * skill_fork_count + 1) * lambda_dev
    return ReachResult(value=reach, n_eff=n_eff, lambda_dev=lambda_dev)


def compute_tier_delta_set_mode(requested_atoms: Set[str], necessary_atoms: Set[str], tier: int) -> Tuple[int, Set[str]]:
    req = get_effective_atoms(requested_atoms, tier)
    nec = get_effective_atoms(necessary_atoms, tier)
    extra = req - nec
    return len(extra), extra


def compute_tier_delta_count_mode(requested_atoms: Set[str], necessary_atoms: Set[str], tier: int) -> Tuple[int, Set[str]]:
    req = get_effective_atoms(requested_atoms, tier)
    nec = get_effective_atoms(necessary_atoms, tier)
    delta = max(0, len(req) - len(nec))
    extra = set(sorted(req)) if delta > 0 else set()
    return delta, extra


def compute_phi(
    requested_atoms: Set[str],
    necessary_atoms: Set[str],
    phi_mode: str,
) -> PhiResult:
    unknown_requested_atoms = requested_atoms - ALL_ATOMS
    unknown_necessary_atoms = necessary_atoms - ALL_ATOMS

    requested_atoms = requested_atoms & ALL_ATOMS
    necessary_atoms = necessary_atoms & ALL_ATOMS

    deltas: Dict[int, int] = {}
    extra_atoms: Dict[int, Set[str]] = {}

    mode = phi_mode.strip().lower()
    for tier in [1, 2, 3, 4]:
        if mode == "count":
            delta, extra = compute_tier_delta_count_mode(requested_atoms, necessary_atoms, tier)
        else:
            delta, extra = compute_tier_delta_set_mode(requested_atoms, necessary_atoms, tier)
        deltas[tier] = delta
        extra_atoms[tier] = extra

    phi = sum(WEIGHTS[tier] * deltas[tier] for tier in [1, 2, 3, 4])
    return PhiResult(
        value=phi,
        deltas=deltas,
        extra_atoms=extra_atoms,
        unknown_requested_atoms=unknown_requested_atoms,
        unknown_necessary_atoms=unknown_necessary_atoms,
    )


def compute_gamma(deltas: Mapping[int, int]) -> GammaResult:
    path_A = int(deltas[1] > 0 and deltas[2] > 0)
    path_B = int(deltas[1] > 0 and deltas[3] > 0)
    path_C = int(deltas[2] > 0 and deltas[3] > 0)
    path_D = int(deltas[4] > 0 and deltas[2] > 0)
    path_E = int(deltas[4] > 0 and deltas[3] > 0)

    gamma = (
        1
        + BETA["A"] * path_A
        + BETA["B"] * path_B
        + BETA["C"] * path_C
        + BETA["D"] * path_D
        + BETA["E"] * path_E
    )
    return GammaResult(
        value=gamma,
        paths={
            "path_A": path_A,
            "path_B": path_B,
            "path_C": path_C,
            "path_D": path_D,
            "path_E": path_E,
        },
    )


def get_requested_atoms(row: pd.Series, config: Mapping[str, Any]) -> Set[str]:
    cols = config["columns"]
    mode = str(config["requested_atoms_mode"]).strip().lower()

    decl = parse_atom_set(row.get(cols["requested_declaration"]))
    impl = parse_atom_set(row.get(cols["requested_implementation"]))

    if mode == "declaration":
        return decl
    if mode == "implementation":
        return impl
    return decl | impl


def score_one_skill(row: pd.Series, config: Mapping[str, Any]) -> pd.Series:
    cols = config["columns"]

    requested_atoms = get_requested_atoms(row, config)
    necessary_atoms = parse_atom_set(row[cols["necessary_atoms"]])

    reach_result = compute_reach(
        skill_download_count=normalize_int(row[cols["skill_download_count"]]),
        skill_star_count=normalize_int(row[cols["skill_star_count"]]),
        skill_fork_count=normalize_int(row[cols["skill_fork_count"]]),
        developer_github_stars=normalize_int(row[cols["developer_github_stars"]]),
        developer_is_org=normalize_bool(row[cols["developer_is_org"]]),
        alpha=float(config["alpha"]),
    )

    phi_result = compute_phi(
        requested_atoms=requested_atoms,
        necessary_atoms=necessary_atoms,
        phi_mode=str(config["phi_mode"]),
    )

    gamma_result = compute_gamma(phi_result.deltas)
    pdei_score = reach_result.value * phi_result.value * gamma_result.value

    return pd.Series({
        "requested_atoms_used": stringify_atom_set(requested_atoms),
        "necessary_atoms_used": stringify_atom_set(necessary_atoms),
        "reach": round(reach_result.value, 3),
        "phi": round(phi_result.value, 3),
        "gamma": round(gamma_result.value, 3),
        "pdei_score": round(pdei_score, 2),
        "n_eff": reach_result.n_eff,
        "lambda_dev": round(reach_result.lambda_dev, 3),
        "delta_t1": phi_result.deltas[1],
        "delta_t2": phi_result.deltas[2],
        "delta_t3": phi_result.deltas[3],
        "delta_t4": phi_result.deltas[4],
        "extra_t1": stringify_atom_set(phi_result.extra_atoms[1]),
        "extra_t2": stringify_atom_set(phi_result.extra_atoms[2]),
        "extra_t3": stringify_atom_set(phi_result.extra_atoms[3]),
        "extra_t4": stringify_atom_set(phi_result.extra_atoms[4]),
        "unknown_requested_atoms": stringify_atom_set(phi_result.unknown_requested_atoms),
        "unknown_necessary_atoms": stringify_atom_set(phi_result.unknown_necessary_atoms),
        **gamma_result.paths,
    })


def score_all_skills(df: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    score_df = df.apply(lambda row: score_one_skill(row, config), axis=1)
    return pd.concat([df, score_df], axis=1)


def get_top_risk_skills(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    return df.nlargest(top_n, "pdei_score").copy()


def build_path_trigger_stats(df: pd.DataFrame, config: Mapping[str, Any], top_n: int = 3) -> Dict[str, Dict[str, Any]]:
    cols = config["columns"]
    id_cols = [c for c in [cols.get("skill_name"), cols.get("domain"), cols.get("source_plat")] if c and c in df.columns]
    id_cols = list(dict.fromkeys(id_cols))
    keep_cols = id_cols + ["pdei_score"]

    stats: Dict[str, Dict[str, Any]] = {}
    for path_col in ["path_A", "path_B", "path_C", "path_D", "path_E"]:
        triggered = df[df[path_col] == 1].copy()
        top_cases = []
        if not triggered.empty:
            top_cases = triggered.nlargest(top_n, "pdei_score")[keep_cols].to_dict(orient="records")
        stats[path_col] = {
            "trigger_rate": float(df[path_col].mean()) if len(df) else 0.0,
            "trigger_count": int(df[path_col].sum()),
            "avg_pdei_when_triggered": float(triggered["pdei_score"].mean()) if not triggered.empty else 0.0,
            "top_cases": top_cases,
        }
    return stats


def summarize_by_domain(df: pd.DataFrame, domain_col: str) -> pd.DataFrame:
    if domain_col not in df.columns:
        raise ValueError(f"找不到 domain 列: {domain_col}")
    summary = (
        df.groupby(domain_col, dropna=False)
        .agg(
            skill_count=("pdei_score", "size"),
            avg_pdei=("pdei_score", "mean"),
            median_pdei=("pdei_score", "median"),
            avg_reach=("reach", "mean"),
            avg_phi=("phi", "mean"),
            avg_gamma=("gamma", "mean"),
            path_A_rate=("path_A", "mean"),
            path_B_rate=("path_B", "mean"),
            path_C_rate=("path_C", "mean"),
            path_D_rate=("path_D", "mean"),
            path_E_rate=("path_E", "mean"),
        )
        .reset_index()
        .sort_values(["avg_pdei", "skill_count"], ascending=[False, False])
    )
    return summary


def export_full_scores_csv(df: pd.DataFrame, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def export_top_risk_csv(df: pd.DataFrame, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def export_path_trigger_stats_json(stats: Dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return output_path


def export_domain_summary_csv(df: pd.DataFrame, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def export_all_outputs(scored_df: pd.DataFrame, config: Mapping[str, Any]) -> Dict[str, Path]:
    out_dir = Path(config["out_dir"])
    prefix = str(config["output_prefix"])
    top_n = int(config["top_n"])
    domain_col = config["columns"]["domain"]

    full_scores_path = export_full_scores_csv(
        scored_df,
        out_dir / f"{prefix}_scores_full_v3.csv",
    )

    top_df = get_top_risk_skills(scored_df, top_n=top_n)
    top_scores_path = export_top_risk_csv(
        top_df,
        out_dir / f"{prefix}_top100_v3.csv",
    )

    path_stats = build_path_trigger_stats(scored_df, config=config)
    path_stats_path = export_path_trigger_stats_json(
        path_stats,
        out_dir / f"{prefix}_path_trigger_stats.json",
    )

    domain_summary = summarize_by_domain(scored_df, domain_col=domain_col)
    domain_summary_path = export_domain_summary_csv(
        domain_summary,
        out_dir / f"{prefix}_domain_pdei_summary.csv",
    )

    return {
        "full_scores": full_scores_path,
        "top_scores": top_scores_path,
        "path_stats": path_stats_path,
        "domain_summary": domain_summary_path,
    }


def run_pdei_pipeline(config: Mapping[str, Any]) -> Dict[str, Path]:
    df = load_input_csv(config["input_csv"])
    validate_input_columns(df, config)
    scored_df = score_all_skills(df, config)
    return export_all_outputs(scored_df, config)


def print_run_summary(output_paths: Mapping[str, Path]) -> None:
    print("PDEI 计算完成，产出如下：")
    for name, path in output_paths.items():
        print(f"- {name}: {path}")


def main() -> None:
    output_paths = run_pdei_pipeline(CONFIG)
    print_run_summary(output_paths)


if __name__ == "__main__":
    main()
