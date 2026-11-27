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
        # Phase 3 M5: the canonical code (owner decision P6, plan §24.5).
        "planned": ["tenancy.support_session.request", "tenancy.tenant.view_any"],
    },
    {
        "code": "platform_billing",
        "name": "Platform Billing",
        "bn": "প্ল্যাটফর্ম বিলিং",
        "description": "Plans, subscriptions and SaaS invoices; no tenant academic data.",
        "permissions": [],
        # Phase 4 (ADR-054 Q4): plans, add-ons, prices, flags and subscriptions.
        "planned": [
            "billing.plan.view",
            "billing.plan.manage",
            "billing.price.manage",
            "billing.subscription.view_any",
            "billing.subscription.manage",
            "module_registry.module.view",
            "module_registry.flag.manage",
            "tenancy.tenant.view_any",
            "billing.invoice.view",
        ],
    },
    {
        "code": "platform_onboarding",
        "name": "Platform Onboarding",
        "bn": "প্ল্যাটফর্ম অনবোর্ডিং",
        "description": "Create and configure new tenants during onboarding.",
        "permissions": ["identity.user.create", "identity.user.view"],
        "planned": ["tenancy.tenant.create", "tenancy.tenant.view_any"],
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
    # Phase 3 M5: support access is decided by the tenant's owners (ADR-045).
    "tenancy.support_session.view",
    "tenancy.support_session.approve",
    "tenancy.support_session.revoke",
    # Phase 4: the organisation's own subscription (read-only).
    "billing.subscription.view",
    # Phase 5: Customization Studio (configuration of the whole organisation).
    "customization.config.view",
    "customization.config.edit",
    "customization.config.publish",
    "customization.rule.view",
    "customization.rule.manage",
    "customization.field.view",
    "customization.field.manage",
    "customization.form.view",
    "customization.form.manage",
    "customization.workflow.view",
    "customization.workflow.manage",
    "customization.template.view",
    "customization.template.manage",
    "customization.numbering.view",
    "customization.numbering.manage",
    # Phase 6: academic structure (years, units, subjects, offerings).
    "academics.year.view",
    "academics.year.manage",
    "academics.structure.view",
    "academics.structure.manage",
    "academics.subject.view",
    "academics.subject.manage",
    "academics.offering.view",
    "academics.offering.manage",
    # Phase 6 M3: files (attached files are authorised through their owners).
    "files.file.view",
    "files.file.upload",
    # Phase 6 M4: admissions.
    "admissions.inquiry.view",
    "admissions.inquiry.manage",
    "admissions.cycle.view",
    "admissions.cycle.manage",
    "admissions.application.view",
    "admissions.application.review",
    "admissions.application.decide",
    # Phase 6 M6: admission tests and the merit list.
    "admissions.test.manage",
    "admissions.test.score",
    "admissions.merit.publish",
    # Phase 7 M1: students (ADR-068, ADR-073).
    "students.student.view",
    "students.student.view_assigned",
    "students.student.manage",
    "students.student.import",
    "students.student.promote",
    "students.student.transfer",
    "students.guardian.view",
    "students.guardian.manage",
    "students.document.view",
    "students.document.upload",
    # Phase 7 M3: staff (ADR-070); view_own so they can assign teachers, who hold it.
    "staff.profile.view",
    "staff.profile.manage",
    "staff.profile.view_own",
    "staff.structure.manage",
    # Phase 7 M7: timetable (ADR-071).
    "timetable.timetable.view",
    "timetable.timetable.manage",
    # Phase 7 M8: so they can invite guardians and students to the portal (nobody grants a code
    # they don't hold; these codes only open children or oneself, never other students).
    "students.child.view",
    "students.profile.view_own",
    "parent_portal.portal.use",
]
# What a tenant owner keeps while the tenant is suspended (restricted mode, D2, plan §11.3):
# review and decide support access, nothing else.
SUSPENDED_OWNER_CODES = frozenset(
    {
        "tenancy.support_session.view",
        "tenancy.support_session.approve",
        "tenancy.support_session.revoke",
    }
)
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
    # Phase 5: Studio configuration of their own institution (and its campuses).
    "customization.config.view",
    "customization.config.edit",
    "customization.config.publish",
    # Phase 6: academic structure (years, units, subjects, offerings).
    "academics.year.view",
    "academics.year.manage",
    "academics.structure.view",
    "academics.structure.manage",
    "academics.subject.view",
    "academics.subject.manage",
    "academics.offering.view",
    "academics.offering.manage",
    # Phase 6 M3: files (and so they can assign admission officers, who upload).
    "files.file.view",
    "files.file.upload",
    # Phase 6 M4: admissions.
    "admissions.inquiry.view",
    "admissions.inquiry.manage",
    "admissions.cycle.view",
    "admissions.cycle.manage",
    "admissions.application.view",
    "admissions.application.review",
    "admissions.application.decide",
    # Phase 6 M6: admission tests and the merit list.
    "admissions.test.manage",
    "admissions.test.score",
    "admissions.merit.publish",
    # Phase 7 M1: students (ADR-068, ADR-073).
    "students.student.view",
    "students.student.view_assigned",
    "students.student.manage",
    "students.student.import",
    "students.student.promote",
    "students.student.transfer",
    "students.guardian.view",
    "students.guardian.manage",
    "students.document.view",
    "students.document.upload",
    # Phase 7 M3: staff (ADR-070); view_own so they can assign teachers, who hold it.
    "staff.profile.view",
    "staff.profile.manage",
    "staff.profile.view_own",
    "staff.structure.manage",
    # Phase 7 M7: timetable (ADR-071).
    "timetable.timetable.view",
    "timetable.timetable.manage",
    # Phase 7 M8: so they can invite guardians and students to the portal (nobody grants a code
    # they don't hold; these codes only open children or oneself, never other students).
    "students.child.view",
    "students.profile.view_own",
    "parent_portal.portal.use",
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
    # Phase 6: campus admins read the academic structure (and so can assign teachers, who read
    # it too: nobody grants permissions they don't hold).
    "academics.year.view",
    "academics.structure.view",
    "academics.subject.view",
    "academics.offering.view",
    # Phase 7 M1: and so can assign teachers and class teachers, who see their students.
    "students.student.view",
    "students.student.view_assigned",
    "students.guardian.view",
    # Phase 7 M3: the campus's staff, and view_own so they can assign teachers, who hold it.
    "staff.profile.view",
    "staff.profile.view_own",
    # Phase 7 M7: and so can assign teachers, who see timetables.
    "timetable.timetable.view",
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
        [
            TENANT_VIEW,
            "academics.year.view",
            "academics.year.manage",
            "academics.structure.view",
            "academics.structure.manage",
            "academics.subject.view",
            "academics.subject.manage",
            "academics.offering.view",
            "academics.offering.manage",
            "timetable.timetable.view",
            "timetable.timetable.manage",
            # Phase 7 M1: students in scope, promotion.
            "students.student.view",
            "students.student.view_assigned",
            "students.student.manage",
            "students.student.promote",
            "students.guardian.view",
            # Phase 7 M3: staff in scope, to choose subject teachers and class teachers.
            "staff.profile.view",
        ],
    ),
    _template(
        "teacher",
        "Teacher",
        "শিক্ষক",
        "Assigned classes: attendance, marks entry, LMS content.",
        [
            TENANT_VIEW,
            "academics.structure.view",
            "academics.subject.view",
            "academics.offering.view",
            "attendance.record.mark",
            "examinations.marks.enter",
            "lms.content.manage",
            # Phase 7 M1 (ADR-073): only the students they teach.
            "students.student.view_assigned",
            # Phase 7 M3: their own staff profile.
            "staff.profile.view_own",
            "timetable.timetable.view",  # Phase 7 M7
        ],
    ),
    _template(
        "class_teacher",
        "Class Teacher",
        "শ্রেণি শিক্ষক",
        "Teacher plus advisor duties for an assigned section.",
        # Phase 7 M1 (ADR-073): advisors see the students of their units, not the institution.
        [
            TENANT_VIEW,
            "attendance.record.mark",
            "students.student.view_assigned",
            "students.guardian.view",
            "staff.profile.view_own",  # Phase 7 M3
            "timetable.timetable.view",  # Phase 7 M7
        ],
    ),
    _template(
        "exam_controller",
        "Exam Controller",
        "পরীক্ষা নিয়ন্ত্রক",
        "Exam setup, moderation and result publishing.",
        [
            TENANT_VIEW,
            "examinations.exam.manage",
            "examinations.result.publish",
            # Phase 6 (ADR-067): admission test scores only (seat lists, no application files).
            "admissions.test.score",
        ],
    ),
    _template(
        "admission_officer",
        "Admission Officer",
        "ভর্তি কর্মকর্তা",
        "Inquiries, applications and enrollment.",
        [
            TENANT_VIEW,
            "admissions.inquiry.view",
            "admissions.inquiry.manage",
            "admissions.cycle.view",
            "admissions.application.view",
            "admissions.application.review",
            "admissions.test.manage",
            "admissions.test.score",
            "files.file.upload",
            # Phase 7 M1: completing enrollment of admitted students.
            "students.student.view",
            "students.student.manage",
            "students.student.import",
            "students.guardian.view",
            "students.guardian.manage",
            "students.document.view",
            "students.document.upload",
        ],
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
        [
            TENANT_VIEW,
            "hr_payroll.payroll.manage",
            # Phase 7 M3: staff records and structure.
            "staff.profile.view",
            "staff.profile.manage",
            "staff.structure.manage",
        ],
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
        [TENANT_VIEW, "admissions.inquiry.view", "admissions.inquiry.manage"],
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
        [
            "students.profile.view_own",
            "examinations.result.view_own",
            "timetable.timetable.view",
            "parent_portal.portal.use",
        ],
    ),
    _template(
        "guardian",
        "Parent / Guardian",
        "অভিভাবক",
        "Linked children: attendance, results, invoices and payments.",
        [
            "students.child.view",
            "fees.invoice.pay",
            "timetable.timetable.view",
            "parent_portal.portal.use",
        ],
    ),
]
