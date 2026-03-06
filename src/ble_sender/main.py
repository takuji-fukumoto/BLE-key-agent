"""BLE key sender entry point.

A simple CLI application that:
1. Scans for and connects to a BLE Peripheral
2. Monitors keyboard input
3. Transmits key events via BLE GATT

Usage:
    python -m ble_sender.main [--device DEVICE_NAME]

Examples:
    # Auto-scan and select device interactively
    python -m ble_sender.main

    # Connect directly to a named device
    python -m ble_sender.main --device "RasPi-KeyAgent"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from common.protocol import KeyEvent
from ble_sender import AgentConfig, KeyBleAgent
from ble_sender.ble_client import BleStatus
from ble_sender.keyboard_monitor import KeyboardMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

class MacAgent:
    """Mac agent application orchestrator.

    Connects KeyMonitor output to BleClient for transmission to Raspberry Pi.
    """

    def __init__(self, device_name: str | None = None) -> None:
        self._device_name = device_name
        self._agent = KeyBleAgent(
            config=AgentConfig(
                device_name=device_name or "RasPi-KeyAgent",
            ),
            on_status_change=self._on_ble_status_change,
            on_error=self._on_error,
            on_key_event=self._on_key_event,
        )
        self._shutdown_event = asyncio.Event()

    def _on_ble_status_change(self, status: BleStatus) -> None:
        """Handle BLE connection status changes."""
        logger.info("BLE status: %s", status)

    def _on_error(self, error: Exception) -> None:
        """Handle internal runtime errors from KeyBleAgent."""
        logger.exception("Agent runtime error: %s", error)

    def _on_key_event(self, _event: KeyEvent) -> None:
        """Handle consumed key events."""

    async def run(self) -> None:
        """Start the agent and run until shutdown."""
        loop = asyncio.get_running_loop()

        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_shutdown)

        try:
            # Scan and connect to BLE device
            await self._connect()

            if self._agent.status != BleStatus.CONNECTED:
                logger.error("Failed to connect to BLE device")
                return

            # Start high-level agent (keyboard monitor + forward + heartbeat)
            await self._agent.start()
            logger.info("Key monitoring started (press Ctrl+C to stop)")

            await self._shutdown_event.wait()

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
            devices = await self._agent.scan(timeout=10.0)
            target = next(
                (d for d in devices if d.name == self._device_name), None
            )
            if target:
                await self._agent.connect(target.address)
            else:
                logger.error(f"Device '{self._device_name}' not found")
        else:
            # Interactive selection
            print("Scanning for BLE devices...")
            devices = await self._agent.scan(timeout=10.0)

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
                    await self._agent.connect(devices[idx].address)
            except (ValueError, IndexError):
                print("Invalid selection")

    def _signal_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        await self._agent.stop()
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
    if sys.platform == "darwin" and not KeyboardMonitor.check_accessibility():
        print("\n⚠️  権限が不足している可能性があります")
        print("   システム設定 → プライバシーとセキュリティ で")
        print("   ・アクセシビリティ → ターミナル/IDE を許可")
        print("   ・入力監視 → ターミナル/IDE を許可\n")

    agent = MacAgent(device_name=args.device)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
