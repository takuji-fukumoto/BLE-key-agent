"""Mac Agent entry point for BLE key transmission.

A simple CLI application that:
1. Scans for and connects to Raspberry Pi (BLE Peripheral)
2. Monitors keyboard input
3. Transmits key events via BLE GATT

Usage:
    python -m mac_agent.main [--device DEVICE_NAME]

Examples:
    # Auto-scan and select device interactively
    python -m mac_agent.main

    # Connect directly to a named device
    python -m mac_agent.main --device "RasPi-KeyAgent"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time

from mac_agent.ble_client import BleClient, STATUS_CONNECTED
from mac_agent.key_monitor import KeyMonitor
from common.protocol import KeyEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Heartbeat interval in seconds. Pi-side timeout (10s) should be >= 3x this.
HEARTBEAT_INTERVAL_SEC: float = 3.0

# Minimum interval between BLE writes to prevent overwhelming the Pi.
MIN_SEND_INTERVAL_S: float = 0.005  # 5ms

# Maximum pending key events on the Mac side (backpressure).
MAC_KEY_QUEUE_MAX_SIZE: int = 256


class MacAgent:
    """Mac agent application orchestrator.

    Connects KeyMonitor output to BleClient for transmission to Raspberry Pi.
    """

    def __init__(self, device_name: str | None = None) -> None:
        self._device_name = device_name
        self._key_queue: asyncio.Queue[KeyEvent | None] = asyncio.Queue(
            maxsize=MAC_KEY_QUEUE_MAX_SIZE
        )
        self._ble_client = BleClient(on_status_change=self._on_ble_status_change)
        self._key_monitor = KeyMonitor(self._key_queue)
        self._shutdown_event = asyncio.Event()
        self._last_send_time: float = 0.0

    def _on_ble_status_change(self, status: str) -> None:
        """Handle BLE connection status changes."""
        logger.info("BLE status: %s", status)

    async def run(self) -> None:
        """Start the agent and run until shutdown."""
        loop = asyncio.get_running_loop()

        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_shutdown)

        try:
            # Scan and connect to BLE device
            await self._connect()

            if self._ble_client.status != STATUS_CONNECTED:
                logger.error("Failed to connect to BLE device")
                return

            # Start key monitoring
            await self._key_monitor.start()
            logger.info("Key monitoring started (press Esc to stop)")

            # Run key forwarding and heartbeat in parallel
            await asyncio.gather(
                self._forward_loop(),
                self._heartbeat_loop(),
            )

        finally:
            await self._cleanup()

    async def _connect(self) -> None:
        """Scan for devices and connect."""
        print("\n" + "=" * 50)
        print("BLE Key Agent - Mac")
        print("=" * 50 + "\n")

        if self._device_name:
            # Direct connection by name
            print(f"Connecting to '{self._device_name}'...")
            devices = await self._ble_client.scan(timeout=10.0)
            target = next(
                (d for d in devices if d.name == self._device_name), None
            )
            if target:
                await self._ble_client.connect(target.address)
            else:
                logger.error(f"Device '{self._device_name}' not found")
        else:
            # Interactive selection
            print("Scanning for BLE devices...")
            devices = await self._ble_client.scan(timeout=10.0)

            if not devices:
                print("No devices found.")
                return

            print("\nFound devices:")
            for i, dev in enumerate(devices, 1):
                rssi_str = f" ({dev.rssi} dBm)" if dev.rssi else ""
                name = dev.name or "(no name)"
                print(f"  [{i}] {name}{rssi_str} - {dev.address}")

            print()
            try:
                choice = input("Select device number (or 'q' to quit): ").strip()
                if choice.lower() == 'q':
                    return
                idx = int(choice) - 1
                if 0 <= idx < len(devices):
                    print(f"\nConnecting to {devices[idx].name}...")
                    await self._ble_client.connect(devices[idx].address)
            except (ValueError, IndexError):
                print("Invalid selection")

    async def _forward_loop(self) -> None:
        """Forward key events from monitor to BLE client."""
        print("\n" + "-" * 50)
        print("Transmitting key input to Raspberry Pi...")
        print("Press Esc to stop.")
        print("-" * 50 + "\n")

        while not self._shutdown_event.is_set():
            try:
                # Get key event with timeout to check shutdown flag
                event = await asyncio.wait_for(
                    self._key_queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue

            if event is None:
                # Stop signal from KeyMonitor (Esc pressed)
                logger.info("Esc pressed, stopping...")
                self._shutdown_event.set()
                break

            # Rate limiting: enforce minimum interval between sends
            now = time.monotonic()
            elapsed = now - self._last_send_time
            if elapsed < MIN_SEND_INTERVAL_S:
                await asyncio.sleep(MIN_SEND_INTERVAL_S - elapsed)

            # Send via BLE
            if self._ble_client.status == STATUS_CONNECTED:
                await self._ble_client.send_key(event)
                self._last_send_time = time.monotonic()
                # Log key press only
                if event.press:
                    logger.debug(f"Sent: {event}")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat while connected.

        Skips sending if a key event was sent recently (within the
        heartbeat interval) to avoid unnecessary BLE traffic.
        """
        while not self._shutdown_event.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
            if self._shutdown_event.is_set():
                break
            # Skip if we sent data recently
            elapsed = time.monotonic() - self._last_send_time
            if elapsed < HEARTBEAT_INTERVAL_SEC:
                continue
            if self._ble_client.status == STATUS_CONNECTED:
                await self._ble_client.send_key(KeyEvent.heartbeat())
                self._last_send_time = time.monotonic()
                logger.debug("Heartbeat sent")

    def _signal_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        await self._key_monitor.stop()
        await self._ble_client.disconnect()
        print("\nDisconnected. Goodbye!")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Mac Agent - BLE key transmitter"
    )
    parser.add_argument(
        "--device", "-d",
        help="Device name to connect directly (e.g., 'RasPi-KeyAgent')",
    )
    args = parser.parse_args()

    # Check accessibility (macOS)
    if sys.platform == "darwin":
        from pynput import keyboard
        if hasattr(keyboard.Listener, 'IS_TRUSTED'):
            if not keyboard.Listener.IS_TRUSTED:
                print("\n⚠️  権限が不足している可能性があります")
                print("   システム設定 → プライバシーとセキュリティ で")
                print("   ・アクセシビリティ → ターミナル/IDE を許可")
                print("   ・入力監視 → ターミナル/IDE を許可\n")

    agent = MacAgent(device_name=args.device)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
