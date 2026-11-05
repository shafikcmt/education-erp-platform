import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_custom_user_model_is_active():
    assert User._meta.label == "identity.User"
    assert User._meta.db_table == "identity_user"


def test_user_has_uuidv7_primary_key_and_timestamps():
    user = User.objects.create_user("Teacher@Example.COM", "a-strong-pass-123")
    assert isinstance(user.pk, uuid.UUID) and user.pk.version == 7
    assert user.created_at is not None and user.updated_at is not None


def test_email_is_normalised_and_used_as_username():
    user = User.objects.create_user("  Mixed.Case@Example.com ", "a-strong-pass-123")
    assert user.email == "mixed.case@example.com"
    assert user.get_username() == "mixed.case@example.com"
    assert user.check_password("a-strong-pass-123")
    assert not user.is_staff and not user.is_superuser


def test_email_uniqueness_is_case_insensitive_at_database_level():
    User.objects.create_user("dup@example.com", "a-strong-pass-123")
    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        User.objects.create(email="DUP@example.com")


def test_user_without_password_has_unusable_password():
    user = User.objects.create_user("invited@example.com")
    assert not user.has_usable_password()


def test_superuser_requires_password_and_is_platform_staff():
    with pytest.raises(ValueError, match="password"):
        User.objects.create_superuser("ops@example.com")
    admin = User.objects.create_superuser("ops@example.com", "a-strong-pass-123")
    assert admin.is_staff and admin.is_superuser


def test_email_required():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user("", "a-strong-pass-123")
