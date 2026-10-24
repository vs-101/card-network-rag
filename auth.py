"""Minimal demo authentication with two roles.

NOT production-grade: credentials are hardcoded and hashed with plain
SHA-256 (no salt) purely to avoid storing literal plaintext passwords in
source control. For a real deployment, replace this with a proper identity
provider (e.g. OAuth/SSO) or at minimum salted bcrypt/argon2 hashes stored
outside the repo.

Roles:
  - "general_user": can only retrieve/answer from 'general' content.
  - "compliance_officer": full access, including 'restricted'
    (security-sensitive) content.
"""
import hashlib

ROLE_GENERAL = "general_user"
ROLE_COMPLIANCE = "compliance_officer"

ROLE_LABELS = {
    ROLE_GENERAL: "General User",
    ROLE_COMPLIANCE: "Compliance Officer",
}


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# Demo accounts. Password shown in README for interview demo purposes.
USERS = {
    "analyst": {
        "password_hash": _hash("analyst123"),
        "role": ROLE_GENERAL,
    },
    "compliance": {
        "password_hash": _hash("compliance123"),
        "role": ROLE_COMPLIANCE,
    },
}


def verify_login(username: str, password: str):
    """Return the role string if credentials are valid, else None."""
    user = USERS.get(username)
    if not user:
        return None
    if user["password_hash"] != _hash(password):
        return None
    return user["role"]
