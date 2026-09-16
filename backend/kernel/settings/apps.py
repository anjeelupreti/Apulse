from typing import Any

from django.apps import AppConfig


class SettingsConfig(AppConfig):
    name = "kernel.settings"
    label = "settings"
    verbose_name = "Settings"

    def ready(self) -> Any:
        from kernel.audit.tracking import track

        from .models import SettingValue
        from .registry import autodiscover

        # Declared settings are collected the same way permissions are: importing each app's
        # settings_spec.py, so declaring one is all it takes to register it.
        autodiscover()

        # Every change to a value leaves an entry. The services record a SETTINGS_CHANGE of their
        # own with the reason on it; this catches anything that writes a row another way.
        track(SettingValue)
