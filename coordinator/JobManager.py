"""Task queue, assignment tracking, and job progress management."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """A single unit of work in the compute cluster."""

    taskId: str
    jobId: str
    taskType: str
    payload: dict
    status: TaskStatus = TaskStatus.PENDING
    assignedTo: Optional[str] = None
    createdAt: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completedAt: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None

    def toDict(self) -> dict:
        return {
            "taskId": self.taskId,
            "jobId": self.jobId,
            "taskType": self.taskType,
            "payload": self.payload,
            "status": self.status.value,
            "assignedTo": self.assignedTo,
            "createdAt": self.createdAt.isoformat(),
            "completedAt": (
                self.completedAt.isoformat() if self.completedAt else None
            ),
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Manages the task queue and tracks job lifecycle."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    # ── Enqueue ──────────────────────────────────────────────────────────────

    async def enqueueTask(
        self,
        taskType: str,
        payload: dict,
        jobId: Optional[str] = None,
    ) -> Task:
        async with self._lock:
            taskId = str(uuid.uuid4())
            resolvedJobId = jobId or str(uuid.uuid4())
            task = Task(
                taskId=taskId,
                jobId=resolvedJobId,
                taskType=taskType,
                payload=payload,
            )
            self._tasks[taskId] = task
            logger.info(
                "Task enqueued: %s  type=%s  job=%s",
                taskId, taskType, resolvedJobId,
            )
            return task

    # ── Query ─────────────────────────────────────────────────────────────────

    def getNextPendingTask(self) -> Optional[Task]:
        """Return the oldest PENDING task, or None if queue is empty."""
        for task in self._tasks.values():
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def getTaskById(self, taskId: str) -> Optional[Task]:
        return self._tasks.get(taskId)

    def getAllTasks(self) -> list[Task]:
        return list(self._tasks.values())

    def getTasksAssignedTo(self, nodeId: str) -> list[Task]:
        """Return all RUNNING tasks currently assigned to a specific worker."""
        return [
            t for t in self._tasks.values()
            if t.assignedTo == nodeId and t.status == TaskStatus.RUNNING
        ]

    def getJobStats(self) -> dict:
        tasks = list(self._tasks.values())
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED),
        }

    # ── State transitions ─────────────────────────────────────────────────────

    async def markTaskRunning(self, taskId: str, nodeId: str) -> None:
        async with self._lock:
            task = self._tasks.get(taskId)
            if task:
                task.status = TaskStatus.RUNNING
                task.assignedTo = nodeId

    async def markTaskCompleted(self, taskId: str, result: dict) -> None:
        async with self._lock:
            task = self._tasks.get(taskId)
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completedAt = datetime.now(timezone.utc)
                logger.info("Task completed: %s", taskId)

    async def markTaskFailed(self, taskId: str, error: str) -> None:
        async with self._lock:
            task = self._tasks.get(taskId)
            if task:
                task.status = TaskStatus.FAILED
                task.error = error
                task.completedAt = datetime.now(timezone.utc)
                logger.warning("Task failed: %s — %s", taskId, error)

    async def requeueFailedTask(self, taskId: str) -> bool:
        """Reset a FAILED task to PENDING so it can be retried."""
        async with self._lock:
            task = self._tasks.get(taskId)
            if task and task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.assignedTo = None
                task.error = None
                task.completedAt = None
                logger.info("Task requeued for retry: %s", taskId)
                return True
            return False
