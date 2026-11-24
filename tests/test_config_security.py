"""Target allowlisting, redaction, profile caps, and load shape."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from perfkit.config.loader import ProfileError, load_profile_file, profile_from_mapping, resolve_profile_name
from perfkit.config.models import TestProfile
from perfkit.datafactory import TemplateError, render_value
from perfkit.engine.plan import resolve_stages, stage_total_seconds, weighted_names
from perfkit.engine.runner import build_command
from perfkit.security import TargetRejected, mask_headers, redact, scrub_text, validate_base_url
from perfkit.settings import Settings


def _profile(**overrides: object) -> dict:
    payload = {
        "name": "unit",
        "test_type": "load",
        "base_url": "http://127.0.0.1:8090",
        "users": 2,
        "spawn_rate": 1,
        "duration_seconds": 8,
        "endpoints": [{"name": "health", "method": "GET", "path": "/health"}],
    }
    payload.update(overrides)
    return payload


def test_loopback_urls_are_normalized() -> None:
    allowed = frozenset({"localhost", "127.0.0.1"})
    assert validate_base_url("http://127.0.0.1:8090", allowed) == "http://127.0.0.1:8090"
    assert validate_base_url("http://localhost:8090/base/", allowed) == "http://localhost:8090/base"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://1.2.3.4",
        "http://169.254.169.254",
        "http://user:pass@127.0.0.1",
        "file:///tmp/x",
        "http://metadata.google.internal",
        "http://127.0.0.1:8090/health?x=1",
    ],
)
def test_external_and_credentialed_urls_are_rejected(url: str) -> None:
    with pytest.raises(TargetRejected):
        validate_base_url(url, frozenset({"localhost", "127.0.0.1", "demo-api"}))


def test_headers_are_masked_and_profile_secrets_redacted() -> None:
    masked = mask_headers({"Authorization": "Bearer secret-token", "Accept": "application/json"})
    assert masked["Authorization"] == "***"
    assert masked["Accept"] == "application/json"
    cleaned = redact({"auth": {"password": "demo-local-only", "username": "demo"}, "name": "x"})
    assert cleaned["auth"]["password"] == "***"
    assert cleaned["auth"]["username"] == "demo"
    scrubbed = scrub_text("password=demo-local-only Authorization: Bearer abc", ["demo-local-only"])
    assert "demo-local-only" not in scrubbed
    assert "Bearer abc" not in scrubbed


def test_invalid_profiles() -> None:
    with pytest.raises(ValidationError):
        TestProfile.model_validate(_profile(users=0))
    with pytest.raises(ValidationError):
        TestProfile.model_validate(
            _profile(endpoints=[{"name": "bad", "method": "GET", "path": "http://evil"}])
        )
    with pytest.raises(ValidationError):
        TestProfile.model_validate(
            _profile(
                endpoints=[
                    {
                        "name": "bad",
                        "method": "GET",
                        "path": "/health",
                        "headers": {"X-Test": "a\nb"},
                    }
                ]
            )
        )
    with pytest.raises(ValidationError):
        TestProfile.model_validate(
            _profile(
                test_type="endpoint",
                endpoints=[
                    {"name": "one", "method": "GET", "path": "/health"},
                    {"name": "two", "method": "GET", "path": "/users"},
                ],
            )
        )
    with pytest.raises(ValidationError):
        TestProfile.model_validate(_profile(test_type="baseline", users=3))


def test_caps_and_traversal(settings: Settings) -> None:
    with pytest.raises(ProfileError):
        profile_from_mapping(_profile(users=100), settings)
    with pytest.raises(ProfileError):
        profile_from_mapping(_profile(base_url="http://example.com"), settings)
    with pytest.raises(ProfileError):
        resolve_profile_name("../secrets.yaml", settings)
    with pytest.raises(ProfileError):
        resolve_profile_name("missing.yaml", settings)


def test_bundled_profiles_validate(settings: Settings) -> None:
    for path in sorted(settings.profiles_dir.glob("*.yaml")):
        profile = load_profile_file(path, settings)
        assert profile.base_url.startswith("http://127.0.0.1")
        stages = resolve_stages(profile)
        assert stage_total_seconds(stages) <= profile.duration_seconds
        assert max(stage.users for stage in stages) <= settings.max_users


def test_shapes_cover_each_test_type() -> None:
    stress = TestProfile.model_validate(_profile(test_type="stress", users=8, duration_seconds=12))
    levels = [stage.users for stage in resolve_stages(stress)]
    assert levels == [2, 4, 6, 8]
    spike = TestProfile.model_validate(_profile(test_type="spike", users=10, duration_seconds=9))
    assert [stage.users for stage in resolve_stages(spike)] == [2, 10, 2]
    baseline = TestProfile.model_validate(_profile(test_type="baseline", users=1, duration_seconds=8))
    assert resolve_stages(baseline)[0].users == 1
    assert weighted_names(
        [{"name": "a", "weight": 3}, {"name": "b", "weight": 1}]
    ) == ["a", "a", "a", "b"]


def test_templates_do_not_execute_code() -> None:
    import itertools
    import random

    rng = random.Random(1)
    seq = itertools.count(1)
    assert render_value("{{int:2,2}}", rng, seq) == 2
    assert render_value("id-{{choice:a,b}}", random.Random(0), seq) in {"id-a", "id-b"}
    assert render_value("n-{{seq}}", rng, seq) == "n-1"
    with pytest.raises(TemplateError):
        render_value("{{os.system('id')}}", rng, seq)


def test_locust_command_is_an_argument_vector() -> None:
    command = build_command(3, 1.5, 20, "http://127.0.0.1:8090")
    assert isinstance(command, list)
    assert command[1:3] == ["-m", "locust"]
    assert "--headless" in command
    assert "&&" not in " ".join(command)
    assert command[command.index("--host") + 1] == "http://127.0.0.1:8090"
    with pytest.raises(ValueError):
        build_command(0, 1, 10, "http://127.0.0.1")
