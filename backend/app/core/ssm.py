"""Load secrets from SSM Parameter Store into the environment at cold start.

On Lambda the secrets (ANTHROPIC_API_KEY, JWT_SECRET_KEY, SSLCOMMERZ_*) are SecureString
parameters under SSM_PARAMETER_PATH (e.g. /story-engine/prod/), never Lambda env vars.
`load_parameters_into_env` runs before Settings is built, so pydantic validates the
loaded values and the production guard (app lifespan) checks them afterwards.

Rules:
- the parameter name's last segment is the setting name (/story-engine/prod/JWT_SECRET_KEY);
- only names that are Settings fields are applied; anything else is ignored;
- a variable already in the environment wins (local dev, explicit overrides);
- values are never logged, only names.

No SSM_PARAMETER_PATH (local dev, tests) means no AWS call and boto3 is never imported.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable, MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

SSM_PATH_ENV = "SSM_PARAMETER_PATH"


def _default_client() -> Any:
    import boto3

    return boto3.client("ssm")


def fetch_parameters(path: str, client: Any = None) -> dict[str, str]:
    """All parameters directly under `path`, decrypted, keyed by their last name segment."""
    client = client if client is not None else _default_client()
    prefix = "/" + path.strip("/")
    out: dict[str, str] = {}
    kwargs: dict[str, Any] = {"Path": prefix, "Recursive": False, "WithDecryption": True}
    while True:
        resp = client.get_parameters_by_path(**kwargs)
        for p in resp.get("Parameters", []):
            out[p["Name"].rsplit("/", 1)[-1]] = p["Value"]
        token = resp.get("NextToken")
        if not token:
            return out
        kwargs["NextToken"] = token


def load_parameters_into_env(
    allowed: Iterable[str],
    environ: MutableMapping[str, str] | None = None,
    client: Any = None,
) -> list[str]:
    """Copy SSM parameters into `environ` (default os.environ). Returns the names applied.

    A failure to read SSM propagates: a production cold start without its secrets must
    fail loudly rather than boot with defaults.
    """
    environ = os.environ if environ is None else environ
    path = environ.get(SSM_PATH_ENV, "").strip()
    if not path:
        return []
    allowed_set = set(allowed)
    params = fetch_parameters(path, client)
    applied: list[str] = []
    for name, value in params.items():
        if name not in allowed_set:
            logger.warning("SSM parameter %s under %s is not a setting; ignored", name, path)
            continue
        if name in environ:
            continue  # environment wins
        environ[name] = value
        applied.append(name)
    logger.info("Loaded %d setting(s) from SSM %s: %s", len(applied), path, ", ".join(sorted(applied)))
    return applied
