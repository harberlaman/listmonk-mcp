"""instance-administration: secrets in a v6.2.0-shaped settings document are masked by key name."""

import copy
import json
from typing import Any

from listmonk_mcp.masking import MASK, mask_settings

CLEAR = "clear-text-secret"


def settings() -> dict[str, Any]:
    """Field names and nesting from knadh/listmonk v6.2.0 models/settings.go."""
    return {
        "app.root_url": "https://lists.example.com",
        "smtp": [
            {"name": "relay", "host": "smtp.example.com", "port": 587, "username": "relay-user",
             "password": CLEAR, "auth_protocol": "login"},
            {"name": "backup", "host": "smtp2.example.com", "port": 25, "username": "u2",
             "password": "•" * 12},
            {"name": "short", "host": "smtp3.example.com", "port": 25, "username": "u3",
             "password": "•" * 4},
        ],
        "messengers": [{"name": "sms", "root_url": "https://sms.example.com", "username": "m", "password": CLEAR}],
        "bounce.mailboxes": [{"host": "imap.example.com", "username": "bounces", "password": CLEAR}],
        "upload.s3.aws_access_key_id": "AKIAEXAMPLEID",
        "upload.s3.aws_secret_access_key": "",
        "bounce.sendgrid_key": CLEAR,
        "bounce.azure": {"enabled": True, "shared_secret": CLEAR, "shared_secret_header": "X-Azure-Secret"},
        "bounce.postmark": {"enabled": True, "username": "pm", "password": CLEAR},
        "bounce.forwardemail": {"enabled": True, "key": CLEAR},
        "bounce.lettermint": {"enabled": False, "key": CLEAR},
        "security.captcha": {
            "altcha": {"enabled": False, "complexity": 300000},
            "hcaptcha": {"enabled": True, "key": "site-key-public", "secret": CLEAR},
        },
        "security.oidc": {"enabled": True, "client_id": "listmonk-client", "client_secret": CLEAR},
    }


def test_clear_text_secrets_are_masked_everywhere() -> None:
    masked = mask_settings(settings())

    assert CLEAR not in json.dumps(masked)
    assert masked["smtp"][0]["password"] == MASK
    assert masked["messengers"][0]["password"] == MASK
    assert masked["bounce.mailboxes"][0]["password"] == MASK
    assert masked["bounce.azure"]["shared_secret"] == MASK
    assert masked["bounce.postmark"]["password"] == MASK
    assert masked["security.captcha"]["hcaptcha"]["secret"] == MASK
    assert masked["security.oidc"]["client_secret"] == MASK


def test_bullet_masks_of_any_length_become_the_fixed_mask() -> None:
    masked = mask_settings(settings())

    assert masked["smtp"][1]["password"] == MASK
    assert masked["smtp"][2]["password"] == MASK


def test_empty_secret_stays_empty() -> None:
    assert mask_settings(settings())["upload.s3.aws_secret_access_key"] == ""


def test_keys_that_are_not_secrets_stay_visible() -> None:
    masked = mask_settings(settings())

    assert masked["upload.s3.aws_access_key_id"] == "AKIAEXAMPLEID"
    assert masked["security.captcha"]["hcaptcha"]["key"] == "site-key-public"
    assert masked["security.oidc"]["client_id"] == "listmonk-client"
    assert masked["smtp"][0]["host"] == "smtp.example.com"
    assert masked["smtp"][0]["username"] == "relay-user"
    assert masked["smtp"][0]["port"] == 587
    assert masked["security.captcha"]["altcha"] == {"enabled": False, "complexity": 300000}


def test_explicit_key_fields_are_masked() -> None:
    masked = mask_settings(settings())

    assert masked["bounce.sendgrid_key"] == MASK
    assert masked["bounce.forwardemail"]["key"] == MASK
    assert masked["bounce.lettermint"]["key"] == MASK


def test_input_is_not_mutated() -> None:
    original = settings()
    snapshot = copy.deepcopy(original)

    mask_settings(original)

    assert original == snapshot
