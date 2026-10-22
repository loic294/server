"""Listener isolation for the playlist fork in the official Home Assistant DEV app."""

from dataclasses import dataclass
from typing import Any

from music_assistant.constants import SENDSPIN_SERVER_PORT


@dataclass(frozen=True)
class NetworkProfile:
    """Optional fixed web/stream ports and the matching internal Sendspin listener."""

    web_port: int | None = None
    stream_port: int | None = None
    sendspin_port: int = SENDSPIN_SERVER_PORT
    ingress_enabled: bool = True


DEFAULT_NETWORK_PROFILE = NetworkProfile()
PLAYLIST_TEST_NETWORK_PROFILE = NetworkProfile(
    web_port=8195, stream_port=8197, sendspin_port=9027, ingress_enabled=False
)


def network_profile_for_options(options: dict[str, Any]) -> NetworkProfile:
    """Select isolation only for the explicitly configured playlist DEV source branch."""
    if options.get("server_repo") == "loic294/server@playlist-playback-test":
        return PLAYLIST_TEST_NETWORK_PROFILE
    return DEFAULT_NETWORK_PROFILE
