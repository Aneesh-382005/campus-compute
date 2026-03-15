"""Registry of connected worker nodes."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WorkerNode:
    """Represents a single connected worker node."""

    nodeId: str
    cpuCores: int
    ramGb: float
    gpuAvailable: bool
    gpuVendor: Optional[str]
    gpuBackend: Optional[str]
    gpuRuntimeVersion: Optional[str]
    gpuCount: int
    gpuDevices: list[dict]
    websocket: WebSocket
    isBusy: bool = False
    connectedAt: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def toDict(self) -> dict:
        return {
            "nodeId": self.nodeId,
            "cpuCores": self.cpuCores,
            "ramGb": self.ramGb,
            "gpuAvailable": self.gpuAvailable,
            "gpuVendor": self.gpuVendor,
            "gpuBackend": self.gpuBackend,
            "gpuRuntimeVersion": self.gpuRuntimeVersion,
            "gpuCount": self.gpuCount,
            "gpuDevices": self.gpuDevices,
            "isBusy": self.isBusy,
            "connectedAt": self.connectedAt.isoformat(),
        }


class NodeRegistry:
    """Thread-safe (asyncio-safe) store of all connected workers."""

    def __init__(self) -> None:
        self._nodes: dict[str, WorkerNode] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        nodeId: str,
        cpuCores: int,
        ramGb: float,
        gpuAvailable: bool,
        gpuVendor: Optional[str],
        gpuBackend: Optional[str],
        gpuRuntimeVersion: Optional[str],
        gpuCount: int,
        gpuDevices: list[dict],
        websocket: WebSocket,
    ) -> WorkerNode:
        async with self._lock:
            node = WorkerNode(
                nodeId=nodeId,
                cpuCores=cpuCores,
                ramGb=ramGb,
                gpuAvailable=gpuAvailable,
                gpuVendor=gpuVendor,
                gpuBackend=gpuBackend,
                gpuRuntimeVersion=gpuRuntimeVersion,
                gpuCount=gpuCount,
                gpuDevices=gpuDevices,
                websocket=websocket,
            )
            self._nodes[nodeId] = node
            logger.info(
                "Node registered: %s  CPU=%d  RAM=%.1fGB  GPU=%s  vendor=%s  backend=%s  runtime=%s  devices=%d",
                nodeId,
                cpuCores,
                ramGb,
                gpuAvailable,
                gpuVendor,
                gpuBackend,
                gpuRuntimeVersion,
                gpuCount,
            )
            return node

    async def unregister(self, nodeId: str) -> None:
        async with self._lock:
            self._nodes.pop(nodeId, None)
            logger.info("Node unregistered: %s", nodeId)

    def getNode(self, nodeId: str) -> Optional[WorkerNode]:
        return self._nodes.get(nodeId)

    def getAvailableWorkers(self) -> list[WorkerNode]:
        """Return workers that are connected and not currently processing a task."""
        return [n for n in self._nodes.values() if not n.isBusy]

    def getAllNodes(self) -> list[WorkerNode]:
        return list(self._nodes.values())

    async def setNodeBusy(self, nodeId: str, busy: bool) -> None:
        async with self._lock:
            node = self._nodes.get(nodeId)
            if node:
                node.isBusy = busy

    async def failRunningTasksFor(self, nodeId: str) -> list[str]:
        """Return task IDs that were assigned to nodeId so caller can mark them failed."""
        node = self._nodes.get(nodeId)
        if node is None:
            return []
        # NodeRegistry does not know about tasks; caller resolves via JobManager.
        # This method is a hook so server can query JobManager and pass results back.
        return []

    def nodeCount(self) -> int:
        return len(self._nodes)
