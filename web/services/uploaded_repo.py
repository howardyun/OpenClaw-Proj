from __future__ import annotations

import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from werkzeug.datastructures import FileStorage


class UploadError(RuntimeError):
    """Raised when an uploaded repository archive is invalid."""


@dataclass(frozen=True, slots=True)
class UploadedRepoRef:
    upload_key: str
    repo_path: Path
    display_name: str


def ingest_uploaded_zip(file_storage: FileStorage, uploads_workspace: Path) -> UploadedRepoRef:
    filename = (file_storage.filename or "").strip()
    if not filename:
        raise UploadError("ZIP 文件不能为空。")
    if not filename.lower().endswith(".zip"):
        raise UploadError("只支持上传 .zip 压缩包。")

    uploads_workspace.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_segment(Path(filename).stem)
    upload_key = f"upload-{safe_name}-{uuid.uuid4().hex[:8]}"
    final_repo_path = uploads_workspace / upload_key

    with tempfile.TemporaryDirectory(prefix="upload-", dir=str(uploads_workspace)) as temp_root:
        temp_root_path = Path(temp_root)
        archive_path = temp_root_path / "archive.zip"
        extract_root = temp_root_path / "extract"
        file_storage.save(archive_path)

        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                if not members:
                    raise UploadError("ZIP 压缩包是空的。")
                for member in members:
                    _validate_zip_member(member.filename)
                archive.extractall(extract_root)
        except zipfile.BadZipFile as exc:
            raise UploadError("上传文件不是有效的 ZIP 压缩包。") from exc

        content_root = _resolve_content_root(extract_root)
        if final_repo_path.exists():
            shutil.rmtree(final_repo_path)
        shutil.copytree(content_root, final_repo_path)

    return UploadedRepoRef(
        upload_key=upload_key,
        repo_path=final_repo_path,
        display_name=filename,
    )


def resolve_uploaded_repo(uploads_workspace: Path, upload_key: str) -> Path:
    safe_key = _safe_segment(upload_key)
    if safe_key != upload_key:
        raise UploadError("上传记录无效。")

    repo_path = uploads_workspace / upload_key
    if not repo_path.is_dir():
        raise UploadError("上传的 ZIP 记录不存在或已失效，请重新上传。")
    return repo_path


def _validate_zip_member(member_name: str) -> None:
    path = PurePosixPath(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise UploadError("ZIP 压缩包包含不安全的路径。")


def _resolve_content_root(extract_root: Path) -> Path:
    top_level_entries = sorted(extract_root.iterdir())
    if not top_level_entries:
        raise UploadError("ZIP 压缩包解压后没有可用内容。")

    if len(top_level_entries) == 1 and top_level_entries[0].is_dir():
        return top_level_entries[0]
    return extract_root


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "upload"
