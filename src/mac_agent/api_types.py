"""Public API type definitions for reusable mac_agent library components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from common.protocol import KeyEvent


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for the reusable BLE key sender agent.

    Attributes:
        device_name: Default BLE peripheral name to target.
        reconnect_initial_delay: Initial reconnect wait in seconds.
        reconnect_max_delay: Maximum reconnect wait in seconds.
        reconnect_backoff_multiplier: Exponential reconnect multiplier.
        heartbeat_interval_sec: Heartbeat interval in seconds.
        min_send_interval_sec: Minimum interval between BLE writes.
        key_queue_max_size: Maximum buffered key events.
        connect_max_attempts: Maximum connection attempts per connect() call.
        connect_retry_delay: Delay in seconds between connection retry attempts.
    """

    device_name: str = "RasPi-KeyAgent"
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    reconnect_backoff_multiplier: float = 2.0
    heartbeat_interval_sec: float = 3.0
    min_send_interval_sec: float = 0.005
    key_queue_max_size: int = 256
    connect_max_attempts: int = 3
    connect_retry_delay: float = 1.0


StatusCallback = Callable[[object], None]
ErrorCallback = Callable[[Exception], None]
KeyEventCallback = Callable[[KeyEvent], None]
