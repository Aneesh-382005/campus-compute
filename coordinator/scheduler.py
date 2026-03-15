"""Hardware-aware task scheduler: assigns pending tasks to available workers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .NodeRegistry import NodeRegistry, WorkerNode
    from .JobManager import JobManager, Task

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Dispatches pending tasks to the best available worker.

    Selection priority
    ------------------
    1. If task payload has ``requiresGpu=True``  -> prefer GPU-capable workers.
    2. If task payload has ``minRamGb``           -> skip workers below that threshold.
    3. Among eligible workers                     -> pick the one with most CPU cores
       then most RAM (maximises utilisation of idle high-end nodes).
    """

    def __init__(
        self,
        nodeRegistry: "NodeRegistry",
        jobManager: "JobManager",
    ) -> None:
        self.nodeRegistry = nodeRegistry
        self.jobManager = jobManager

    # -- Public ---------------------------------------------------------------

    async def dispatchPending(self) -> None:
        """
        Drain the pending task queue by assigning each task to the best
        available worker.  Stops when either queue or workers are exhausted.
        """
        while True:
            pendingTask = self.jobManager.getNextPendingTask()
            if pendingTask is None:
                break

            availableWorkers = self.nodeRegistry.getAvailableWorkers()
            if not availableWorkers:
                pendingCount = self.jobManager.getJobStats()["pending"]
                logger.debug(
                    "No idle workers available; %d task(s) remain pending",
                    pendingCount,
                )
                break

            selectedWorker = self._selectWorker(pendingTask, availableWorkers)
            if selectedWorker is None:
                logger.debug(
                    "No eligible worker for task %s - staying in queue",
                    pendingTask.taskId,
                )
                break

            await self._assignTask(pendingTask, selectedWorker)

    # -- Private --------------------------------------------------------------

    def _selectWorker(
        self,
        task: "Task",
        workers: list["WorkerNode"],
    ) -> Optional["WorkerNode"]:
        requiresGpu = bool(task.payload.get("requiresGpu", False))
        minRamGb = float(task.payload.get("minRamGb", 0))

        eligible = [w for w in workers if w.ramGb >= minRamGb]
        if not eligible:
            # Relax RAM requirement rather than permanently stall the queue.
            eligible = workers

        if requiresGpu:
            gpuWorkers = [w for w in eligible if w.gpuAvailable]
            if gpuWorkers:
                return max(gpuWorkers, key=lambda w: (w.cpuCores, w.ramGb))
            # No GPU worker available right now; keep task pending.
            logger.debug(
                "Task %s requires GPU but no GPU worker is idle",
                task.taskId,
            )
            return None

        return max(eligible, key=lambda w: (w.cpuCores, w.ramGb))

    async def _assignTask(
        self,
        task: "Task",
        worker: "WorkerNode",
    ) -> None:
        """Transition task to RUNNING, mark worker busy, push over WebSocket."""
        await self.jobManager.markTaskRunning(task.taskId, worker.nodeId)
        await self.nodeRegistry.setNodeBusy(worker.nodeId, True)

        message = json.dumps({
            "type": "TASK_ASSIGN",
            "taskId": task.taskId,
            "jobId": task.jobId,
            "taskType": task.taskType,
            "payload": task.payload,
        })

        try:
            await worker.websocket.send_text(message)
            logger.info(
                "Task %s  assigned to worker %s",
                task.taskId, worker.nodeId,
            )
        except Exception as exc:
            # Worker disconnected mid-dispatch; roll back.
            logger.error(
                "Dispatch failed for task %s -> worker %s: %s",
                task.taskId, worker.nodeId, exc,
            )
            await self.jobManager.markTaskFailed(
                task.taskId, f"Dispatch error: {exc}"
            )
            await self.nodeRegistry.setNodeBusy(worker.nodeId, False)
