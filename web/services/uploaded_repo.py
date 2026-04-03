from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from werkzeug.datastructures import FileStorage


class UploadError(RuntimeError):
    """Raised when an uploaded repository archive is invalid."""


@dataclass(frozen=True, slots=True)
class UploadedRepoRef:
    repo_path: Path
    display_name: str
    temp_root: Path


def ingest_uploaded_zip(file_storage: FileStorage) -> UploadedRepoRef:
    filename = (file_storage.filename or "").strip()
    if not filename:
        raise UploadError("ZIP 文件不能为空。")
    if not filename.lower().endswith(".zip"):
        raise UploadError("只支持上传 .zip 压缩包。")

    temp_root = Path(tempfile.mkdtemp(prefix="openclaw-upload-"))
    archive_path = temp_root / "archive.zip"
    extract_root = temp_root / "extract"
    file_storage.save(archive_path)

    try:
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
        return UploadedRepoRef(
            repo_path=content_root,
            display_name=filename,
            temp_root=temp_root,
        )
    except Exception:
        cleanup_uploaded_repo(temp_root)
        raise


def restore_uploaded_repo(temp_root_value: str, display_name: str) -> UploadedRepoRef:
    temp_root = Path(temp_root_value)
    repo_path = temp_root / "extract"
    if not temp_root.is_dir() or not repo_path.exists():
        raise UploadError("上传的 ZIP 记录不存在或已失效，请重新上传。")

    content_root = _resolve_content_root(repo_path)
    return UploadedRepoRef(
        repo_path=content_root,
        display_name=display_name,
        temp_root=temp_root,
    )


def cleanup_uploaded_repo(temp_root: Path | None) -> None:
    if not temp_root:
        return
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)


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
