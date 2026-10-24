"""Core exception hierarchy. `api/errors.py` maps these to HTTP responses."""


class JutantError(Exception):
    """Base class for every core error."""


class PolicyDenied(JutantError):
    """The policy engine refused a tool call."""


class FeatureUnavailable(PolicyDenied):
    """A question clearly for a kind of help the caller may not use: staff are told whose it
    is, and nothing is looked up."""

    def __init__(self, feature_id: str, title: str, roles: tuple[str, ...], pack: str) -> None:
        super().__init__(f"{feature_id} is not available to the caller")
        self.feature_id, self.title, self.roles, self.pack = feature_id, title, roles, pack


class InvalidToolCall(JutantError):
    """A tool call is not permitted for the feature or fails its schema."""


class UnknownTool(JutantError):
    """A tool call names a tool that no MCP server exposes."""


class StepLimitExceeded(JutantError):
    """The tool loop exceeded `max_steps` model calls."""


class PackContractError(JutantError):
    """The loaded pack fails one or more contract checks."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("Pack contract failed:\n- " + "\n- ".join(violations))


class ModelUnavailable(JutantError):
    """The model provider could not be reached or timed out."""


class ActionUnavailable(JutantError):
    """A proposed action cannot be confirmed or cancelled: there is no such proposal for the
    caller (`not_found`), or it is no longer waiting (`expired`, `sending`, `sent`, `failed`,
    `cancelled`)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
