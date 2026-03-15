"""
Campus Compute Coordinator
--------------------------
FastAPI application that wires together:
  - UDP discovery  (DiscoveryServer)
  - Worker registry (NodeRegistry)
  - Task queue     (JobManager)
  - Scheduler      (Scheduler)

WebSocket /ws handles both workers and dashboard clients.

Workers send:
  { "type": "REGISTER",     "nodeId": "...", "cpuCores": 4, "ramGb": 8.0, "gpuAvailable": false }
  { "type": "TASK_RESULT",  "taskId": "...", "jobId": "...", "nodeId": "...",
    "status": "completed"|"failed", "result": {}, "error": null }

Dashboard clients send:
  { "type": "SUBSCRIBE_DASHBOARD" }

Run with:
  uvicorn coordinator.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .NodeRegistry import NodeRegistry
from .JobManager import JobManager
from .scheduler import Scheduler
from .DiscoveryServer import CoordinatorDiscoveryServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# -- Pydantic message schemas -------------------------------------------------

class RegisterMessage(BaseModel):
    type: str
    nodeId: str
    cpuCores: int
    ramGb: float
    gpuAvailable: bool
    gpuVendor: Optional[str] = None
    gpuBackend: Optional[str] = None
    gpuRuntimeVersion: Optional[str] = None
    gpuCount: Optional[int] = 0
    gpuDevices: list[dict] = Field(default_factory=list)


class TaskResultMessage(BaseModel):
    type: str
    taskId: str
    jobId: str
    nodeId: str
    status: str               # "completed" | "failed"
    result: Optional[dict] = None
    error: Optional[str] = None


class SubmitJobRequest(BaseModel):
    taskType: str
    payload: dict = Field(default_factory=dict)
    jobId: Optional[str] = None


# -- App-level singletons -----------------------------------------------------

nodeRegistry = NodeRegistry()
jobManager = JobManager()
scheduler = Scheduler(nodeRegistry, jobManager)

# Clients that sent SUBSCRIBE_DASHBOARD — receive CLUSTER_STATE broadcasts.
dashboardClients: set[WebSocket] = set()


# -- Lifespan: start UDP discovery alongside FastAPI --------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    discoveryServer = CoordinatorDiscoveryServer()
    discoveryServer.startInBackground()
    logger.info("Coordinator started  |  UDP discovery active on port 9999")
    yield
    discoveryServer.stop()
    logger.info("Coordinator shutting down")


# -- FastAPI app --------------------------------------------------------------

app = FastAPI(title="Campus Compute Coordinator", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- HTTP routes --------------------------------------------------------------

@app.get("/status")
async def getStatus():
    """Snapshot of nodes, tasks, and job stats."""
    return {
        "nodes": [n.toDict() for n in nodeRegistry.getAllNodes()],
        "jobs": jobManager.getJobStats(),
        "tasks": [t.toDict() for t in jobManager.getAllTasks()],
    }


@app.post("/jobs", status_code=201)
async def submitJob(req: SubmitJobRequest):
    """Enqueue a new task and immediately attempt to dispatch it."""
    task = await jobManager.enqueueTask(req.taskType, req.payload, req.jobId)
    await scheduler.dispatchPending()
    await broadcastClusterState()
    return {
        "taskId": task.taskId,
        "jobId": task.jobId,
        "status": task.status.value,
    }


@app.post("/jobs/{taskId}/retry")
async def retryJob(taskId: str):
    """Re-queue a failed task."""
    requeued = await jobManager.requeueFailedTask(taskId)
    if not requeued:
        return {"error": "Task not found or not in failed state"}
    await scheduler.dispatchPending()
    await broadcastClusterState()
    return {"taskId": taskId, "status": "requeued"}


# -- WebSocket endpoint -------------------------------------------------------

@app.websocket("/ws")
async def websocketEndpoint(websocket: WebSocket):
    await websocket.accept()

    nodeId: Optional[str] = None
    isDashboard = False

    try:
        async for rawMessage in websocket.iter_text():
            try:
                data = json.loads(rawMessage)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "ERROR", "detail": "Invalid JSON"})
                )
                continue

            msgType = data.get("type", "")

            if msgType == "REGISTER":
                nodeId = await handleRegister(data, websocket)

            elif msgType == "TASK_RESULT":
                await handleTaskResult(data)

            elif msgType == "SUBSCRIBE_DASHBOARD":
                isDashboard = True
                dashboardClients.add(websocket)
                await websocket.send_text(json.dumps({"type": "SUBSCRIBED"}))
                await sendClusterStateTo(websocket)

            else:
                logger.warning("Unknown WebSocket message type: %s", msgType)

    except WebSocketDisconnect:
        pass
    finally:
        if nodeId:
            # Fail any tasks that were running on this worker.
            orphanedTasks = jobManager.getTasksAssignedTo(nodeId)
            for orphan in orphanedTasks:
                await jobManager.markTaskFailed(
                    orphan.taskId, f"Worker {nodeId} disconnected"
                )
            await nodeRegistry.unregister(nodeId)
            await scheduler.dispatchPending()
            await broadcastClusterState()
            logger.info("Worker %s disconnected; %d task(s) re-queued", nodeId, len(orphanedTasks))

        if isDashboard:
            dashboardClients.discard(websocket)


# -- WebSocket message handlers -----------------------------------------------

async def handleRegister(data: dict, websocket: WebSocket) -> str:
    msg = RegisterMessage(**data)
    await nodeRegistry.register(
        nodeId=msg.nodeId,
        cpuCores=msg.cpuCores,
        ramGb=msg.ramGb,
        gpuAvailable=msg.gpuAvailable,
        gpuVendor=msg.gpuVendor,
        gpuBackend=msg.gpuBackend,
        gpuRuntimeVersion=msg.gpuRuntimeVersion,
        gpuCount=msg.gpuCount or len(msg.gpuDevices),
        gpuDevices=msg.gpuDevices,
        websocket=websocket,
    )
    await websocket.send_text(json.dumps({
        "type": "REGISTER_ACK",
        "status": "ok",
        "nodeId": msg.nodeId,
    }))
    logger.info(
        "Worker registered: %s  CPU=%d  RAM=%.1fGB  GPU=%s  vendor=%s  backend=%s  runtime=%s  devices=%d",
        msg.nodeId,
        msg.cpuCores,
        msg.ramGb,
        msg.gpuAvailable,
        msg.gpuVendor,
        msg.gpuBackend,
        msg.gpuRuntimeVersion,
        msg.gpuCount or len(msg.gpuDevices),
    )
    await scheduler.dispatchPending()
    await broadcastClusterState()
    return msg.nodeId


async def handleTaskResult(data: dict) -> None:
    msg = TaskResultMessage(**data)
    if msg.status == "completed":
        await jobManager.markTaskCompleted(msg.taskId, msg.result or {})
    else:
        await jobManager.markTaskFailed(msg.taskId, msg.error or "Unknown error")
    await nodeRegistry.setNodeBusy(msg.nodeId, False)
    await scheduler.dispatchPending()
    await broadcastClusterState()


# -- Dashboard broadcasting ----------------------------------------------------

async def buildClusterStatePayload() -> str:
    return json.dumps({
        "type": "CLUSTER_STATE",
        "nodes": [n.toDict() for n in nodeRegistry.getAllNodes()],
        "jobs": jobManager.getJobStats(),
        "tasks": [t.toDict() for t in jobManager.getAllTasks()],
    })


async def sendClusterStateTo(websocket: WebSocket) -> None:
    try:
        await websocket.send_text(await buildClusterStatePayload())
    except Exception:
        dashboardClients.discard(websocket)


async def broadcastClusterState() -> None:
    if not dashboardClients:
        return
    stateJson = await buildClusterStatePayload()
    dead: set[WebSocket] = set()
    for client in list(dashboardClients):
        try:
            await client.send_text(stateJson)
        except Exception:
            dead.add(client)
    dashboardClients.difference_update(dead)
