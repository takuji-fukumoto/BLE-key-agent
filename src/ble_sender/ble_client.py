"""BLE Central client for connecting to Raspberry Pi key receiver.

Manages device scanning, connection lifecycle, and key event transmission
using the bleak library. Implements automatic reconnection with exponential
backoff per requirements.md.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

from common.protocol import KeyEvent
from common.uuids import KEY_CHAR_UUID, KEY_SERVICE_UUID

if TYPE_CHECKING:
    from bleak import BleakClient as BleakClientType
    from bleak.backends.device import BLEDevice

logger = logging.getLogger(__name__)

class BleStatus(Enum):
    """BLE connection status (per spec-mac-agent.md §3)."""

    DISCONNECTED = "DISCONNECTED"
    SCANNING = "SCANNING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


# Backward-compatible aliases
STATUS_DISCONNECTED = BleStatus.DISCONNECTED
STATUS_SCANNING = BleStatus.SCANNING
STATUS_CONNECTING = BleStatus.CONNECTING
STATUS_CONNECTED = BleStatus.CONNECTED
STATUS_RECONNECTING = BleStatus.RECONNECTING


@dataclass
class BleDevice:
    """BLE device information from scan results.

    Attributes:
        name: Device name (may be empty if not advertised).
        address: MAC address (unique identifier).
        rssi: Signal strength in dBm (may be None).
    """

    name: str
    address: str
    rssi: Optional[int]


class BleClient:
    """BLE Central client for connecting to Raspberry Pi key receiver.

    Manages device scanning, connection lifecycle, and key event transmission.
    Implements automatic reconnection with exponential backoff per requirements.md.

    Based on poc/ble_gatt/central_mac.py with reconnection logic added.

    Args:
        on_status_change: Callback invoked when connection status changes.
                          Receives status string (DISCONNECTED, SCANNING, etc.)

    Example:
        >>> def on_status(status: str):
        ...     print(f"Status: {status}")
        >>> client = BleClient(on_status_change=on_status)
        >>> devices = await client.scan(timeout=5.0)
        >>> if devices:
        ...     await client.connect(devices[0].address)
        ...     event = KeyEvent(...)
        ...     await client.send_key(event)
        ...     await client.disconnect()
    """

    def __init__(
        self,
        on_status_change: Callable[[BleStatus], None] | None = None,
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        reconnect_backoff_multiplier: float = 2.0,
        connect_max_attempts: int = 3,
        connect_retry_delay: float = 1.0,
    ) -> None:
        """Initialize BleClient.

        Args:
            on_status_change: Callback for status changes.
            reconnect_initial_delay: Initial delay before first reconnect attempt.
            reconnect_max_delay: Maximum reconnect delay.
            reconnect_backoff_multiplier: Exponential backoff multiplier.
            connect_max_attempts: Maximum connection attempts per connect() call.
            connect_retry_delay: Delay in seconds between connection retry attempts.
        """
        self._on_status_change = on_status_change
        self._status = STATUS_DISCONNECTED
        self._client: Optional[BleakClientType] = None
        self._connected_device: Optional[BleDevice] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_address: Optional[str] = None
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._reconnect_backoff_multiplier = reconnect_backoff_multiplier
        self._connect_max_attempts = connect_max_attempts
        self._connect_retry_delay = connect_retry_delay

    @property
    def status(self) -> BleStatus:
        """Return current connection status."""
        return self._status

    @property
    def connected_device(self) -> Optional[BleDevice]:
        """Return connected device info, or None if not connected."""
        return self._connected_device

    async def scan(self, timeout: float = 5.0) -> list[BleDevice]:
        """Scan for BLE devices.

        Prioritizes devices advertising KEY_SERVICE_UUID per spec.

        Args:
            timeout: Scan duration in seconds.

        Returns:
            List of BleDevice objects sorted by RSSI (strongest first).
        """
        from bleak import BleakScanner

        self._set_status(STATUS_SCANNING)

        try:
            devices = await BleakScanner.discover(
                timeout=timeout,
                return_adv=True,
                service_uuids=[KEY_SERVICE_UUID],
            )

            # Convert to BleDevice objects
            result = []
            for device, adv in devices.values():
                ble_device = BleDevice(
                    name=device.name or adv.local_name or "",
                    address=device.address,
                    rssi=adv.rssi
                )
                result.append(ble_device)

            # Sort by RSSI (strongest first)
            result.sort(key=lambda d: d.rssi or -100, reverse=True)

            logger.info("Scan found %d devices", len(result))
            return result

        finally:
            if self._status == STATUS_SCANNING:
                self._set_status(STATUS_DISCONNECTED)

    async def connect(self, address: str) -> bool:
        """Connect to a BLE device by address with retry.

        Attempts connection up to ``connect_max_attempts`` times with
        ``connect_retry_delay`` seconds between attempts.  Verifies
        KEY_SERVICE_UUID is present before returning success.

        Args:
            address: MAC address of target device.

        Returns:
            True if connection succeeded, False otherwise.
        """
        if self._client is not None:
            await self.disconnect()

        self._set_status(STATUS_CONNECTING)
        self._last_address = address

        for attempt in range(1, self._connect_max_attempts + 1):
            logger.info(
                "Connection attempt %d/%d to %s",
                attempt,
                self._connect_max_attempts,
                address,
            )
            success = await self._connect_once(address)
            if success:
                return True

            if attempt < self._connect_max_attempts:
                logger.info("Retrying in %.1fs...", self._connect_retry_delay)
                await asyncio.sleep(self._connect_retry_delay)

        logger.warning(
            "All %d connection attempts failed for %s",
            self._connect_max_attempts,
            address,
        )
        self._set_status(STATUS_DISCONNECTED)
        return False

    async def _connect_once(self, address: str) -> bool:
        """Single connection attempt (internal).

        Discovers the device using Service UUID hint for improved
        reliability on macOS, then connects and verifies the GATT service.

        Args:
            address: MAC address of target device.

        Returns:
            True if connection succeeded, False otherwise.
        """
        from bleak import BleakClient, BleakScanner

        try:
            device = await BleakScanner.find_device_by_filter(
                filterfunc=lambda d, adv: d.address == address,
                timeout=10.0,
                service_uuids=[KEY_SERVICE_UUID],
            )

            if device is None:
                logger.warning("Device not found: %s", address)
                return False

            client = BleakClient(
                device,
                disconnected_callback=self._on_disconnect,
            )
            await client.connect()

            if not self._verify_key_service(client):
                logger.error("Device missing KEY_SERVICE_UUID")
                await client.disconnect()
                return False

            self._client = client
            self._connected_device = BleDevice(
                name=device.name or "",
                address=address,
                rssi=None,
            )
            self._set_status(STATUS_CONNECTED)

            logger.info(
                "Connected to %s (%s), MTU: %d",
                device.name,
                address,
                client.mtu_size,
            )
            return True

        except Exception:
            logger.exception("Connection attempt failed to %s", address)
            return False

    async def send_key(self, event: KeyEvent) -> bool:
        """Send a key event to the connected device.

        Uses Write Without Response for low latency per spec.

        Args:
            event: KeyEvent to transmit.

        Returns:
            True if send succeeded, False otherwise.
        """
        if self._client is None or not self._client.is_connected:
            logger.warning("Cannot send key: not connected")
            return False

        try:
            data = event.serialize()

            await self._client.write_gatt_char(
                KEY_CHAR_UUID,
                data,
                response=False  # Write Without Response
            )

            logger.debug(
                "Sent key: type=%s, value=%s, size=%d bytes",
                event.key_type.value,
                event.value,
                len(data)
            )
            return True

        except Exception:
            logger.exception("Failed to send key event")
            return False

    async def disconnect(self) -> None:
        """Disconnect from current device.

        Cancels any pending reconnection attempts.
        """
        # Cancel reconnection if running
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Disconnect client
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                logger.exception("Error during disconnect")
            finally:
                self._client = None
                self._connected_device = None

        self._set_status(STATUS_DISCONNECTED)

    def _verify_key_service(self, client: BleakClientType) -> bool:
        """Verify client has KEY_SERVICE_UUID and KEY_CHAR_UUID.

        Args:
            client: Connected BleakClient instance.

        Returns:
            True if service and characteristic are found, False otherwise.
        """
        for service in client.services:
            if service.uuid == KEY_SERVICE_UUID:
                for char in service.characteristics:
                    if char.uuid == KEY_CHAR_UUID:
                        logger.debug(
                            "Found KEY_CHAR_UUID with properties: %s",
                            char.properties
                        )
                        return True

        logger.error(
            "KEY_SERVICE_UUID or KEY_CHAR_UUID not found. "
            "Available services: %s",
            [s.uuid for s in client.services]
        )
        return False

    def _set_status(self, new_status: BleStatus) -> None:
        """Update status and notify callback with exception isolation.

        Args:
            new_status: New connection status.
        """
        old_status = self._status
        self._status = new_status

        logger.debug("Status change: %s -> %s", old_status, new_status)

        if self._on_status_change:
            try:
                self._on_status_change(new_status)
            except Exception:
                logger.exception(
                    "Exception in on_status_change callback (status=%s)",
                    new_status
                )

    def _on_disconnect(self, client: BleakClientType) -> None:
        """Bleak disconnection callback (runs in event loop).

        Triggers automatic reconnection if a previous address is stored.

        Args:
            client: Disconnected BleakClient instance.
        """
        logger.warning("BLE connection lost")
        self._client = None

        # Start reconnection if we have a last address
        if self._last_address is not None:
            if self._reconnect_task and not self._reconnect_task.done():
                logger.debug("Reconnect task already running, skipping")
                return
            loop = asyncio.get_running_loop()
            self._reconnect_task = loop.create_task(
                self._reconnect_loop()
            )
        else:
            self._set_status(STATUS_DISCONNECTED)

    async def _reconnect_loop(self) -> None:
        """Automatic reconnection with exponential backoff.

        Implements exponential backoff: 1s → 2s → 4s → ... → max 60s.
        Resets backoff on successful reconnection.

        Continues indefinitely until connection succeeds or task is cancelled.
        """
        if self._last_address is None:
            logger.warning("No last address for reconnection")
            return

        self._set_status(STATUS_RECONNECTING)

        delay = self._reconnect_initial_delay
        max_delay = self._reconnect_max_delay
        backoff_multiplier = self._reconnect_backoff_multiplier

        attempt = 0
        while True:
            attempt += 1
            logger.info(
                "Reconnection attempt %d in %.1fs to %s",
                attempt,
                delay,
                self._last_address
            )

            await asyncio.sleep(delay)

            success = await self.connect(self._last_address)
            if success:
                logger.info("Reconnection successful after %d attempts", attempt)
                return  # Exit loop

            # Exponential backoff
            delay = min(delay * backoff_multiplier, max_delay)


class BleSender(BleClient):
    """Library-friendly BLE sender API.

    This class is an explicit, reusable sender-facing alias for `BleClient`.
    Existing applications can keep using `BleClient`, while external users
    can depend on the semantically clearer `BleSender` name.
    """

