"""files manifest (Phase 6 M3; ADR-064).

Object storage behind presigned URLs with server-chosen tenant keys. Modules declare the
purposes they store (``FILE_PURPOSES``: allowed types, size and count limits, whether
applicants may download); most access is authorised through the owning object's permission.
"""

MODULE = {
    "code": "files",
    "name": "Files",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["tenancy"],
    "sellable": False,
}

PERMISSIONS = [
    {"code": "files.file.view", "description": "Download files of the organisation"},
    {"code": "files.file.upload", "description": "Upload files"},
]
