"""Tests for opt-in playlist playback settings, permissions and completed identities."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from music_assistant_models.access import PlaylistAccess
from music_assistant_models.auth import User, UserRole
from music_assistant_models.enums import ProviderSharing
from music_assistant_models.errors import (
    InsufficientPermissions,
    InvalidDataError,
    MediaNotFoundError,
)
from music_assistant_models.media_items import Playlist, ProviderMapping

if TYPE_CHECKING:
    from music_assistant.controllers.music.media.playlists import PlaylistController
    from music_assistant.mass import MusicAssistant

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest.fixture
async def playlist(
    music_mass_module: MusicAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PlaylistController, Playlist]:
    """Create a real persisted playlist with an owner."""
    controller = music_mass_module.music.playlists
    monkeypatch.setattr(
        music_mass_module.webserver.auth,
        "get_user",
        AsyncMock(return_value=User(user_id="owner", username="owner", role=UserRole.USER)),
    )
    monkeypatch.setattr(music_mass_module.cache, "delete", AsyncMock())
    item_id = uuid4().hex
    item = await controller.add_item_to_library(
        Playlist(
            item_id=item_id,
            provider="builtin",
            name="Up Next",
            provider_mappings={
                ProviderMapping(
                    item_id=item_id, provider_domain="builtin", provider_instance="builtin"
                )
            },
            is_editable=True,
            access=PlaylistAccess(owner="owner"),
        )
    )
    return controller, item


async def test_old_playlist_defaults_are_opt_out(
    playlist: tuple[PlaylistController, Playlist],
) -> None:
    """No new stored fields are needed to preserve existing playlist behavior."""
    controller, item = playlist
    assert await controller.get_playback_settings(item.item_id) == {
        "spoken_word": False,
        "remove_finished": False,
        "show_remaining_time": False,
    }


async def test_settings_survive_metadata_refresh_and_toggle(
    playlist: tuple[PlaylistController, Playlist],
) -> None:
    """Provider metadata updates cannot erase independently stored preferences."""
    controller, item = playlist
    expected = {"spoken_word": True, "remove_finished": True, "show_remaining_time": True}
    assert await controller.set_playback_settings(item.item_id, **expected) == expected
    item.metadata.description = "Updated by the provider"
    await controller.update_item_in_library(item.item_id, item, overwrite=True)
    assert await controller.get_playback_settings(item.item_id) == expected
    await controller.set_playback_settings(item.item_id, False, False)
    assert not controller.playback_settings(item.item_id)["spoken_word"]
    assert controller.playback_settings(item.item_id)["show_remaining_time"]


async def test_remaining_time_is_independent_and_can_be_disabled(
    playlist: tuple[PlaylistController, Playlist],
) -> None:
    """Display preferences persist independently of resume and removal."""
    controller, item = playlist
    settings = await controller.set_playback_settings(
        item.item_id, False, False, show_remaining_time=True
    )
    assert settings == {
        "spoken_word": False,
        "remove_finished": False,
        "show_remaining_time": True,
    }
    await controller.set_playback_settings(item.item_id, True, True)
    assert (await controller.get_playback_settings(item.item_id))["show_remaining_time"]
    await controller.set_playback_settings(item.item_id, True, True, show_remaining_time=False)
    assert not (await controller.get_playback_settings(item.item_id))["show_remaining_time"]


@pytest.mark.parametrize(
    ("sharing", "error"),
    [
        (ProviderSharing.PRIVATE, MediaNotFoundError),
        (ProviderSharing.EVERYONE, InsufficientPermissions),
    ],
)
async def test_non_owner_cannot_change_playback_settings(
    playlist: tuple[PlaylistController, Playlist],
    sharing: ProviderSharing,
    error: type[Exception],
) -> None:
    """Library write scope does not grant permission to change somebody else's preferences."""
    controller, item = playlist
    await controller.set_access(item.item_id, sharing=sharing, owner="owner")
    with (
        patch(
            "music_assistant.controllers.music.media.playlists.get_current_user",
            return_value=User(user_id="other", username="other", role=UserRole.USER),
        ),
        pytest.raises(error),
    ):
        await controller.set_playback_settings(item.item_id, True, True)


@pytest.mark.parametrize(
    ("editable", "dynamic", "spoken_word"),
    [(False, False, True), (True, True, True), (True, False, False)],
)
async def test_invalid_removal_settings_are_rejected(
    playlist: tuple[PlaylistController, Playlist],
    editable: bool,
    dynamic: bool,
    spoken_word: bool,
) -> None:
    """Auto-removal requires an editable, finite spoken-word playlist."""
    controller, item = playlist
    item.is_editable, item.is_dynamic = editable, dynamic
    with (
        patch.object(controller, "get_library_item", AsyncMock(return_value=item)),
        pytest.raises(InvalidDataError),
    ):
        await controller.set_playback_settings(item.item_id, spoken_word, True)


async def test_completed_removal_resolves_current_position_and_records_identity(
    playlist: tuple[PlaylistController, Playlist],
) -> None:
    """A moved item is removed at its current position, not its original queued index."""
    controller, item = playlist
    await controller.set_playback_settings(item.item_id, True, True)
    episode = MagicMock(uri="pocketcasts://podcast_episode/show:episode", position=7)
    with (
        patch.object(controller, "tracks", AsyncMock(return_value=[episode])),
        patch.object(controller, "_handle_remove_playlist_tracks", AsyncMock()) as remove,
        patch.object(controller, "_task_user", AsyncMock(return_value=None)),
    ):
        await controller.remove_finished_item(item.item_id, episode.uri, None)
        remove.assert_awaited_once_with(item.item_id, (7,), None)
    assert await controller.completed_items(item.item_id) == [episode.uri]


async def test_removal_failure_is_not_recorded_as_success(
    playlist: tuple[PlaylistController, Playlist],
) -> None:
    """A provider removal failure is surfaced and does not claim a removed item."""
    controller, item = playlist
    await controller.set_playback_settings(item.item_id, True, True)
    episode = MagicMock(uri="pocketcasts://podcast_episode/show:episode", position=1)
    with (
        patch.object(controller, "tracks", AsyncMock(return_value=[episode])),
        patch.object(
            controller,
            "_handle_remove_playlist_tracks",
            AsyncMock(side_effect=InvalidDataError("failed")),
        ),
        patch.object(controller, "_task_user", AsyncMock(return_value=None)),
        pytest.raises(InvalidDataError, match="failed"),
    ):
        await controller.remove_finished_item(item.item_id, episode.uri, None)
    assert await controller.completed_items(item.item_id) == []
