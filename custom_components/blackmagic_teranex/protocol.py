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

A device that is switched off or unplugged is a normal condition, not an
integration failure: those paths log at debug level and surface as
unavailable entities.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Mapping
import logging

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 9800

CONNECT_TIMEOUT = 10.0
READY_TIMEOUT = 15.0
COMMAND_TIMEOUT = 10.0
PING_INTERVAL = 30.0
RECONNECT_MIN = 5.0
RECONNECT_MAX = 60.0

# Defensive limits on what the unit may send. A real Teranex 2D sends about 20
# blocks, at most about 100 fields in one block, and lines well under 100
# characters, so these leave a wide margin while keeping a faulty or hostile
# peer from exhausting memory.
MAX_LINE_BYTES = 8192
MAX_BLOCKS = 64
MAX_FIELDS_PER_BLOCK = 512
MAX_NAME_LENGTH = 64
MAX_VALUE_LENGTH = 255  # Also the longest state Home Assistant accepts.
LOG_EXCERPT = 200

# Characters that would end a protocol line or split a key from its value.
_LINE_BREAKS = ("\r", "\n")

BLOCK_PREAMBLE = "PROTOCOL PREAMBLE"
BLOCK_DEVICE = "TERANEX DEVICE"
BLOCK_VIDEO_INPUT = "VIDEO INPUT"
BLOCK_VIDEO_OUTPUT = "VIDEO OUTPUT"
BLOCK_PROC_AMP = "VIDEO PROC AMP"
BLOCK_GENLOCK = "GENLOCK"
BLOCK_VIDEO_ADJUST = "VIDEO ADJUST"
BLOCK_NOISE_REDUCTION = "NOISE REDUCTION"
BLOCK_TEST_PATTERN = "TEST PATTERN"
BLOCK_ANCILLARY = "ANCILLARY DATA"
BLOCK_AUDIO = "AUDIO"
BLOCK_VARIABLE_ASPECT = "VARIABLE ASPECT RATIO"
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


class TeranexInvalidValueError(TeranexError):
    """Raised when a command would break the protocol framing.

    Nothing is sent in that case. Values that contain a line break could
    otherwise smuggle extra commands to the unit.
    """


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
        self._last_logged_online: bool | None = None
        self._ready = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._waiters: deque[asyncio.Future[bool]] = deque()
        self._listeners: list[Callable[[], None]] = []

        # Partial block being assembled by the reader.
        self._block: str | None = None
        self._fields: dict[str, str] = {}
        # True while the lines of an ignored block are being skipped.
        self._skipping = False

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
            raise TeranexConnectionError(
                f"{self.host} accepted the connection but sent no device block"
            ) from err

    async def async_start(self) -> None:
        """Start the supervised connection in the background.

        This never fails: a Teranex that is switched off is a normal state,
        and the supervisor keeps trying until it answers.
        """
        self._closing = False
        self._supervisor = asyncio.create_task(self._supervise())

    async def async_wait_ready(self, timeout: float) -> bool:
        """Wait up to timeout seconds for the first state dump.

        Returns False when the device did not answer in time.
        """
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def async_close(self) -> None:
        """Tear everything down."""
        self._closing = True
        if self._supervisor is not None:
            self._supervisor.cancel()
            self._supervisor = None
        await self._disconnect()

    async def async_send(self, block: str, fields: Mapping[str, str]) -> None:
        """Send a command block and wait for ACK.

        An ACK is not confirmation that the value changed -- watch for the
        status update instead.
        """
        _validate_command(block, fields)
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
                # A reply that arrives late would be matched to the next
                # command. Reconnecting gives a clean slate and a fresh dump.
                self._force_reconnect()
                raise TeranexConnectionError(
                    f"No reply to {block} from {self.host}"
                ) from err
            except (OSError, ConnectionError) as err:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
                raise TeranexConnectionError(
                    f"Write to {self.host} failed: {err}"
                ) from err

        if not accepted:
            raise TeranexCommandError(f"Device rejected: {block} {dict(fields)}")

    async def async_request_block(self, block: str) -> None:
        """Ask the device to resend a full status block."""
        await self.async_send(block, {})

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def _supervise(self) -> None:
        """Keep the connection up, reconnecting with backoff.

        A device that is off or unreachable is expected in this domain. Each
        change between online and offline is logged once at info level; the
        individual retries in between are debug level only. An unexpected
        error is logged and retried too, so this loop only ends on close.
        """
        delay = RECONNECT_MIN
        while not self._closing:
            try:
                await self._open()
            except TeranexConnectionError as err:
                _LOGGER.debug("Teranex %s not reachable: %s", self.host, err)
                self._log_reachability(False)
            except Exception:  # noqa: BLE001 - the reconnect loop must survive anything
                _LOGGER.exception("Teranex %s: unexpected error while connecting", self.host)
            else:
                delay = RECONNECT_MIN
                self._log_reachability(True)
                await self._async_wait_for_reader()

            if self._closing:
                return

            await self._disconnect()
            _LOGGER.debug("Teranex %s retrying in %.0f s", self.host, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    async def _async_wait_for_reader(self) -> None:
        """Wait until the read loop ends, whatever the reason."""
        reader_task = self._reader_task
        if reader_task is None:
            return
        try:
            await reader_task
        except asyncio.CancelledError:
            if self._closing:
                raise
        except Exception:  # noqa: BLE001 - logged; the supervisor reconnects
            _LOGGER.exception("Teranex %s: read loop failed", self.host)

    def _force_reconnect(self) -> None:
        """Drop the connection; the supervisor opens a fresh one."""
        reader_task = self._reader_task
        if reader_task is not None:
            reader_task.cancel()

    def _log_reachability(self, online: bool) -> None:
        """Log a change between reachable and unreachable, once per change."""
        if online == self._last_logged_online:
            return
        if online:
            _LOGGER.info("Teranex %s:%s is online", self.host, self.port)
        else:
            _LOGGER.info(
                "Teranex %s:%s is offline, will keep trying to reconnect",
                self.host,
                self.port,
            )
        self._last_logged_online = online

    async def _open(self) -> None:
        """Open the socket and start the reader and keepalive tasks."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, limit=MAX_LINE_BYTES),
                CONNECT_TIMEOUT,
            )
        except (OSError, TimeoutError) as err:
            raise TeranexConnectionError(
                f"Cannot reach {self.host}:{self.port}: {err}"
            ) from err

        self._connected = True
        self._block = None
        self._fields = {}
        self._skipping = False
        self._reader_task = asyncio.create_task(self._read_loop())
        self._ping_task = asyncio.create_task(self._keepalive())

    async def _disconnect(self) -> None:
        """Close the socket and cancel helper tasks."""
        was_connected = self._connected
        self._connected = False
        self._ready.clear()

        if self._ping_task is not None:
            self._ping_task.cancel()
            self._ping_task = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None

        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.cancel()

        writer = self._writer
        self._writer = None
        self._reader = None

        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError) as err:
                # The peer is already gone; nothing left to clean up.
                _LOGGER.debug("Teranex %s socket closed with %s", self.host, err)

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
                self._force_reconnect()
                return

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read and parse lines until the connection drops."""
        reader = self._reader
        if reader is None:
            return
        while True:
            try:
                raw = await reader.readline()
            except (OSError, ConnectionError) as err:
                _LOGGER.debug("Teranex %s read error: %s", self.host, err)
                return
            except ValueError:
                # readline() raises ValueError for a line longer than the
                # buffer limit. A Teranex never sends one; reconnect cleanly.
                _LOGGER.warning(
                    "Teranex %s sent a line longer than %s bytes; reconnecting",
                    self.host,
                    MAX_LINE_BYTES,
                )
                return
            if not raw:
                return  # EOF
            self._handle_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))

    def _handle_line(self, line: str) -> None:
        """Feed one line into the block assembler.

        Everything the unit sends is treated as untrusted: names and values
        are length-limited, and the number of blocks and fields is capped.
        """
        if not line.strip():
            self._flush()
            return

        if self._skipping:
            return

        if self._block is None:
            if line in (_ACK, _NACK):
                self._resolve(line == _ACK)
                return
            if line.endswith(":"):
                name = line[:-1].strip()
                if len(name) > MAX_NAME_LENGTH:
                    self._log_ignored("over-long block name", line)
                    name = None
                self._block = name
                self._skipping = name is None
                self._fields = {}
            else:
                self._log_ignored("stray line", line)
            return

        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep:
            self._log_ignored("unparsable line", line)
        elif len(key) > MAX_NAME_LENGTH or len(value) > MAX_VALUE_LENGTH:
            self._log_ignored("over-long field", line)
        elif key not in self._fields and len(self._fields) >= MAX_FIELDS_PER_BLOCK:
            self._log_ignored("field beyond the per-block limit", line)
        else:
            self._fields[key] = value

    def _flush(self) -> None:
        """Commit the assembled block into state and notify listeners."""
        self._skipping = False
        if self._block is None:
            return
        block, fields = self._block, self._fields
        self._block, self._fields = None, {}

        if not fields:
            return

        if block not in self.state and len(self.state) >= MAX_BLOCKS:
            self._log_ignored("block beyond the block limit", block)
            return

        # Status updates contain only what changed, so merge rather than replace.
        stored = self.state.setdefault(block, {})
        for key, value in fields.items():
            if key in stored or len(stored) < MAX_FIELDS_PER_BLOCK:
                stored[key] = value

        if block == BLOCK_DEVICE and not self._ready.is_set():
            self._ready.set()

        self._notify()

    def _log_ignored(self, reason: str, text: str) -> None:
        """Log ignored input at debug level, shortened so logs stay small."""
        _LOGGER.debug("Teranex %s: ignoring %s %r", self.host, reason, text[:LOG_EXCERPT])

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
            except Exception:  # noqa: BLE001 - one bad listener must not stop the rest
                _LOGGER.exception("Teranex %s listener raised", self.host)


def _validate_command(block: str, fields: Mapping[str, str]) -> None:
    """Refuse anything that would break the line-based framing.

    The unit reads one "key: value" per line and a blank line ends a block,
    so a line break in any part, or a colon in a name, could inject commands.
    Raises TeranexInvalidValueError without sending anything.
    """
    names = [block, *fields.keys()]
    parts = [*names, *(str(value) for value in fields.values())]
    if any(brk in part for part in parts for brk in _LINE_BREAKS):
        raise TeranexInvalidValueError("Line breaks are not allowed in a command")
    if any(":" in name or not name.strip() for name in names):
        raise TeranexInvalidValueError("Names must be non-empty and contain no colon")
    if any(len(part) > MAX_VALUE_LENGTH for part in parts):
        raise TeranexInvalidValueError("Command part too long")
