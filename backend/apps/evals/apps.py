from django.apps import AppConfig


class EvalsConfig(AppConfig):
    """Holds the `run_evals` command only; it has no models."""

    name = "apps.evals"
    label = "evals"
