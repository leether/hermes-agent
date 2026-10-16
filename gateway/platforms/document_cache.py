"""Opaque document-cache paths independent of inbound filename length or character set."""
from pathlib import Path
import re
import uuid


def cache_document(data: bytes, filename: str, cache_dir: Path) -> str:
    name = str(filename or "").replace("\x00", "").strip()
    suffix = Path(name).suffix.lower()
    suffix = suffix if re.fullmatch(r"\.[a-zA-Z0-9]{1,16}", suffix) else ""
    destination = cache_dir / f"doc_{uuid.uuid4().hex[:12]}{suffix}"
    destination.write_bytes(data)
    return str(destination)
