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


def _extract_text_from_pdf(filepath: str) -> str:
    """Extract text from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        return f"[Error reading PDF: {e}]"


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
    ".css", ".html", ".sql", ".sh", ".yml", ".yaml", ".json", ".toml",
    ".md", ".txt", ".env", ".cfg", ".ini", ".xml",
}


def add_resume(filepath: str) -> dict:
    """
    Add a resume file (PDF or text) to persistent storage.
    Returns document info dict.
    """
    ensure_dirs()
    filename = os.path.basename(filepath)
    dest = os.path.join(DOCUMENTS_DIR, filename)

    # Copy file to persistent storage
    shutil.copy2(filepath, dest)

    # Extract text
    if filepath.lower().endswith(".pdf"):
        text = _extract_text_from_pdf(dest)
    else:
        text = _extract_text_from_file(dest)

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

    # Remove old copy if exists
    if os.path.exists(dest_folder):
        shutil.rmtree(dest_folder)

    os.makedirs(dest_folder, exist_ok=True)

    files_copied = 0
    for root, dirs, files in os.walk(folder_path):
        # Skip hidden dirs, node_modules, __pycache__, .git, etc.
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
        ]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in CODE_EXTENSIONS:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, folder_path)
                dst = os.path.join(dest_folder, rel)
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
    }

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
            if path.lower().endswith(".pdf"):
                text = _extract_text_from_pdf(path)
            else:
                text = _extract_text_from_file(path)
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
