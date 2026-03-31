from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class ScanRunError(RuntimeError):
    """Raised when a single-skill scan cannot produce a usable result."""


@dataclass(slots=True)
class ScanRunResult:
    run_id: str
    run_dir: Path
    skill_id: str
    skill_key: str
    stdout: str
    stderr: str


def safe_skill_key(skill_id: str) -> str:
    return skill_id.replace("/", "__")


def run_single_skill_scan(
    skill_id: str,
    *,
    python_bin: str | None = None,
    script_path: str | Path = REPO_ROOT / "scripts" / "run_single_skill_from_skills_sh.py",
    db_path: str | Path = REPO_ROOT / "crawling" / "skills" / "skills_sh" / "skills.db",
    repos_root: str | Path = REPO_ROOT / "skills" / "skill_sh_test",
    output_root: str | Path = REPO_ROOT / "outputs" / "web_runs",
    matrix_path: str | Path = REPO_ROOT / "analyzer" / "security matrix.md",
    llm_review_mode: str = "off",
) -> ScanRunResult:
    normalized_skill_id = skill_id.strip()
    if not normalized_skill_id:
        raise ScanRunError("skill_id 不能为空。")

    resolved_python = python_bin or sys.executable
    resolved_script = Path(script_path)
    resolved_output_root = Path(output_root)
    command = [
        resolved_python,
        str(resolved_script),
        "--skill-id",
        normalized_skill_id,
        "--db",
        str(db_path),
        "--repos-root",
        str(repos_root),
        "--output-dir",
        str(resolved_output_root),
        "--format",
        "json",
        "--matrix-path",
        str(matrix_path),
        "--llm-review-mode",
        llm_review_mode,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    output_dir = _extract_output_dir(completed.stdout)
    skill_key = safe_skill_key(normalized_skill_id)

    if completed.returncode != 0:
        raise ScanRunError(_build_failure_message(completed, output_dir))

    if output_dir is None:
        raise ScanRunError("扫描已执行，但未在输出中找到 Output directory。")

    run_dir = Path(output_dir)
    case_path = run_dir / "cases" / f"{skill_key}.json"
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        raise ScanRunError(f"扫描已完成，但缺少 manifest 文件：{manifest_path}")
    if not case_path.is_file():
        raise ScanRunError(f"扫描已完成，但缺少 case 文件：{case_path}")

    return ScanRunResult(
        run_id=run_dir.name,
        run_dir=run_dir,
        skill_id=normalized_skill_id,
        skill_key=skill_key,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _extract_output_dir(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("Output directory:"):
            return line.partition(":")[2].strip()
    return None


def _build_failure_message(completed: subprocess.CompletedProcess[str], output_dir: str | None) -> str:
    lines: list[str] = [f"扫描失败，退出码 {completed.returncode}。"]
    if output_dir:
        lines.append(f"输出目录：{output_dir}")
    if completed.stdout.strip():
        lines.append("stdout:")
        lines.append(completed.stdout.strip())
    if completed.stderr.strip():
        lines.append("stderr:")
        lines.append(completed.stderr.strip())
    return "\n".join(lines)
