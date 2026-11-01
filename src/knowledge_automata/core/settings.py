"""Reading settings from the environment, shared by the agents."""

from collections.abc import Mapping


def whole_number(
    env: Mapping[str, str], name: str, default: int, error_type: type[Exception]
) -> int:
    """Read a whole number of at least 1; unset or empty is ``default``.

    Raises ``error_type`` naming the variable for any other value.
    """
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise error_type(f"{name} must be a whole number of at least 1, got {raw!r}")
    return value
