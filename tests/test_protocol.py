"""Tests for the Teranex protocol parser, independent of Home Assistant."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import pytest

from custom_components.blackmagic_teranex import protocol
from custom_components.blackmagic_teranex.protocol import (
    TeranexClient,
    TeranexConnectionError,
    TeranexInvalidValueError,
)

DUMP = """PROTOCOL PREAMBLE:
Version: 1.13

TERANEX DEVICE:
Model name: Teranex 2D
Software Version: 0x00000001

ANCILLARY DATA:
Timecode generate value: 00:00:00;00

VIDEO OUTPUT:
Video mode: 1080p24
Aspect ratio: Anamorphic

"""


def _feed(client: TeranexClient, text: str) -> None:
    for line in text.split("\n"):
        client._handle_line(line)


async def test_dump_is_parsed_into_blocks() -> None:
    """Blocks and values arrive exactly as the unit spells them."""
    client = TeranexClient("unit")
    _feed(client, DUMP)

    assert client.model == "Teranex 2D"
    assert client.get("VIDEO OUTPUT", "Video mode") == "1080p24"
    # Only the first colon separates key and value.
    assert client.get("ANCILLARY DATA", "Timecode generate value") == "00:00:00;00"
    assert client.get("VIDEO OUTPUT", "Missing") is None


async def test_partial_update_is_merged() -> None:
    """A status update carries only what changed and keeps the rest."""
    client = TeranexClient("unit")
    _feed(client, DUMP)
    _feed(client, "VIDEO OUTPUT:\nAspect ratio: CentreCut\n\n")

    assert client.get("VIDEO OUTPUT", "Aspect ratio") == "CentreCut"
    assert client.get("VIDEO OUTPUT", "Video mode") == "1080p24"


async def test_listeners_fire_per_block() -> None:
    """Every completed block notifies the listeners once."""
    client = TeranexClient("unit")
    calls: list[int] = []
    remove = client.add_listener(lambda: calls.append(1))

    _feed(client, DUMP)
    assert len(calls) == 4

    remove()
    _feed(client, "VIDEO OUTPUT:\nAspect ratio: Letterbox\n\n")
    assert len(calls) == 4


async def test_ack_and_nack_resolve_waiters_in_order() -> None:
    """Replies are matched to commands in the order they were sent."""
    client = TeranexClient("unit")
    loop = asyncio.get_running_loop()
    first: asyncio.Future[bool] = loop.create_future()
    second: asyncio.Future[bool] = loop.create_future()
    client._waiters.extend([first, second])

    _feed(client, "ACK\n\nNACK\n\n")

    assert first.result() is True
    assert second.result() is False


async def test_wait_ready_times_out_without_device() -> None:
    """Waiting for an unreachable unit returns instead of raising."""
    client = TeranexClient("unit")
    assert await client.async_wait_ready(0.01) is False

    _feed(client, DUMP)
    assert await client.async_wait_ready(0.01) is True


@pytest.mark.parametrize("sequence", [[False, False, True, True, False]])
async def test_reachability_logged_once_per_change(
    caplog: pytest.LogCaptureFixture, sequence: list[bool]
) -> None:
    """Retries while a unit stays off do not fill the log."""
    client = TeranexClient("unit")
    with caplog.at_level(logging.INFO):
        for online in sequence:
            client._log_reachability(online)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Teranex unit:9800 is offline, will keep trying to reconnect",
        "Teranex unit:9800 is online",
        "Teranex unit:9800 is offline, will keep trying to reconnect",
    ]


async def test_over_long_line_ends_read_loop_cleanly() -> None:
    """A line beyond the buffer limit ends the read loop instead of raising."""
    client = TeranexClient("unit")
    reader = asyncio.StreamReader(limit=protocol.MAX_LINE_BYTES)
    reader.feed_data(b"X" * (protocol.MAX_LINE_BYTES * 2))
    reader.feed_eof()
    client._reader = reader

    await client._read_loop()


async def test_supervisor_survives_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected error while connecting never stops the reconnect loop."""
    monkeypatch.setattr(protocol, "RECONNECT_MIN", 0)
    monkeypatch.setattr(protocol, "RECONNECT_MAX", 0)
    client = TeranexClient("unit")
    attempts = 0

    async def failing_open() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("unexpected")
        raise TeranexConnectionError("unreachable")

    monkeypatch.setattr(client, "_open", failing_open)
    await client.async_start()
    await asyncio.sleep(0.05)

    assert attempts >= 3
    assert client._supervisor is not None
    assert not client._supervisor.done()
    await client.async_close()


async def test_block_count_is_capped() -> None:
    """A peer inventing blocks cannot grow the stored state without bound."""
    client = TeranexClient("unit")
    for index in range(protocol.MAX_BLOCKS + 10):
        _feed(client, f"BLOCK {index}:\nKey: value\n\n")

    assert len(client.state) == protocol.MAX_BLOCKS


async def test_field_count_is_capped() -> None:
    """A peer inventing fields cannot grow a block without bound."""
    client = TeranexClient("unit")
    fields = "".join(f"Key {index}: value\n" for index in range(protocol.MAX_FIELDS_PER_BLOCK + 10))
    _feed(client, f"AUDIO:\n{fields}\n")

    assert len(client.block("AUDIO")) == protocol.MAX_FIELDS_PER_BLOCK


async def test_over_long_names_and_values_are_ignored() -> None:
    """Over-long input is dropped, and parsing carries on with the next block."""
    client = TeranexClient("unit")
    long_name = "B" * (protocol.MAX_NAME_LENGTH + 1)
    long_value = "v" * (protocol.MAX_VALUE_LENGTH + 1)
    _feed(
        client,
        f"{long_name}:\nKey: value\n\n"
        f"VIDEO OUTPUT:\nVideo mode: 1080p25\nAspect ratio: {long_value}\n\n",
    )

    assert long_name not in client.state
    assert client.block("VIDEO OUTPUT") == {"Video mode": "1080p25"}


@pytest.mark.parametrize(
    ("block", "fields"),
    [
        ("VIDEO OUTPUT", {"Video mode": "1080p25\nPRESET:\nSave: 1"}),
        ("VIDEO OUTPUT", {"Video mode": "1080p25\r"}),
        ("VIDEO OUTPUT", {"Video: mode": "1080p25"}),
        ("VIDEO\nOUTPUT", {"Video mode": "1080p25"}),
        ("", {"Video mode": "1080p25"}),
        ("VIDEO OUTPUT", {"Video mode": "x" * (protocol.MAX_VALUE_LENGTH + 1)}),
    ],
)
async def test_unsafe_commands_are_refused(block: str, fields: dict[str, str]) -> None:
    """Nothing that could break the line framing is ever sent."""
    client = TeranexClient("unit")
    with pytest.raises(TeranexInvalidValueError):
        await client.async_send(block, fields)


async def test_safe_command_needs_a_connection() -> None:
    """A well-formed command only fails because nothing is connected."""
    client = TeranexClient("unit")
    with pytest.raises(TeranexConnectionError):
        await client.async_send("VIDEO OUTPUT", {"Video mode": "1080p25"})


async def test_timeout_forces_a_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    """A command without a reply drops the connection to resynchronise."""
    monkeypatch.setattr(protocol, "COMMAND_TIMEOUT", 0.01)
    client = TeranexClient("unit")

    class SilentWriter:
        def write(self, data: bytes) -> None:
            """Accept the bytes and never answer."""

        async def drain(self) -> None:
            """Nothing to flush."""

    reader_task = asyncio.create_task(asyncio.sleep(10))
    client._connected = True
    client._writer = SilentWriter()  # type: ignore[assignment]
    client._reader_task = reader_task

    with pytest.raises(TeranexConnectionError):
        await client.async_send("PING", {})
    with contextlib.suppress(asyncio.CancelledError):
        await reader_task

    assert reader_task.cancelled()
