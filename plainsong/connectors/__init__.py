"""Connectors: ways of getting notation and audio in and out of other systems."""

from .base import Connector, ConnectorResult, discover, registry

__all__ = ["Connector", "ConnectorResult", "discover", "registry"]
