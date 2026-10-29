"""Resolve and check files sent to Listmonk, whether uploaded as base64 or read from a server-local path.

Every check runs before any request is made, so a rejected upload never reaches Listmonk.
"""

import base64
import binascii
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ValidationError

MB = 1024 * 1024

# SVG is left out on purpose: Listmonk serves media from a public URL and SVG can carry script.
MEDIA_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
MEDIA_MAX_BYTES = 5 * MB

IMPORT_EXTENSIONS = frozenset({".csv", ".zip"})
IMPORT_MAX_BYTES = 10 * MB

_CONTENT_TYPES = {".csv": "text/csv", ".zip": "application/zip", ".webp": "image/webp"}


@dataclass(frozen=True)
class Upload:
    filename: str
    content: bytes
    content_type: str


def decode_base64(content_base64: str, what: str) -> bytes:
    """Strictly decode base64 (whitespace allowed), naming ``what`` in the error."""
    try:
        return base64.b64decode("".join(content_base64.split()), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValidationError(f"{what}: content_base64 is not valid base64 ({e})", field="content_base64") from e


def content_type_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _CONTENT_TYPES.get(ext) or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def resolve_upload(
    *,
    content_base64: str | None,
    filename: str | None,
    file_path: str | None,
    allowed_extensions: frozenset[str],
    max_bytes: int,
) -> Upload:
    """Return the file to send from exactly one source, enforcing type and size limits."""
    has_content = content_base64 is not None
    if has_content == (file_path is not None):
        raise ValidationError("Give exactly one of content_base64 (with filename) or file_path")

    if has_content:
        if not filename:
            raise ValidationError("filename is required with content_base64", field="filename")
        name = Path(filename).name
    else:
        assert file_path is not None
        path = Path(file_path)
        if not path.is_file():
            raise ValidationError(f"File not found: {file_path}", field="file_path", value=file_path)
        name = path.name

    ext = Path(name).suffix.lower()
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"{name}: file type not allowed; allowed types are {allowed}", field="filename")

    if has_content:
        assert content_base64 is not None
        content = decode_base64(content_base64, name)
    else:
        size = path.stat().st_size
        if size > max_bytes:
            raise ValidationError(f"{name}: {size} bytes exceeds the {max_bytes // MB} MB limit")
        content = path.read_bytes()

    if len(content) > max_bytes:
        raise ValidationError(f"{name}: {len(content)} bytes exceeds the {max_bytes // MB} MB limit")

    return Upload(filename=name, content=content, content_type=content_type_for(name))
