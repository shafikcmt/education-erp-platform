"""Template sandbox (exit criterion) and numbering sequences (Phase 5 M5; ADR-056)."""

from __future__ import annotations

import datetime as dt
import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.core.tenancy import tenant_atomic
from apps.customization import numbering, template_services
from apps.customization.models import NumberCounter, NumberingSequence, TemplateDefinition
from apps.customization.templates_engine import TemplateRenderError, check_source, render
from tests.helpers import make_user
from tests.isolation.factories import grant_role, seed_tenant_roles, tenant_events
from tests.isolation.threads import in_thread

pytestmark = pytest.mark.django_db
EMAIL = "customization.email"
NOTICE = "customization.notice"
SMS = "customization.sms"


@pytest.fixture
def owner(org):
    user = make_user("tpl-owner@example.com", mfa=True).user
    grant_role(org.tenant, user, "tenant_owner")
    return user


# --------------------------------------------------------------------------- sandbox security
@pytest.mark.parametrize(
    "source",
    [
        "{{ ''.__class__.__mro__ }}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ recipient.__class__.__init__.__globals__ }}",
        "{{ self._TemplateReference__context }}",
        "{{ recipient|attr('__class__') }}",
        "{{ '%s'|format(recipient) }}",
        "{{ range(10**9)|list }}",
        "{{ lipsum() }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ namespace() }}",
        "{{ items|map(attribute='__class__')|list }}",
        "{{ config }}",
        "{{ request }}",
        "{% set x = recipient.upper.__self__ %}{{ x }}",
    ],
)
def test_escape_payloads_never_render_internals(source):
    with pytest.raises(TemplateRenderError):
        render(source, {"recipient": "A", "items": ["a"]}, html=False, max_output=1000)


@pytest.mark.parametrize(
    "source",
    [
        "{% include 'x.html' %}",
        "{% import 'm' as m %}",
        "{% extends 'base' %}",
        "{% from 'm' import f %}",
    ],
)
def test_loading_other_templates_is_refused_at_save_time(source):
    with pytest.raises(TemplateRenderError, match="not allowed"):
        check_source(source, html=False)


def test_output_size_and_data_limits():
    with pytest.raises(TemplateRenderError, match="longer than"):
        render(
            "{% for i in items %}{{ big }}{% endfor %}",
            {"items": list(range(100)), "big": "x" * 1000},
            html=False,
            max_output=10_000,
        )
    with pytest.raises(TemplateRenderError, match="at most"):
        check_source("x" * 30_000, html=False)
    with pytest.raises(TemplateRenderError, match="not template data"):
        render("{{ x }}", {"x": object()}, html=False, max_output=100)
    with pytest.raises(TemplateRenderError, match="Floats"):
        render("{{ x }}", {"x": 0.1}, html=False, max_output=100)


def test_html_is_autoescaped_and_undefined_variables_fail():
    out = render(
        "<p>{{ title }}</p>", {"title": "<script>alert(1)</script>"}, html=True, max_output=1000
    )
    assert out == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
    with pytest.raises(TemplateRenderError, match="Rendering failed"):
        render("{{ missing }}", {}, html=False, max_output=100)
    assert (
        render("{{ d|date('%d/%m/%Y') }}", {"d": dt.date(2026, 11, 22)}, html=False, max_output=100)
        == "22/11/2026"
    )


# --------------------------------------------------------------------------- template services
def test_templates_are_checked_previewed_and_published(org, owner):
    content = {
        "en": {
            "subject": "Welcome to {{ organisation }}",
            "body": "Dear {{ recipient }},\nSee {{ link }}",
        },
        "bn": {"subject": "{{ organisation }}-এ স্বাগতম", "body": "প্রিয় {{ recipient }}"},
    }
    with tenant_atomic(org.tenant):
        with pytest.raises(ValidationError, match="Unknown template kind"):
            template_services.save_template_draft(
                actor=owner, key="welcome", kind_code="nope.x", name="W", content=content
            )
        with pytest.raises(ValidationError, match="give"):
            template_services.save_template_draft(
                actor=owner, key="welcome", kind_code=EMAIL, name="W", content={"en": {"body": "x"}}
            )
        template_services.save_template_draft(
            actor=owner, key="welcome", kind_code=EMAIL, name="W", content=content
        )
        shown = template_services.preview(kind_code=EMAIL, content=content, locale="bn")
        assert shown == {"body": "প্রিয় A. Rahman", "subject": "Example Academy-এ স্বাগতম"}
        with pytest.raises(ValidationError, match="Undeclared variables"):
            template_services.preview(
                kind_code=EMAIL, content=content, locale="en", data={"password": "x"}
            )
        published = template_services.publish_template(actor=owner, key="welcome")
        assert published.status == "published"
        out = template_services.render_published(
            "welcome", "en", {"organisation": "Org", "recipient": "Ana", "link": "/l"}
        )
        assert out["subject"] == "Welcome to Org"
        # Header injection: a subject that renders to several lines is refused.
        bad = {"en": {"subject": "Hi {{ recipient }}", "body": "x"}}
        template_services.save_template_draft(
            actor=owner, key="inject", kind_code=EMAIL, name="I", content=bad
        )
        with pytest.raises(ValidationError, match="single line"):
            template_services.preview(
                kind_code=EMAIL, content=bad, locale="en", data={"recipient": "x\nBcc: a@b.c"}
            )
        # SMS output is capped; an over-long message can't be published.
        long_sms = {"en": {"body": "{{ recipient }}" + "x" * 500}}
        template_services.save_template_draft(
            actor=owner, key="sms", kind_code=SMS, name="S", content=long_sms
        )
        with pytest.raises(ValidationError, match="longer than 480"):
            template_services.publish_template(actor=owner, key="sms")
        body = "<h1>{{ title }}</h1><ul>{% for i in items %}<li>{{ i }}</li>{% endfor %}</ul>"
        notice = {"en": {"body": body}}
        assert (
            "<li>One</li>"
            in template_services.preview(kind_code=NOTICE, content=notice, locale="en")["body"]
        )
    assert len(tenant_events(org.tenant, action="customization.template.published")) == 1


# --------------------------------------------------------------------------- numbering
@pytest.mark.parametrize(
    ("pattern", "scope", "message"),
    [
        ("RCP-{YYYY}", "tenant", "exactly one"),
        ("{SEQ:3}{SEQ:2}", "tenant", "exactly one"),
        ("RCP {SEQ:5}", "tenant", "Only letters"),
        ("{INST}-{SEQ:4}", "tenant", "INST"),
        ("{CAMPUS}-{SEQ:4}", "institution", "CAMPUS"),
        ("{SEQ:20}", "tenant", "exactly one"),
    ],
)
def test_patterns_are_validated(pattern, scope, message):
    with pytest.raises(ValidationError, match=message):
        numbering.validate_pattern(pattern, scope)


def test_numbers_are_formatted_scoped_reset_and_gap_free(org, owner):
    today = dt.date(2026, 11, 22)
    with tenant_atomic(org.tenant):
        numbering.define_sequence(
            actor=owner,
            key="receipt",
            name="Receipts",
            pattern="RCP-{INST}-{YYYY}-{SEQ:5}",
            scope="institution",
            reset="yearly",
        )
        with pytest.raises(ValidationError, match="exists"):
            numbering.define_sequence(actor=owner, key="receipt", name="R", pattern="{SEQ:3}")
        assert (
            numbering.allocate("receipt", institution=org.north, today=today)
            == "RCP-north-2026-00001"
        )
        assert (
            numbering.allocate("receipt", institution=org.north, today=today)
            == "RCP-north-2026-00002"
        )
        assert (
            numbering.allocate("receipt", institution=org.south, today=today)
            == "RCP-south-2026-00001"
        )
        assert (
            numbering.allocate("receipt", institution=org.north, today=dt.date(2027, 1, 2))
            == "RCP-north-2027-00001"
        )
        with pytest.raises(ValidationError, match="per institution"):
            numbering.allocate("receipt", today=today)
    # A rolled-back business transaction gives its number back (gap-free).
    with pytest.raises(RuntimeError), tenant_atomic(org.tenant):
        assert (
            numbering.allocate("receipt", institution=org.north, today=today)
            == "RCP-north-2026-00003"
        )
        raise RuntimeError("payment failed")
    with tenant_atomic(org.tenant):
        assert (
            numbering.allocate("receipt", institution=org.north, today=today)
            == "RCP-north-2026-00003"
        )
        numbering.define_sequence(
            actor=owner,
            key="student_id",
            name="IDs",
            pattern="S{AY}-{SEQ:4}",
            scope="institution",
            reset="academic_year",
        )
        assert numbering.allocate("student_id", institution=org.north, today=today) == "S2026-0001"


def test_allocation_fails_closed_without_a_tenant(org):
    from apps.core.tenancy.exceptions import TenantContextMissing

    with pytest.raises(TenantContextMissing):
        numbering.allocate("receipt")


def test_concurrent_allocations_never_duplicate(committed_tenant_pair):
    """Two real transactions allocate at once: distinct, consecutive numbers (row lock)."""
    tenant = committed_tenant_pair[0]

    def setup() -> None:
        with tenant_atomic(tenant):
            NumberingSequence.objects.create(key="ticket", name="T", pattern="T-{SEQ:3}")

    def cleanup() -> None:
        with tenant_atomic(tenant):
            NumberCounter.objects.all().delete()
            NumberingSequence.objects.all().delete()

    in_thread(setup)
    barrier = threading.Barrier(4)
    numbers: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        def run() -> None:
            with tenant_atomic(tenant):
                barrier.wait()
                value = numbering.allocate("ticket")
            with lock:
                numbers.append(value)

        try:
            in_thread(run)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert sorted(numbers) == ["T-001", "T-002", "T-003", "T-004"]
    finally:
        in_thread(cleanup)


def test_templates_and_counters_are_tenant_isolated(org, owner, tenant_site):
    other = tenant_site(slug="bravo")
    seed_tenant_roles(other)
    with tenant_atomic(org.tenant):
        template_services.save_template_draft(
            actor=owner, key="note", kind_code=SMS, name="N", content={"en": {"body": "Hi"}}
        )
        numbering.define_sequence(actor=owner, key="receipt", name="R", pattern="R-{SEQ:3}")
        numbering.allocate("receipt")
    with tenant_atomic(other):
        assert TemplateDefinition.objects.count() == NumberingSequence.objects.count() == 0
        with pytest.raises(ValidationError, match="Unknown numbering"):
            numbering.allocate("receipt")
        with connection.cursor() as cursor:  # raw SQL as erp_app: RLS, not the manager
            for table in (
                "customization_templatedefinition",
                "customization_numberingsequence",
                "customization_numbercounter",
            ):
                cursor.execute(
                    f"SELECT count(*) FROM {table} WHERE tenant_id = %s", [org.tenant.id]
                )
                assert cursor.fetchone() == (0,), table
