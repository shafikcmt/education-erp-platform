"""System roles seeded by ``manage.py seed_roles`` (Phase 2 plan §5.2; CLAUDE.md §9).

Stored as Python data rather than YAML: YAML would need PyYAML, which is not an approved
dependency. ``permissions`` lists codes registered in Phase 2. ``planned`` lists codes of modules
not built yet; ``seed_roles`` links them automatically once the owning module registers them.
``"*"`` means every registered permission (Super Admin only).

Template roles are copied by tenants from Phase 3; self-service codes come from
``SelfServiceSource`` and are therefore not listed.
"""

from typing import Any

ALL = "*"

PLATFORM_ROLES: list[dict[str, Any]] = [
    {
        "code": "super_admin",
        "name": "Super Admin",
        "bn": "সুপার অ্যাডমিন",
        "description": "Full platform administration. No tenant data without a support session.",
        "permissions": [ALL],
        "planned": [],
    },
    {
        "code": "platform_support",
        "name": "Platform Support",
        "bn": "প্ল্যাটফর্ম সাপোর্ট",
        "description": "Diagnostics; tenant data only via audited support sessions (Phase 3).",
        "permissions": [
            "identity.user.view",
            "identity.session.revoke_any",
            "identity.mfa.reset",
            "audit.event.view",
        ],
        "planned": ["platform.support_session.request"],
    },
    {
        "code": "platform_billing",
        "name": "Platform Billing",
        "bn": "প্ল্যাটফর্ম বিলিং",
        "description": "Plans, subscriptions and SaaS invoices; no tenant academic data.",
        "permissions": [],
        "planned": ["billing.plan.view", "billing.subscription.view", "billing.invoice.view"],
    },
    {
        "code": "platform_onboarding",
        "name": "Platform Onboarding",
        "bn": "প্ল্যাটফর্ম অনবোর্ডিং",
        "description": "Create and configure new tenants during onboarding.",
        "permissions": ["identity.user.create", "identity.user.view"],
        "planned": ["tenancy.tenant.create"],
    },
]

_ALL_TYPES = [
    "school",
    "college",
    "university",
    "madrasa",
    "coaching_center",
    "training_institute",
]


def _template(
    code: str, name: str, bn: str, description: str, planned: list[str]
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "bn": bn,
        "description": description,
        "institution_types": _ALL_TYPES,
        "permissions": [],
        "planned": planned,
    }


# Phase 3 M4 (plan §12.3): what the three administrative templates hold. A role is granted
# in a scope, so the same code means "this institution" for an institution admin and "the
# whole organisation" for the owner.
TENANT_VIEW = "tenancy.tenant.view"
_OWNER_CODES = [
    TENANT_VIEW,
    "tenancy.tenant.update",
    "tenancy.institution.view",
    "tenancy.institution.create",
    "tenancy.institution.update",
    "tenancy.institution.archive",
    "tenancy.campus.view",
    "tenancy.campus.create",
    "tenancy.campus.update",
    "tenancy.campus.archive",
    "tenancy.member.view",
    "tenancy.member.invite",
    "tenancy.member.update",
    "tenancy.member.remove",
    "rbac.role.view",
    "rbac.role.create",
    "rbac.role.update",
    "rbac.role.delete",
    "rbac.role.clone",
    "rbac.assignment.view",
    "rbac.assignment.manage",
    "audit.event.view",
    "audit.event.view_ip",
]
_INSTITUTION_ADMIN_CODES = [
    TENANT_VIEW,
    "tenancy.institution.view",
    "tenancy.institution.update",
    "tenancy.campus.view",
    "tenancy.campus.create",
    "tenancy.campus.update",
    "tenancy.campus.archive",
    "tenancy.member.view",
    "tenancy.member.invite",
    "tenancy.member.update",
    "rbac.role.view",
    "rbac.assignment.view",
    "rbac.assignment.manage",
]
_CAMPUS_ADMIN_CODES = [
    TENANT_VIEW,
    "tenancy.institution.view",
    "tenancy.campus.view",
    "tenancy.campus.update",
    "tenancy.member.view",
    "rbac.role.view",
    "rbac.assignment.view",
    "rbac.assignment.manage",
]
TENANT_OWNER = "tenant_owner"

TEMPLATE_ROLES: list[dict[str, Any]] = [
    _template(
        TENANT_OWNER,
        "Tenant Owner",
        "সংস্থার মালিক",
        "Owns the tenant: subscription, institutions and administrators.",
        _OWNER_CODES,
    ),
    _template(
        "institution_admin",
        "Institution Admin",
        "প্রতিষ্ঠান প্রশাসক",
        "Principal/Head/Rector/Muhtamim: manages one institution and its campuses.",
        _INSTITUTION_ADMIN_CODES,
    ),
    _template(
        "campus_admin",
        "Campus Admin",
        "ক্যাম্পাস প্রশাসক",
        "Institution admin capabilities limited to one campus.",
        _CAMPUS_ADMIN_CODES,
    ),
    _template(
        "academic_coordinator",
        "Academic Coordinator",
        "একাডেমিক সমন্বয়ক",
        "Academic structure, timetable and curriculum coordination (incl. HoD).",
        [TENANT_VIEW, "academics.structure.manage", "timetable.timetable.manage"],
    ),
    _template(
        "teacher",
        "Teacher",
        "শিক্ষক",
        "Assigned classes: attendance, marks entry, LMS content.",
        [TENANT_VIEW, "attendance.record.mark", "examinations.marks.enter", "lms.content.manage"],
    ),
    _template(
        "class_teacher",
        "Class Teacher",
        "শ্রেণি শিক্ষক",
        "Teacher plus advisor duties for an assigned section.",
        [TENANT_VIEW, "attendance.record.mark", "students.student.view"],
    ),
    _template(
        "exam_controller",
        "Exam Controller",
        "পরীক্ষা নিয়ন্ত্রক",
        "Exam setup, moderation and result publishing.",
        [TENANT_VIEW, "examinations.exam.manage", "examinations.result.publish"],
    ),
    _template(
        "admission_officer",
        "Admission Officer",
        "ভর্তি কর্মকর্তা",
        "Inquiries, applications and enrollment.",
        [TENANT_VIEW, "admissions.application.manage"],
    ),
    _template(
        "accountant",
        "Accountant",
        "হিসাবরক্ষক",
        "Fee structures, invoices, ledgers and reports.",
        [TENANT_VIEW, "fees.invoice.manage", "accounting.journal.post"],
    ),
    _template(
        "cashier",
        "Cashier",
        "ক্যাশিয়ার",
        "Collects payments and issues receipts.",
        [TENANT_VIEW, "fees.payment.collect"],
    ),
    _template(
        "hr_manager",
        "HR Manager",
        "মানবসম্পদ ব্যবস্থাপক",
        "Staff records, leave and payroll.",
        [TENANT_VIEW, "hr_payroll.payroll.manage"],
    ),
    _template(
        "librarian",
        "Librarian",
        "গ্রন্থাগারিক",
        "Catalog and circulation.",
        [TENANT_VIEW, "library.circulation.manage"],
    ),
    _template(
        "hostel_warden",
        "Hostel Warden",
        "হোস্টেল তত্ত্বাবধায়ক",
        "Allocations, roll-calls, leave and visitors.",
        [TENANT_VIEW, "hostel.allocation.manage"],
    ),
    _template(
        "transport_manager",
        "Transport Manager",
        "পরিবহন ব্যবস্থাপক",
        "Vehicles, routes and assignments.",
        [TENANT_VIEW, "transport.route.manage"],
    ),
    _template(
        "front_desk",
        "Front Desk",
        "ফ্রন্ট ডেস্ক",
        "Inquiries, visitors and notices.",
        [TENANT_VIEW, "admissions.inquiry.manage"],
    ),
    _template(
        "staff_member",
        "Staff",
        "কর্মচারী",
        "Generic non-teaching staff: own profile, attendance, payslips and leave.",
        [TENANT_VIEW, "staff.profile.view_own", "hr_payroll.payslip.view_own"],
    ),
    _template(
        "student",
        "Student",
        "শিক্ষার্থী",
        "Own timetable, attendance, results, invoices and courses.",
        ["students.profile.view_own", "examinations.result.view_own"],
    ),
    _template(
        "guardian",
        "Parent / Guardian",
        "অভিভাবক",
        "Linked children: attendance, results, invoices and payments.",
        ["students.child.view", "fees.invoice.pay"],
    ),
]
