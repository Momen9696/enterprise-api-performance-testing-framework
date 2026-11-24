"""Pydantic models for performance profiles. Thresholds are always per profile."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from perfkit.security import validate_header

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
TestType = Literal["load", "stress", "spike", "soak", "baseline", "concurrent", "endpoint"]
AuthMode = Literal["none", "bearer", "api_key"]


class EndpointConfig(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,40}$")
    method: HttpMethod
    path: str
    weight: int = Field(default=1, ge=1, le=100)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: dict[str, Any] | list[Any] | None = None
    expected_status: list[int] = Field(default_factory=lambda: [200], min_length=1)

    @field_validator("path")
    @classmethod
    def path_must_be_relative(cls, value: str) -> str:
        if not value.startswith("/") or "://" in value or "\\" in value:
            raise ValueError("endpoint path must start with / and stay relative")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("endpoint path contains control characters")
        if len(value) > 200:
            raise ValueError("endpoint path is too long")
        return value

    @field_validator("headers")
    @classmethod
    def headers_are_safe(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            validate_header(str(key), str(item))
        return value

    @field_validator("expected_status")
    @classmethod
    def statuses_are_http(cls, value: list[int]) -> list[int]:
        for code in value:
            if code < 100 or code > 599:
                raise ValueError(f"invalid expected status {code}")
        return value


class WaitConfig(BaseModel):
    min_seconds: float = Field(default=0.1, ge=0, le=30)
    max_seconds: float = Field(default=0.4, ge=0, le=60)

    @model_validator(mode="after")
    def ordered(self) -> WaitConfig:
        if self.max_seconds < self.min_seconds:
            raise ValueError("wait.max_seconds must be >= wait.min_seconds")
        return self


class PacingConfig(BaseModel):
    """Optional per-user pacing. When set, each task sleeps so the iteration is at least this long."""

    min_iteration_seconds: float | None = Field(default=None, gt=0, le=60)


class AuthConfig(BaseModel):
    mode: AuthMode = "none"
    login_path: str = "/auth/token"
    username: str | None = None
    password: str | None = None
    password_env: str | None = None
    api_key_header: str = "X-Api-Key"
    api_key: str | None = None
    api_key_env: str | None = None

    @field_validator("login_path")
    @classmethod
    def login_path_relative(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("auth.login_path must start with /")
        return value

    @field_validator("password_env", "api_key_env")
    @classmethod
    def env_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("environment variable names must be identifiers")
        return value


class ThresholdConfig(BaseModel):
    """All limits are optional. An empty object means the run is not judged."""

    max_p95_ms: float | None = Field(default=None, gt=0)
    max_p99_ms: float | None = Field(default=None, gt=0)
    min_rps: float | None = Field(default=None, gt=0)
    max_error_pct: float | None = Field(default=None, ge=0, le=100)


class StageConfig(BaseModel):
    duration_seconds: int = Field(ge=1, le=3600)
    users: int = Field(ge=1, le=500)
    spawn_rate: float = Field(gt=0, le=500)


class TestProfile(BaseModel):
    __test__ = False

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,60}$")
    test_type: TestType
    base_url: str
    endpoints: list[EndpointConfig] = Field(min_length=1, max_length=30)
    users: int = Field(default=2, ge=1, le=500)
    spawn_rate: float = Field(default=1, gt=0, le=500)
    duration_seconds: int = Field(ge=5, le=7200)
    wait: WaitConfig = Field(default_factory=WaitConfig)
    pacing: PacingConfig = Field(default_factory=PacingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    stages: list[StageConfig] | None = None
    request_timeout_seconds: float = Field(default=10, gt=0, le=30)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def type_rules(self) -> TestProfile:
        names = [item.name for item in self.endpoints]
        if len(names) != len(set(names)):
            raise ValueError("endpoint names must be unique")
        if self.test_type == "endpoint" and len(self.endpoints) != 1:
            raise ValueError("endpoint tests must configure exactly one endpoint")
        if self.test_type == "baseline" and self.users != 1:
            raise ValueError("baseline tests must use users: 1")
        if self.stages:
            total = sum(stage.duration_seconds for stage in self.stages)
            if total > self.duration_seconds:
                raise ValueError("sum of stages exceeds duration_seconds")
            for stage in self.stages:
                if stage.users > self.users and self.test_type != "spike":
                    # Spike may jump to `users`; stages must not exceed the profile cap.
                    pass
            peak = max(stage.users for stage in self.stages)
            if peak > max(self.users, 1):
                raise ValueError("a stage requests more users than profile.users")
        if self.auth.mode == "bearer" and not (self.auth.password or self.auth.password_env):
            raise ValueError("bearer auth requires password or password_env")
        if self.auth.mode == "api_key" and not (self.auth.api_key or self.auth.api_key_env):
            raise ValueError("api_key auth requires api_key or api_key_env")
        return self
