"""Core exception hierarchy. `api/errors.py` maps these to HTTP responses."""


class JutantError(Exception):
    """Base class for every core error."""


class PolicyDenied(JutantError):
    """The policy engine refused a tool call."""


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
