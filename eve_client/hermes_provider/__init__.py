"""Hermes-native Eve memory provider registration entry point."""

from typing import Any


def register(ctx: Any) -> None:
    from eve_client.hermes_provider.provider import register as register_provider

    return register_provider(ctx)


__all__ = ["register"]
