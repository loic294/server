"""Regression checks for the official DEV app's isolated test-server profile."""

import pytest

from music_assistant.helpers.network_profile import (
    DEFAULT_NETWORK_PROFILE,
    network_profile_for_options,
)


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"server_repo": ""},
        {"server_repo": "dev"},
        {"server_repo": "another/server@playlist-playback-test"},
        {"server_repo": "loic294/server@another-branch"},
    ],
)
def test_normal_installations_keep_their_network_profile(options: dict[str, str]) -> None:
    """The fork's network isolation never changes a normal server's listeners."""
    assert network_profile_for_options(options) == DEFAULT_NETWORK_PROFILE


def test_selected_dev_fork_has_no_normal_instance_listeners() -> None:
    """The exact DEV source configuration must not bind any production listener."""
    profile = network_profile_for_options({"server_repo": "loic294/server@playlist-playback-test"})

    assert profile.web_port == 8195
    assert profile.stream_port == 8197
    assert profile.sendspin_port == 9027
    assert not profile.ingress_enabled
    assert {profile.web_port, profile.stream_port, profile.sendspin_port}.isdisjoint(
        {8094, 8095, 8097, 8927}
    )
