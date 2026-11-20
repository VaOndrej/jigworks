from hypothesis import HealthCheck, settings

# Deterministic property tests: the same examples every run, so a red run in the gate is
# reproducible and break-invariant.sh catches its bugs every time. No example database on
# disk (keeps worktrees clean).
settings.register_profile(
    "jigworks",
    derandomize=True,
    database=None,
    deadline=None,
    max_examples=300,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("jigworks")
