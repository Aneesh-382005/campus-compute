"""UDP discovery server for coordinator auto-discovery on a LAN."""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from typing import Optional

DISCOVERY_PORT = 9999
DEFAULT_API_PORT = 8000
DISCOVERY_MESSAGE = "DISCOVER_CLUSTER"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryConfig:
    """Configuration for the UDP discovery service."""

    host: str = "0.0.0.0"
    discovery_port: int = DISCOVERY_PORT
    api_port: int = DEFAULT_API_PORT


class CoordinatorDiscoveryServer:
    """Listens for worker discovery broadcasts and responds with connection info."""

    def __init__(self, config: Optional[DiscoveryConfig] = None) -> None:
        self.config = config or DiscoveryConfig()
        self._stopEvent = threading.Event()

    def stop(self) -> None:
        """Signal the server loop to stop."""

        self._stopEvent.set()

    def runForever(self) -> None:
        """Start listening for discovery requests and respond until stopped."""

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as serverSocket:
            serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            serverSocket.bind((self.config.host, self.config.discovery_port))
            serverSocket.settimeout(1.0)

            logger.info(
                "Discovery server listening on UDP %s:%s",
                self.config.host,
                self.config.discovery_port,
            )

            while not self._stopEvent.is_set():
                try:
                    data, workerAddr = serverSocket.recvfrom(4096)
                except socket.timeout:
                    continue

                message = data.decode("utf-8", errors="ignore").strip()
                if message != DISCOVERY_MESSAGE:
                    continue

                coordinatorIp = self._resolveCoordinatorIp(workerAddr[0])
                payload = {
                    "coordinator_ip": coordinatorIp,
                    "ws_port": self.config.api_port,
                }
                response = json.dumps(payload).encode("utf-8")
                serverSocket.sendto(response, workerAddr)

                logger.info(
                    "Handled discovery from %s:%s -> %s:%s",
                    workerAddr[0],
                    workerAddr[1],
                    coordinatorIp,
                    self.config.api_port,
                )

    def startInBackground(self, name: str = "discovery-server") -> threading.Thread:
        """Run the discovery server in a daemon thread and return it."""

        thread = threading.Thread(target=self.runForever, name=name, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _resolveCoordinatorIp(workerIp: str) -> str:
        """Find the local IP that can route traffic back to the requesting worker."""

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.connect((workerIp, 1))
                return probe.getsockname()[0]
            except OSError:
                # Fallback if route probing fails on an unusual network setup.
                return socket.gethostbyname(socket.gethostname())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    CoordinatorDiscoveryServer().runForever()
