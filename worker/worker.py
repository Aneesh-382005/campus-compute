"""
Campus Compute Worker
---------------------
Boot sequence:
  1. Detect hardware (CPU, RAM, GPU)
  2. Discover coordinator via UDP broadcast / unicast
  3. Connect to coordinator WebSocket
  4. Send REGISTER message
  5. Listen for TASK_ASSIGN  →  execute  →  send TASK_RESULT
  6. On disconnect: exponential-backoff reconnect

Run:
  python -m worker.worker
  # or with a known coordinator IP:
  COORDINATOR_HOST=192.168.1.100 python -m worker.worker
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import uuid

import websockets
from websockets.exceptions import ConnectionClosed

from .DiscoveryClient import discoverCoordinator
from .hardware import detectHardware
from .executor import executeTask

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NODE_ID: str = os.environ.get(
    "NODE_ID",
    f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}",
)
DISCOVERY_TIMEOUT: float = float(os.environ.get("DISCOVERY_TIMEOUT", "8"))
RECONNECT_BASE_DELAY: float = 1.0   # seconds before first retry
RECONNECT_MAX_DELAY: float = 30.0   # cap on backoff ceiling
RECONNECT_MAX_ATTEMPTS: int = 0     # 0 = retry forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [worker]  %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run() -> None:
    """Detect hardware once, then connect and stay connected."""

    hardware = detectHardware(NODE_ID)
    logger.info(
        "Node: %s  |  CPU=%d  RAM=%.2fGB  GPU=%s  vendor=%s  backend=%s  runtime=%s  devices=%d",
        hardware.nodeId,
        hardware.cpuCores,
        hardware.ramGb,
        hardware.gpuAvailable,
        hardware.gpuVendor,
        hardware.gpuBackend,
        hardware.gpuRuntimeVersion,
        hardware.gpuCount,
    )

    wsAddress = await _resolveCoordinatorAddress()
    logger.info("Coordinator WebSocket: %s", wsAddress)

    attempt = 0
    delay = RECONNECT_BASE_DELAY

    while True:
        attempt += 1
        if RECONNECT_MAX_ATTEMPTS and attempt > RECONNECT_MAX_ATTEMPTS:
            logger.error("Max reconnect attempts (%d) reached. Exiting.", RECONNECT_MAX_ATTEMPTS)
            sys.exit(1)

        try:
            logger.info("Connecting (attempt %d) -> %s", attempt, wsAddress)
            async with websockets.connect(wsAddress) as ws:
                attempt = 1          # reset counter after successful connection
                delay = RECONNECT_BASE_DELAY
                await _runSession(ws, hardware)

        except ConnectionClosed as exc:
            logger.warning("Connection closed: %s", exc)
        except OSError as exc:
            logger.warning("Connection error: %s", exc)
        except Exception as exc:
            logger.error("Unexpected error: %s", exc)

        logger.info("Reconnecting in %.1fs ...", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_DELAY)


# ---------------------------------------------------------------------------
# Session: register then process tasks
# ---------------------------------------------------------------------------

async def _runSession(ws, hardware) -> None:
    """Handle one continuous WebSocket session."""

    await _register(ws, hardware)
    logger.info("Registered with coordinator. Waiting for tasks ...")

    async for rawMessage in ws:
        try:
            data = json.loads(rawMessage)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message, ignoring")
            continue

        msgType = data.get("type", "")

        if msgType == "TASK_ASSIGN":
            await _handleTaskAssign(ws, data)

        elif msgType == "REGISTER_ACK":
            # Ack may arrive here if coordinator sends it after some queued messages.
            logger.info("REGISTER_ACK confirmed by coordinator")

        elif msgType == "ERROR":
            logger.error("Coordinator error: %s", data.get("detail", data))

        else:
            logger.debug("Unhandled message type: %s", msgType)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

async def _register(ws, hardware) -> None:
    registerMsg = json.dumps({
        "type": "REGISTER",
        "nodeId": hardware.nodeId,
        "cpuCores": hardware.cpuCores,
        "ramGb": hardware.ramGb,
        "gpuAvailable": hardware.gpuAvailable,
        "gpuVendor": hardware.gpuVendor,
        "gpuBackend": hardware.gpuBackend,
        "gpuRuntimeVersion": hardware.gpuRuntimeVersion,
        "gpuCount": hardware.gpuCount,
        "gpuDevices": hardware.gpuDevices,
    })
    await ws.send(registerMsg)
    logger.info("REGISTER sent for node: %s", hardware.nodeId)

    # Wait for ACK with a short deadline.
    try:
        async with asyncio.timeout(10):
            raw = await ws.recv()
            ack = json.loads(raw)
            if ack.get("type") == "REGISTER_ACK":
                logger.info("REGISTER_ACK received")
            else:
                # Could be a TASK_ASSIGN that arrived immediately; put back in
                # the pipeline by raising so _runSession handles it.
                logger.debug("First message after register was type=%s", ack.get("type"))
    except TimeoutError:
        logger.warning("No REGISTER_ACK within 10s; continuing anyway")


# ---------------------------------------------------------------------------
# Task assignment handler
# ---------------------------------------------------------------------------

async def _handleTaskAssign(ws, data: dict) -> None:
    taskId = data.get("taskId", "unknown")
    jobId = data.get("jobId", "unknown")
    taskType = data.get("taskType", "unknown")
    payload = data.get("payload", {})

    logger.info("TASK_ASSIGN received: taskId=%s  type=%s", taskId, taskType)

    try:
        result = await executeTask(taskType, payload)
        await _sendResult(ws, taskId, jobId, "completed", result=result)
        logger.info("Task %s completed", taskId)

    except Exception as exc:
        errorMsg = f"{type(exc).__name__}: {exc}"
        logger.error("Task %s failed: %s", taskId, errorMsg)
        await _sendResult(ws, taskId, jobId, "failed", error=errorMsg)


async def _sendResult(
    ws,
    taskId: str,
    jobId: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    msg = json.dumps({
        "type": "TASK_RESULT",
        "taskId": taskId,
        "jobId": jobId,
        "nodeId": NODE_ID,
        "status": status,
        "result": result,
        "error": error,
    })
    await ws.send(msg)


# ---------------------------------------------------------------------------
# Discovery with retry
# ---------------------------------------------------------------------------

async def _resolveCoordinatorAddress() -> str:
    """Discover coordinator; retry with backoff until found."""

    delay = RECONNECT_BASE_DELAY
    attempt = 0

    while True:
        attempt += 1
        try:
            result = await asyncio.to_thread(
                discoverCoordinator, DISCOVERY_TIMEOUT
            )
            logger.info(
                "Coordinator discovered: %s (attempt %d)",
                result.websocketAddress, attempt,
            )
            return result.websocketAddress

        except TimeoutError as exc:
            logger.warning("Discovery attempt %d failed: %s", attempt, exc)
            logger.info("Retrying discovery in %.1fs ...", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
