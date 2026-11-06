"""DRF session authentication that answers unauthenticated requests with 401 (not 403).

Behaviour is otherwise DRF's ``SessionAuthentication`` (Django session + CSRF on unsafe methods).
The ``WWW-Authenticate: Session`` challenge makes DRF return 401 (docs/API_STANDARDS.md §3).
"""

from rest_framework import authentication
from rest_framework.request import Request


class SessionAuthentication(authentication.SessionAuthentication):
    def authenticate_header(self, request: Request) -> str:
        return 'Session realm="api"'
