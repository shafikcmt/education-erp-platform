"""notifications_core manifest (Phase 5 M4; ADR-059): in-app notifications and email through the
existing mail path. SMS and push arrive with ``communication`` (Phase 14)."""

MODULE = {
    "code": "notifications_core",
    "name": "Notifications",
    "category": "platform",
    "version": "1.0.0",
    "dependencies": ["tenancy"],
    "sellable": False,
}
