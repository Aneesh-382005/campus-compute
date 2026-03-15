"""UDP broadcast client for worker auto-discovery of coordinator.

Network fallback hierarchy
--------------------------
1. If COORDINATOR_HOST env var is set → unicast directly to that IP (works even
   on AP-isolated networks like campus/enterprise WiFi).
2. Otherwise → broadcast to 255.255.255.255 (works on mobile hotspot / home LAN).
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass

DISCOVERY_BROADCAST_IP = "255.255.255.255"
DISCOVERY_PORT = 9999
DISCOVERY_MESSAGE = "DISCOVER_CLUSTER"
DEFAULT_WS_PORT = 8000


@dataclass(frozen=True)
class DiscoveryResult:
    """Coordinator connection details discovered over UDP."""

    coordinatorIp: str
    wsPort: int

    @property
    def websocketAddress(self) -> str:
        """Address workers should use to connect to the coordinator WebSocket."""

        return f"ws://{self.coordinatorIp}:{self.wsPort}/ws"


def discoverCoordinator(
    timeout_seconds: float = 5.0,
    broadcast_ip: str = DISCOVERY_BROADCAST_IP,
    discovery_port: int = DISCOVERY_PORT,
) -> DiscoveryResult:
    """Discover coordinator via UDP.

    Resolution order:
    1. COORDINATOR_HOST environment variable → unicast (isolated networks / campus WiFi).
    2. UDP broadcast to 255.255.255.255    → auto-discover (mobile hotspot / home LAN).

    Raises:
        TimeoutError: If no valid coordinator response is received before timeout.
    """

    coordinatorHost = os.environ.get("COORDINATOR_HOST", "").strip()
    if coordinatorHost:
        return _discoverDirect(coordinatorHost, discovery_port, timeout_seconds)

    return _discoverBroadcast(broadcast_ip, discovery_port, timeout_seconds)


def _discoverBroadcast(
    broadcast_ip: str,
    discovery_port: int,
    timeout_seconds: float,
) -> DiscoveryResult:
    """Send LAN broadcast and wait for coordinator reply."""

    deadline = time.monotonic() + timeout_seconds

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))

        request = DISCOVERY_MESSAGE.encode("utf-8")
        sock.sendto(request, (broadcast_ip, discovery_port))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "No coordinator responded to discovery broadcast within "
                    f"{timeout_seconds:.1f}s. "
                    "Hint: if WiFi has AP isolation (campus / enterprise), "
                    "set COORDINATOR_HOST=<coordinator-ip> and retry."
                )

            sock.settimeout(remaining)

            try:
                responseData, _ = sock.recvfrom(4096)
            except socket.timeout as exc:
                raise TimeoutError(
                    "No coordinator responded to discovery broadcast within "
                    f"{timeout_seconds:.1f}s. "
                    "Hint: if WiFi has AP isolation (campus / enterprise), "
                    "set COORDINATOR_HOST=<coordinator-ip> and retry."
                ) from exc

            parsed = _parseDiscoveryResponse(responseData)
            if parsed is not None:
                return parsed


def _discoverDirect(
    coordinatorHost: str,
    discovery_port: int,
    timeout_seconds: float,
) -> DiscoveryResult:
    """Send unicast discovery to a known coordinator IP (fallback for isolated networks).

    This bypasses broadcast entirely: the worker sends the DISCOVER_CLUSTER
    message directly to the coordinator's IP.  Works on campus WiFi, enterprise
    networks, and any setup where broadcast is blocked.

    Raises:
        TimeoutError: If coordinator does not reply before timeout.
    """

    deadline = time.monotonic() + timeout_seconds

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 0))

        request = DISCOVERY_MESSAGE.encode("utf-8")
        sock.sendto(request, (coordinatorHost, discovery_port))

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"No reply from coordinator at {coordinatorHost}:{discovery_port}."
            )

        sock.settimeout(remaining)

        try:
            responseData, _ = sock.recvfrom(4096)
        except socket.timeout as exc:
            raise TimeoutError(
                f"Coordinator at {coordinatorHost}:{discovery_port} did not reply "
                f"within {timeout_seconds:.1f}s."
            ) from exc

        parsed = _parseDiscoveryResponse(responseData)
        if parsed is not None:
            return parsed

        # Coordinator address is known; build result directly even if response
        # body could not be parsed (e.g. non-standard reply).
        return DiscoveryResult(coordinatorIp=coordinatorHost, wsPort=DEFAULT_WS_PORT)


def _parseDiscoveryResponse(raw_bytes: bytes) -> DiscoveryResult | None:
    """Parse discovery response payload into DiscoveryResult."""

    payloadText = raw_bytes.decode("utf-8", errors="ignore").strip()

    # Primary protocol: JSON payload.
    try:
        payload = json.loads(payloadText)
        ip = str(payload.get("coordinatorIp") or payload["coordinator_ip"])
        wsPort = int(payload.get("wsPort", payload.get("ws_port", DEFAULT_WS_PORT)))
        return DiscoveryResult(coordinatorIp=ip, wsPort=wsPort)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    # Backward-compatible fallback: COORDINATOR:<ip>[:<port>]
    if payloadText.startswith("COORDINATOR:"):
        _, rawIp, *maybePort = payloadText.split(":")
        if not rawIp:
            return None

        wsPort = DEFAULT_WS_PORT
        if maybePort:
            try:
                wsPort = int(maybePort[0])
            except ValueError:
                return None

        return DiscoveryResult(coordinatorIp=rawIp, wsPort=wsPort)

    return None


if __name__ == "__main__":
    import sys

    t = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    mode = "unicast" if os.environ.get("COORDINATOR_HOST") else "broadcast"
    print(f"[discovery] mode={mode}, timeout={t}s")
    try:
        result = discoverCoordinator(timeout_seconds=t)
        print(f"[discovery] FOUND -> {result.websocketAddress}")
    except TimeoutError as e:
        print(f"[discovery] FAILED -> {e}")
        sys.exit(1)
