"""Who may open the dashboard, behind the built-in login of Azure Container Apps (Google).

The platform signs the person in and passes who it is in X-MS-CLIENT-PRINCIPAL (base64 JSON with the claims)
and X-MS-CLIENT-PRINCIPAL-NAME; it drops those headers if a client sends them itself. Google lets any Google
account in, so the dashboard also checks the email against ALLOWED_EMAILS.
"""

import base64
import json
from collections.abc import Mapping

EMAIL_CLAIMS = ("email", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")


def principal_email(headers: Mapping[str, str]) -> str | None:
    raw = headers.get("X-Ms-Client-Principal") or headers.get("x-ms-client-principal")
    if raw:
        try:
            data = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
            for claim in data.get("claims", []):
                if claim.get("typ") in EMAIL_CLAIMS and claim.get("val"):
                    return str(claim["val"]).strip().lower()
        except (ValueError, TypeError, AttributeError):
            pass
    name = headers.get("X-Ms-Client-Principal-Name") or headers.get("x-ms-client-principal-name")
    return name.strip().lower() if name and "@" in name else None


def allowed_emails(value: str) -> set[str]:
    return {e.strip().lower() for e in value.split(",") if e.strip()}


def can_enter(headers: Mapping[str, str], allowed: set[str]) -> bool:
    """With no list (local Docker Compose) anyone on the machine may enter; with a list, only those emails."""
    if not allowed:
        return True
    return principal_email(headers) in allowed
