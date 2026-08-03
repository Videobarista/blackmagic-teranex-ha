"""Client for the Blackmagic Teranex Ethernet Protocol (TCP 9800).

The protocol is line oriented and text based. The device sends a full state
dump on connect and pushes only the changed block whenever anything changes --
including changes made by the front panel or by another controller. We
therefore keep one persistent connection open and never poll.

Blocks look like::

    VIDEO OUTPUT:
    Video mode: 1080p24
    Aspect ratio: Anamorphic
    <blank line>

Commands use the same shape and are answered with a bare ACK or NACK. The ACK
only means "understood" -- the actual truth arrives as a separate status block,
so callers must never assume their write took effect.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Mapping

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 9800

CONNECT_TIMEOUT = 10.0
READY_TIMEOUT = 15.0
COMMAND_TIMEOUT = 10.0
PING_INTERVAL = 30.0
RECONNECT_MIN = 5.0
RECONNECT_MAX = 120.0

BLOCK_PREAMBLE = "PROTOCOL PREAMBLE"
BLOCK_DEVICE = "TERANEX DEVICE"
BLOCK_VIDEO_INPUT = "VIDEO INPUT"
BLOCK_VIDEO_OUTPUT = "VIDEO OUTPUT"
BLOCK_PROC_AMP = "VIDEO PROC AMP"
BLOCK_GENLOCK = "GENLOCK"
BLOCK_PRESET = "PRESET"
BLOCK_NETWORK = "NETWORK CONFIG"

_ACK = "ACK"
_NACK = "NACK"


class TeranexError(Exception):
    """Base error for the Teranex client."""


class TeranexConnectionError(TeranexError):
    """Raised when the device cannot be reached."""


class TeranexCommandError(TeranexError):
    """Raised when the device rejects a command with NACK."""


class TeranexClient:
    """Persistent connection to a Teranex processor."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        """Initialise the client. No I/O happens here."""
        self.host = host
        self.port = port

        # state[block][key] = value, exactly as reported by the device.
        self.state: dict[str, dict[str, str]] = {}

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._supervisor: asyncio.Task | None = None
        self._reader_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None

        self._connected = False
        self._closing = False
        self._ready = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._waiters: deque[asyncio.Future[bool]] = deque()
        self._listeners: list[Callable[[], None]] = []

        # Partial block being assembled by the reader.
        self._block: str | None = None
        self._fields: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Return whether the connection is currently up."""
        return self._connected

    @property
    def model(self) -> str | None:
        """Return the reported model name, if known."""
        return self.get(BLOCK_DEVICE, "Model name")

    def get(self, block: str, key: str) -> str | None:
        """Return a single value, or None if the device never reported it."""
        return self.state.get(block, {}).get(key)

    def block(self, block: str) -> Mapping[str, str]:
        """Return a whole block as a read-only mapping."""
        return self.state.get(block, {})

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired on every state or availability change."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    async def async_connect_once(self) -> None:
        """Connect once and wait for the initial dump. Used by the config flow.

        Raises TeranexConnectionError on any failure. The caller is
        responsible for calling async_close().
        """
        await self._open()
        try:
            await asyncio.wait_for(self._ready.wait(), READY_TIMEOUT)
        except TimeoutError as err:
            await self.async_close()
            raise TeranexConnectionError(
                f"{self.host} accepted the connection but sent no device block"
            ) from err

    async def async_start(self) -> None:
        """Start the supervised connection and wait for the first dump."""
        self._closing = False
        self._supervisor = asyncio.create_task(self._supervise())
        try:
            await asyncio.wait_for(self._ready.wait(), READY_TIMEOUT)
        except TimeoutError as err:
            await self.async_close()
            raise TeranexConnectionError(
                f"No response from {self.host}:{self.port}"
            ) from err

    async def async_close(self) -> None:
        """Tear everything down."""
        self._closing = True
        if self._supervisor:
            self._supervisor.cancel()
            self._supervisor = None
        await self._disconnect()

    async def async_send(self, block: str, fields: Mapping[str, str]) -> None:
        """Send a command block and wait for ACK.

        An ACK is not confirmation that the value changed -- watch for the
        status update instead.
        """
        lines = [f"{block}:"]
        lines.extend(f"{key}: {value}" for key, value in fields.items())
        payload = ("\n".join(lines) + "\n\n").encode("utf-8")

        async with self._send_lock:
            if not self._connected or self._writer is None:
                raise TeranexConnectionError(f"Not connected to {self.host}")

            loop = asyncio.get_running_loop()
            waiter: asyncio.Future[bool] = loop.create_future()
            self._waiters.append(waiter)

            try:
                self._writer.write(payload)
                await self._writer.drain()
                accepted = await asyncio.wait_for(waiter, COMMAND_TIMEOUT)
            except TimeoutError as err:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
                raise TeranexConnectionError(
                    f"No reply to {block} from {self.host}"
                ) from err
            except (OSError, ConnectionError) as err:
                raise TeranexConnectionError(str(err)) from err

        if not accepted:
            raise TeranexCommandError(f"Device rejected: {block} {dict(fields)}")

    async def async_request_block(self, block: str) -> None:
        """Ask the device to resend a full status block."""
        await self.async_send(block, {})

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def _supervise(self) -> None:
        """Keep the connection up, reconnecting with backoff."""
        delay = RECONNECT_MIN
        while not self._closing:
            try:
                await self._open()
                delay = RECONNECT_MIN
                # _reader_task lives until the connection drops.
                if self._reader_task:
                    await self._reader_task
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - supervisor must not die
                _LOGGER.debug("Teranex %s connection failed: %s", self.host, err)

            if self._closing:
                return

            await self._disconnect()
            _LOGGER.debug(
                "Teranex %s disconnected, retrying in %.0fs", self.host, delay
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            delay = min(delay * 2, RECONNECT_MAX)

    async def _open(self) -> None:
        """Open the socket and start the reader and keepalive tasks."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
            )
        except (OSError, TimeoutError) as err:
            raise TeranexConnectionError(
                f"Cannot reach {self.host}:{self.port}: {err}"
            ) from err

        self._connected = True
        self._block = None
        self._fields = {}
        self._reader_task = asyncio.create_task(self._read_loop())
        self._ping_task = asyncio.create_task(self._keepalive())

    async def _disconnect(self) -> None:
        """Close the socket and cancel helper tasks."""
        was_connected = self._connected
        self._connected = False
        self._ready.clear()

        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.cancel()

        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (OSError, ConnectionError):
                pass
        self._writer = None
        self._reader = None

        if was_connected:
            self._notify()

    async def _keepalive(self) -> None:
        """Send PING periodically so a dead socket is noticed."""
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await self.async_send("PING", {})
            except TeranexError as err:
                _LOGGER.debug("Teranex %s keepalive failed: %s", self.host, err)
                if self._reader_task:
                    self._reader_task.cancel()
                return

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read and parse lines until the connection drops."""
        assert self._reader is not None
        while True:
            try:
                raw = await self._reader.readline()
            except (OSError, ConnectionError) as err:
                _LOGGER.debug("Teranex %s read error: %s", self.host, err)
                return
            if not raw:
                return  # EOF
            self._handle_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))

    def _handle_line(self, line: str) -> None:
        """Feed one line into the block assembler."""
        if not line.strip():
            self._flush()
            return

        if self._block is None:
            if line in (_ACK, _NACK):
                self._resolve(line == _ACK)
                return
            if line.endswith(":"):
                self._block = line[:-1].strip()
                self._fields = {}
            else:
                _LOGGER.debug("Teranex %s: stray line %r", self.host, line)
            return

        key, sep, value = line.partition(":")
        if not sep:
            _LOGGER.debug("Teranex %s: unparsable line %r", self.host, line)
            return
        self._fields[key.strip()] = value.strip()

    def _flush(self) -> None:
        """Commit the assembled block into state and notify listeners."""
        if self._block is None:
            return
        block, fields = self._block, self._fields
        self._block, self._fields = None, {}

        if not fields:
            return

        # Status updates contain only what changed, so merge rather than replace.
        self.state.setdefault(block, {}).update(fields)

        if block == BLOCK_DEVICE and not self._ready.is_set():
            self._ready.set()

        self._notify()

    def _resolve(self, accepted: bool) -> None:
        """Hand an ACK/NACK to the oldest waiting command."""
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(accepted)
                return

    def _notify(self) -> None:
        """Fire all registered listeners, never letting one break the rest."""
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Teranex listener raised")
