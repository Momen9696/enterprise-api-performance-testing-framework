"""Turn a profile into a concrete load shape. Pure functions, no Locust import."""

from __future__ import annotations

from perfkit.config.models import StageConfig, TestProfile


def resolve_stages(profile: TestProfile) -> list[StageConfig]:
    """Build the user shape for the declared test type.

    Explicit ``stages`` on the profile win. Otherwise:

    - stress steps through 25/50/75/100 percent of users
    - spike holds a low base, jumps to the peak, then returns
    - baseline forces a single user
    - load, soak, concurrent, and endpoint hold a flat user count
    """
    if profile.stages:
        return list(profile.stages)

    duration = profile.duration_seconds
    users = profile.users
    rate = profile.spawn_rate

    if profile.test_type == "baseline":
        return [StageConfig(duration_seconds=duration, users=1, spawn_rate=1)]

    if profile.test_type == "stress":
        step = max(1, duration // 4)
        durations = [step, step, step, max(1, duration - 3 * step)]
        # If integer division made the plan longer than the cap, shrink the tail.
        overflow = sum(durations) - duration
        if overflow > 0:
            durations[-1] = max(1, durations[-1] - overflow)
        levels = [max(1, round(users * fraction)) for fraction in (0.25, 0.5, 0.75, 1.0)]
        levels = [min(level, users) for level in levels]
        return [
            StageConfig(duration_seconds=durations[index], users=levels[index], spawn_rate=rate)
            for index in range(4)
        ]

    if profile.test_type == "spike":
        base = max(1, users // 5)
        first = max(1, duration // 3)
        second = max(1, duration // 3)
        third = max(1, duration - first - second)
        return [
            StageConfig(duration_seconds=first, users=base, spawn_rate=rate),
            StageConfig(duration_seconds=second, users=users, spawn_rate=max(rate, float(users))),
            StageConfig(duration_seconds=third, users=base, spawn_rate=rate),
        ]

    return [StageConfig(duration_seconds=duration, users=users, spawn_rate=rate)]


def weighted_names(endpoints: list[dict]) -> list[str]:
    """Expand endpoint weights into a flat list of names. Locust samples this list."""
    names: list[str] = []
    for endpoint in endpoints:
        weight = int(endpoint.get("weight", 1))
        if weight < 1:
            raise ValueError("endpoint weight must be positive")
        names.extend([str(endpoint["name"])] * weight)
    return names


def stage_peak(stages: list[StageConfig]) -> int:
    return max(stage.users for stage in stages)


def stage_total_seconds(stages: list[StageConfig]) -> int:
    return sum(stage.duration_seconds for stage in stages)
