"""
Persistent document context manager.
Stores uploaded resumes and project code in ~/.interviewagent/documents/
Auto-loads all documents on app launch for every interview session.
"""

import os
import json
import shutil
from config import DOCUMENTS_DIR, ensure_dirs

METADATA_PATH = os.path.join(DOCUMENTS_DIR, "documents.json")


def _load_metadata() -> dict:
    """Load document metadata."""
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"documents": []}


def _save_metadata(metadata: dict):
    """Save document metadata."""
    ensure_dirs()
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)


def _extract_text_from_pdf(filepath: str) -> tuple[str, str | None]:
    """Extract text from a PDF file. Returns (text, error) tuple."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        result = "\n".join(text_parts).strip()
        if not result:
            return "", "PDF appears empty or contains no extractable text."
        return result, None
    except Exception as e:
        return "", f"Could not parse PDF: {e}"


def _extract_text_from_docx(filepath: str) -> tuple[str, str | None]:
    """Extract text from a .docx file. Returns (text, error) tuple."""
    try:
        import docx
        doc = docx.Document(filepath)
        result = "\n".join([p.text for p in doc.paragraphs]).strip()
        if not result:
            return "", "DOCX appears empty or contains no extractable text."
        return result, None
    except Exception as e:
        return "", f"Could not parse DOCX: {e}"


def _extract_text_from_file(filepath: str) -> str:
    """Extract text from a plain text or code file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"[Error reading file: {e}]"


CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sol",
    ".css", ".html", ".sql", ".sh", ".yml", ".yaml", ".toml",
    ".md", ".txt", ".cfg", ".ini", ".xml",
}

RESUME_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# Files that must never be read or forwarded to the LLM regardless of extension.
# Matches against the lowercase filename (not extension alone).
SENSITIVE_FILENAME_PATTERNS = {
    # Secrets and credentials
    ".env", ".env.local", ".env.production", ".env.development",
    "secrets.json", "secrets.yaml", "secrets.yml",
    "credentials.json", "credentials.yaml",
    "serviceaccount.json",
    # Private keys
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    ".pem", ".key", ".p12", ".pfx",
    # Lock files (useless noise in LLM context)
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "gemfile.lock", "cargo.lock",
    # Common config files that may hold tokens
    ".netrc", ".npmrc", ".pypirc",
}


def _is_binary(filepath: str) -> bool:
    """Check if a file is likely binary by looking for NUL bytes."""
    try:
        with open(filepath, 'rb') as f:
            # Check up to 8KB
            chunk = f.read(8192)
            return b'\x00' in chunk
    except Exception:
        return True

def _is_sensitive_file(filename: str) -> bool:
    """Return True if the file should be excluded from LLM context."""
    lower = filename.lower()
    if lower in SENSITIVE_FILENAME_PATTERNS:
        return True
    # Check extension-only patterns
    _, ext = os.path.splitext(lower)
    if ext in {".pem", ".key", ".p12", ".pfx", ".env"}:
        return True
    # Wildcard-style checks for common secret file naming conventions
    if (
        lower.startswith("secrets") or
        lower.startswith(".env") or
        "credentials" in lower or
        "service-account" in lower or
        "service_account" in lower
    ):
        return True
    return False


def add_resume(filepath: str) -> dict:
    """
    Add a resume file (PDF or text) to persistent storage.
    Returns document info dict or error dict.
    """
    ensure_dirs()
    filename = os.path.basename(filepath)
    lower = filename.lower()
    _, ext = os.path.splitext(lower)
    
    # 1. Strict Extension Allowlist
    if ext not in RESUME_EXTENSIONS:
        return {
            "type": "error",
            "filename": filename,
            "error": f"Unsupported resume format: {ext or 'none'}. Use PDF, DOCX, or Text.",
        }

    # 2. Heuristic Binary Check (for files masquerading as text)
    if ext != ".pdf" and ext != ".docx" and _is_binary(filepath):
        return {
            "type": "error",
            "filename": filename,
            "error": "File content appears to be binary (unsupported).",
        }

    dest = os.path.join(DOCUMENTS_DIR, filename)

    # Atomic approach: parse from the SOURCE first, only overwrite dest on success.
    # This guarantees an existing valid resume is never clobbered by a corrupt upload.
    lower_src = filepath.lower()
    if lower_src.endswith(".pdf"):
        text, parse_err = _extract_text_from_pdf(filepath)
    elif lower_src.endswith(".docx"):
        text, parse_err = _extract_text_from_docx(filepath)
    else:
        text = _extract_text_from_file(filepath)
        parse_err = None

    if parse_err:
        return {
            "type": "error",
            "filename": filename,
            "error": parse_err,
        }

    # Only copy after successful parse
    shutil.copy2(filepath, dest)

    doc_info = {
        "type": "resume",
        "filename": filename,
        "path": dest,
        "text_length": len(text),
    }

    # Update metadata
    metadata = _load_metadata()
    # Remove existing resume entries with same filename
    metadata["documents"] = [
        d for d in metadata["documents"] if d.get("filename") != filename
    ]
    metadata["documents"].append(doc_info)
    _save_metadata(metadata)

    return doc_info


def add_project_folder(folder_path: str) -> dict:
    """
    Add a project folder to persistent storage.
    Copies relevant code files, extracts text.
    Returns document info dict.
    """
    ensure_dirs()
    folder_name = os.path.basename(folder_path.rstrip("/"))
    dest_folder = os.path.join(DOCUMENTS_DIR, f"project_{folder_name}")

    temp_folder = dest_folder + ".tmp"

    # Build into a temp folder first so a bad re-upload never clobbers
    # an existing valid stored project.
    if os.path.exists(temp_folder):
        shutil.rmtree(temp_folder)
    os.makedirs(temp_folder, exist_ok=True)

    files_copied = 0
    skipped_sensitive = 0
    for root, dirs, files in os.walk(folder_path):
        # Skip hidden dirs, node_modules, __pycache__, .git, etc.
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
        ]
        for fname in files:
            # Never copy sensitive files
            if _is_sensitive_file(fname):
                skipped_sensitive += 1
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in CODE_EXTENSIONS:
                src = os.path.join(root, fname)
                # Skip mislabeled binaries (e.g. notes.txt that is actually a binary)
                if _is_binary(src):
                    skipped_sensitive += 1
                    continue
                rel = os.path.relpath(src, folder_path)
                dst = os.path.join(temp_folder, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    files_copied += 1
                except Exception:
                    pass

    doc_info = {
        "type": "project",
        "filename": folder_name,
        "path": dest_folder,
        "files_count": files_copied,
        "skipped_sensitive": skipped_sensitive,
    }

    # Reject empty projects — no usable files were found
    if files_copied == 0:
        shutil.rmtree(temp_folder, ignore_errors=True)
        return {
            "type": "error",
            "filename": folder_name,
            "error": (
                f"No supported source files found in '{folder_name}'. "
                f"{skipped_sensitive} file(s) were skipped (sensitive/binary/unsupported)."
            ),
        }

    # Replace old persisted project only after the new copy succeeded.
    if os.path.exists(dest_folder):
        shutil.rmtree(dest_folder)
    os.replace(temp_folder, dest_folder)

    metadata = _load_metadata()
    metadata["documents"] = [
        d for d in metadata["documents"]
        if not (d.get("type") == "project" and d.get("filename") == folder_name)
    ]
    metadata["documents"].append(doc_info)
    _save_metadata(metadata)

    return doc_info


def add_code_file(filepath: str) -> dict:
    """Add a single code file to persistent storage."""
    ensure_dirs()
    filename = os.path.basename(filepath)
    lower = filename.lower()
    _, ext = os.path.splitext(lower)

    # 1. Strict Sensitive Check
    if _is_sensitive_file(filename):
        return {
            "type": "error",
            "filename": filename,
            "error": "File excluded: sensitive content (secret/env/config)",
        }
    
    # 2. Strict Extension Check
    if ext not in CODE_EXTENSIONS:
        return {
            "type": "error",
            "filename": filename,
            "error": f"Unsupported code format: {ext or 'none'}. Supported: {', '.join(sorted(CODE_EXTENSIONS))}",
        }
    
    # 3. Content Check
    if _is_binary(filepath):
        return {
            "type": "error",
            "filename": filename,
            "error": "File content appears to be binary (unsupported).",
        }

    dest = os.path.join(DOCUMENTS_DIR, filename)
    shutil.copy2(filepath, dest)

    doc_info = {
        "type": "code_file",
        "filename": filename,
        "path": dest,
    }

    metadata = _load_metadata()
    metadata["documents"] = [
        d for d in metadata["documents"] if d.get("filename") != filename
    ]
    metadata["documents"].append(doc_info)
    _save_metadata(metadata)

    return doc_info


def remove_document(filename: str):
    """Remove a document from persistent storage."""
    metadata = _load_metadata()
    doc = next(
        (d for d in metadata["documents"] if d.get("filename") == filename), None
    )
    if doc:
        path = doc.get("path", "")
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
        metadata["documents"] = [
            d for d in metadata["documents"] if d.get("filename") != filename
        ]
        _save_metadata(metadata)


def get_all_documents() -> list:
    """Get metadata for all stored documents."""
    return _load_metadata().get("documents", [])


def build_context_string(max_chars: int = 12000) -> str:
    """
    Build a context string from all uploaded documents.
    Used as system prompt context for the LLM.
    """
    metadata = _load_metadata()
    parts = []
    total_chars = 0

    for doc in metadata.get("documents", []):
        path = doc.get("path", "")
        doc_type = doc.get("type", "")
        filename = doc.get("filename", "")

        if doc_type == "resume":
            lower_path = path.lower()
            if lower_path.endswith(".pdf"):
                text, _err = _extract_text_from_pdf(path)
            elif lower_path.endswith(".docx"):
                text, _err = _extract_text_from_docx(path)
            else:
                text = _extract_text_from_file(path)
                _err = None
            if _err or not text:
                continue  # Skip corrupt/empty files rather than inject error strings
            header = f"=== RESUME: {filename} ===\n"
            section = header + text

        elif doc_type == "project":
            file_texts = []
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for fname in sorted(files):
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, path)
                        content = _extract_text_from_file(fpath)
                        file_texts.append(f"--- {rel} ---\n{content}")
            header = f"=== PROJECT: {filename} ===\n"
            section = header + "\n".join(file_texts)

        elif doc_type == "code_file":
            text = _extract_text_from_file(path)
            header = f"=== CODE FILE: {filename} ===\n"
            section = header + text
        else:
            continue

        # Truncate section if it would exceed budget
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        if len(section) > remaining:
            section = section[:remaining] + "\n[... truncated ...]"

        parts.append(section)
        total_chars += len(section)

    return "\n\n".join(parts)
