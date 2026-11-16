"""Tenant services (Phase 3 M4): members, invitations, role assignments, system roles.

Every function runs inside the current tenant's transaction (``tenant_atomic``), re-checks the
actor's permission without the cache, and audits in the tenant's log in the same transaction.
"""
