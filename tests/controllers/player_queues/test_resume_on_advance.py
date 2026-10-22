"""Tests that a queue advancing on its own resumes an audiobook at its saved position."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from music_assistant_models.enums import MediaType, PlaybackState, RepeatMode
from music_assistant_models.errors import InvalidDataError, ProviderUnavailableError
from music_assistant_models.media_items import Audiobook, ItemMapping, ProviderMapping, Track
from music_assistant_models.player_queue import PlayerQueue, PlayLogEntry
from music_assistant_models.queue_item import QueueItem, QueueItemOrigin

from music_assistant.controllers.player_queues.controller import PlayerQueuesController
from music_assistant.controllers.player_queues.helpers import CompareState
from music_assistant.controllers.player_queues.state import PlayerQueueData

QUEUE_ID = "queue-1"


def _mappings(item_id: str) -> set[ProviderMapping]:
    return {
        ProviderMapping(
            item_id=item_id,
            provider_domain="filesystem_local",
            provider_instance="filesystem_local--1",
        )
    }


def _book(item_id: str, resume_position_ms: int = 0) -> QueueItem:
    return QueueItem(
        queue_id=QUEUE_ID,
        queue_item_id=item_id,
        name=item_id,
        duration=120,
        media_item=Audiobook(
            item_id=item_id,
            provider="filesystem_local--1",
            name=item_id,
            duration=120,
            resume_position_ms=resume_position_ms,
            provider_mappings=_mappings(item_id),
        ),
    )


def _track(item_id: str) -> QueueItem:
    return QueueItem(
        queue_id=QUEUE_ID,
        queue_item_id=item_id,
        name=item_id,
        duration=120,
        media_item=Track(
            item_id=item_id,
            provider="filesystem_local--1",
            name=item_id,
            duration=120,
            provider_mappings=_mappings(item_id),
        ),
    )


def _controller(
    items: list[QueueItem], repeat_mode: RepeatMode = RepeatMode.OFF
) -> tuple[PlayerQueuesController, AsyncMock]:
    """Build a bare controller holding the given items, returning its stream details mock."""
    controller = PlayerQueuesController.__new__(PlayerQueuesController)
    controller.logger = MagicMock()
    controller._queue_data = {
        QUEUE_ID: PlayerQueueData(
            queue=PlayerQueue(
                queue_id=QUEUE_ID,
                active=True,
                display_name="Test queue",
                available=True,
                items=len(items),
                repeat_mode=repeat_mode,
            ),
            items=items,
        )
    }
    mass = MagicMock()
    mass.music.get_library_item_by_prov_id = AsyncMock(return_value=None)
    mass.music.get_item_by_uri = AsyncMock(
        side_effect=lambda uri: next(i.media_item for i in items if i.uri == uri)
    )
    get_stream_details = AsyncMock(return_value=MagicMock(duration=None))
    mass.streams.audio.get_stream_details = get_stream_details
    controller.mass = mass
    return controller, get_stream_details


def _report_played(
    controller: PlayerQueuesController,
    played: QueueItem,
    seconds_played: int,
    now: QueueItem,
    state_after: PlaybackState = PlaybackState.PLAYING,
) -> None:
    """Have the playback tracker report an item played up to a position, then moved on."""

    def state(item: QueueItem, elapsed: int) -> CompareState:
        return CompareState(
            queue_id=QUEUE_ID,
            state=PlaybackState.PLAYING,
            current_item_id=item.queue_item_id,
            next_item_id=None,
            current_item=item,
            elapsed_time=elapsed,
            last_playing_elapsed_time=elapsed,
            stream_title=None,
            codec_type=None,
            output_player_ids=None,
        )

    queue = controller._queue_data[QUEUE_ID].queue
    queue.state = state_after
    # the stream server records an item once its first chunk went out to the player
    controller.mark_item_served(QUEUE_ID, played.queue_item_id)
    new_state = state(now, 0)
    new_state["state"] = state_after
    if state_after != PlaybackState.PLAYING:
        new_state["last_playing_elapsed_time"] = seconds_played
    controller._handle_playback_progress_report(queue, state(played, seconds_played), new_state)


async def test_next_audiobook_starts_at_its_resume_point() -> None:
    """The next audiobook starts where it was left off, not at 0:00."""
    items = [_book("book-a"), _book("book-b", resume_position_ms=60000)]
    controller, get_stream_details = _controller(items)

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 59


async def test_repeated_audiobook_starts_from_the_beginning() -> None:
    """Repeat all wraps around to the start of the first audiobook, not its old bookmark."""
    items = [_book("book-a", resume_position_ms=60000), _book("book-b")]
    controller, get_stream_details = _controller(items, repeat_mode=RepeatMode.ALL)

    await controller.load_next_queue_item(QUEUE_ID, "book-b")

    assert get_stream_details.call_args.kwargs["seek_position"] == 0


async def test_repeated_single_audiobook_starts_from_the_beginning() -> None:
    """Repeat one plays the audiobook over from its start, not from its old bookmark."""
    items = [_book("book-a", resume_position_ms=60000), _book("book-b")]
    controller, get_stream_details = _controller(items, repeat_mode=RepeatMode.ONE)

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 0


@pytest.mark.parametrize("repeat_mode", [RepeatMode.ONE, RepeatMode.ALL])
async def test_flow_repeat_preserves_previous_playback_offset(repeat_mode: RepeatMode) -> None:
    """Buffered audio from the previous pass keeps its seek offset after repeat loading."""
    item = _book("book-a", resume_position_ms=60000)
    controller, get_stream_details = _controller([item], repeat_mode)
    item.streamdetails = MagicMock(seek_position=59)
    queue_data = controller._queue_data[QUEUE_ID]
    queue_data.queue.current_item = item
    queue_data.queue.current_index = 0
    queue_data.queue.flow_mode = True
    previous_entry = PlayLogEntry(item.queue_item_id, seconds_streamed=61, seek_position=59)
    queue_data.flow_mode_stream_log = [previous_entry]
    player = MagicMock()
    player.state = SimpleNamespace(corrected_elapsed_time=10, playback_state=PlaybackState.PLAYING)
    get_stream_details.return_value.seek_position = 0

    await controller.load_next_queue_item(QUEUE_ID, item.queue_item_id)
    queue_data.flow_mode_stream_log.append(PlayLogEntry(item.queue_item_id))

    assert get_stream_details.call_args.kwargs["seek_position"] == 0
    assert controller._get_flow_queue_stream_index(queue_data.queue, player) == (0, 69)
    player.state.corrected_elapsed_time = 66
    assert controller._get_flow_queue_stream_index(queue_data.queue, player) == (0, 5)


@pytest.mark.parametrize("repeat_mode", [RepeatMode.ONE, RepeatMode.ALL])
async def test_non_flow_repeat_preloads_and_enqueues(repeat_mode: RepeatMode) -> None:
    """Non-flow players need the repeated item enqueued to continue playback."""
    item = _book("book-a", resume_position_ms=60000)
    controller, get_stream_details = _controller([item], repeat_mode)
    queue = controller._queue_data[QUEUE_ID].queue
    queue.current_item = item
    queue.flow_mode = False
    item.streamdetails = MagicMock(seek_position=59)
    tasks: list[asyncio.Task[None]] = []
    cast("MagicMock", controller.mass).create_task.side_effect = lambda coro, **_kwargs: (
        tasks.append(asyncio.create_task(coro))
    )
    controller._enqueue_next_item = MagicMock()  # type: ignore[method-assign]

    controller._preload_next_item(QUEUE_ID, item.queue_item_id)
    await asyncio.gather(*tasks)

    get_stream_details.assert_awaited_once()
    assert get_stream_details.call_args.kwargs["seek_position"] == 0
    controller._enqueue_next_item.assert_called_once_with(QUEUE_ID, item)


@pytest.mark.parametrize("flow_mode", [False, True])
async def test_preload_next_audiobook_still_resumes_and_enqueues(flow_mode: bool) -> None:
    """A distinct upcoming audiobook is still prepared at its bookmark and enqueued."""
    items = [_book("book-a"), _book("book-b", resume_position_ms=60000)]
    controller, get_stream_details = _controller(items)
    controller._queue_data[QUEUE_ID].queue.current_item = items[0]
    controller._queue_data[QUEUE_ID].queue.flow_mode = flow_mode
    tasks: list[asyncio.Task[None]] = []
    cast("MagicMock", controller.mass).create_task.side_effect = lambda coro, **_kwargs: (
        tasks.append(asyncio.create_task(coro))
    )
    controller._enqueue_next_item = MagicMock()  # type: ignore[method-assign]

    controller._preload_next_item(QUEUE_ID, items[0].queue_item_id)
    await asyncio.gather(*tasks)

    assert get_stream_details.call_args.kwargs["seek_position"] == 59
    controller._enqueue_next_item.assert_called_once_with(QUEUE_ID, items[1])


async def test_audiobook_played_to_the_end_restarts_on_the_next_repeat_pass() -> None:
    """An audiobook finished during this queue starts at 0:00 on the next pass, not its bookmark."""
    items = [_book("book-a"), _book("book-b", resume_position_ms=60000)]
    controller, get_stream_details = _controller(items, repeat_mode=RepeatMode.ALL)
    _report_played(controller, items[1], seconds_played=118, now=items[0])

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 0


async def test_partly_played_audiobook_resumes_where_it_was_left_this_time() -> None:
    """An audiobook left part way during this queue resumes there, not at its enqueue bookmark."""
    items = [_book("book-a"), _book("book-b", resume_position_ms=10000)]
    controller, get_stream_details = _controller(items)
    _report_played(controller, items[1], seconds_played=40, now=items[0])

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 39


async def test_next_track_starts_from_the_beginning() -> None:
    """A music track that follows an audiobook plays from its start."""
    items = [_book("book-a", resume_position_ms=60000), _track("track-b")]
    controller, get_stream_details = _controller(items)

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 0


def _spoken_word(controller: PlayerQueuesController, item: QueueItem) -> MagicMock:
    """Opt a queue item into a library playlist's spoken-word behavior."""
    item.origin = QueueItemOrigin(
        container=ItemMapping(
            media_type=MediaType.PLAYLIST, item_id="42", provider="library", name="Up Next"
        ),
        provider_instance="filesystem_local--1",
        item_id=item.media_item.item_id if item.media_item else None,
    )
    mass = cast("MagicMock", controller.mass)
    mass.music.playlists.playback_settings.return_value = {
        "spoken_word": True,
        "remove_finished": True,
    }
    mass.music.get_resume_position = AsyncMock(return_value=(False, 2034000))
    mass.music.playlists.remove_finished_item = AsyncMock()
    return mass


async def test_playlist_resume_fetches_fresh_user_progress_without_rewind() -> None:
    """A reconstructed item with no resume fields starts at the current provider position."""
    item = _book("book-a")
    item.duration = 3600
    controller, _ = _controller([item])
    mass = _spoken_word(controller, item)
    controller._queue_data[QUEUE_ID].userid = "listener"

    assert await controller._get_resume_position(item) == 2034
    mass.music.get_resume_position.assert_awaited_once_with(
        item.media_item,
        userid="listener",
        pinned=("filesystem_local--1", "book-a"),
        prefer_provider=True,
    )
    mass.music.get_resume_position.return_value = (False, 900000)
    assert await controller._get_resume_position(item) == 900
    mass.music.get_resume_position.return_value = (False, 0)
    assert await controller._get_resume_position(item) == 0


async def test_playlist_advancement_fetches_next_items_progress() -> None:
    """Later playlist items use fresh progress too, not the enqueue-time bookmark."""
    items = [_book("book-a"), _book("book-b", resume_position_ms=10000)]
    controller, get_stream_details = _controller(items)
    mass = _spoken_word(controller, items[1])
    mass.music.get_resume_position.return_value = (False, 60000)

    await controller.load_next_queue_item(QUEUE_ID, "book-a")

    assert get_stream_details.call_args.kwargs["seek_position"] == 60


async def test_spoken_word_start_from_beginning_does_not_fetch_progress() -> None:
    """The explicit restart action overrides provider progress."""
    item = _book("book-a", resume_position_ms=60000)
    controller, _ = _controller([item])
    mass = _spoken_word(controller, item)
    item.extra_attributes["start_from_beginning"] = True

    assert await controller._get_resume_position(item) == 0
    mass.music.get_resume_position.assert_not_awaited()


async def test_completed_spoken_word_item_replays_from_zero() -> None:
    """A completed episode/book is replayed instead of seeking to its end."""
    item = _book("book-a")
    controller, _ = _controller([item])
    mass = _spoken_word(controller, item)
    mass.music.get_resume_position.return_value = (True, 120000)

    assert await controller._get_resume_position(item) == 0


async def test_unknown_duration_does_not_silently_restart_spoken_word() -> None:
    """A saved position with no usable duration is an explicit error, not a zero start."""
    item = _book("book-a")
    item.duration = 0
    assert item.media_item is not None
    item.media_item.duration = 0
    controller, _ = _controller([item])
    _spoken_word(controller, item)
    controller._restore_probed_duration = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(InvalidDataError, match="duration is unknown"):
        await controller._get_resume_position(item)


async def test_probed_duration_allows_spoken_word_resume() -> None:
    """Previously probed duration makes a missing-duration playlist item seekable."""
    item = _book("book-a")
    item.duration = 0
    assert item.media_item is not None
    item.media_item.duration = 0
    controller, _ = _controller([item])
    _spoken_word(controller, item)

    async def restore(queue_item: QueueItem) -> None:
        queue_item.duration = 3600

    controller._restore_probed_duration = AsyncMock(side_effect=restore)  # type: ignore[method-assign]
    assert await controller._get_resume_position(item) == 2034


async def test_spoken_word_provider_errors_do_not_restart_at_zero() -> None:
    """An unavailable progress source must not look like verified zero progress."""
    item = _book("book-a")
    controller, _ = _controller([item])
    mass = _spoken_word(controller, item)
    mass.music.get_resume_position.side_effect = ProviderUnavailableError("offline")

    with pytest.raises(ProviderUnavailableError, match="offline"):
        await controller._get_resume_position(item)


@pytest.mark.parametrize("seconds", [30, 61, 110, 114, 118, 120])
@pytest.mark.parametrize("interrupted", [False, True])
async def test_only_natural_end_removes_source_playlist_item(
    seconds: int, interrupted: bool
) -> None:
    """The 60-second completion threshold and explicit interruptions never delete an item."""
    items = [_book("book-a"), _book("book-b")]
    controller, _ = _controller(items)
    mass = _spoken_word(controller, items[0])
    data = controller._queue_data[QUEUE_ID]
    if interrupted:
        data.interrupted_item_ids.add(items[0].queue_item_id)
    tasks: list[asyncio.Task[None]] = []
    mass.create_task.side_effect = lambda coro, **_kwargs: (
        tasks.append(asyncio.create_task(coro)) if asyncio.iscoroutine(coro) else None
    )

    _report_played(controller, items[0], seconds_played=seconds, now=items[1])
    _report_played(controller, items[0], seconds_played=seconds, now=items[1])
    await asyncio.gather(*tasks)

    if seconds >= 115 and not interrupted:
        mass.music.playlists.remove_finished_item.assert_awaited_once_with("42", items[0].uri, None)
    else:
        mass.music.playlists.remove_finished_item.assert_not_awaited()


@pytest.mark.parametrize("state_after", [PlaybackState.PLAYING, PlaybackState.IDLE])
@pytest.mark.parametrize("interrupted_after_seek", [False, True])
async def test_seeking_then_finishing_removes_source_playlist_item(
    state_after: PlaybackState, interrupted_after_seek: bool
) -> None:
    """Seeking within an episode must not prevent its later natural-end removal."""
    items = [_book("book-a"), _book("book-b")]
    controller, _ = _controller(items)
    mass = _spoken_word(controller, items[0])
    queue = controller._queue_data[QUEUE_ID].queue
    queue.current_index = 0
    queue.current_item = items[0]
    queue.state = PlaybackState.PLAYING
    controller._check_player_permission = MagicMock()  # type: ignore[method-assign]
    controller._set_transitioning = MagicMock()  # type: ignore[method-assign]
    controller.signal_update = MagicMock()  # type: ignore[method-assign]
    controller._load_item = AsyncMock()  # type: ignore[method-assign]
    controller.player_media_from_queue_item = AsyncMock()  # type: ignore[method-assign]
    mass.music.get_playback_speed = AsyncMock(return_value=1.0)
    mass.players.play_media = AsyncMock()
    tasks: list[asyncio.Task[None]] = []
    mass.create_task.side_effect = lambda coro, **_kwargs: (
        tasks.append(asyncio.create_task(coro)) if asyncio.iscoroutine(coro) else None
    )

    await controller.seek(QUEUE_ID, 110)
    if interrupted_after_seek:
        controller._queue_data[QUEUE_ID].interrupted_item_ids.add(items[0].queue_item_id)
    _report_played(
        controller,
        items[0],
        seconds_played=118,
        now=items[1] if state_after == PlaybackState.PLAYING else items[0],
        state_after=state_after,
    )
    await asyncio.gather(*tasks)

    if interrupted_after_seek:
        mass.music.playlists.remove_finished_item.assert_not_awaited()
    else:
        mass.music.playlists.remove_finished_item.assert_awaited_once_with("42", items[0].uri, None)
