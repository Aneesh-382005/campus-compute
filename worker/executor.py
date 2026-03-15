"""Task executor: dispatches TASK_ASSIGN payloads to handler functions.

Add new task types by registering a handler with @taskHandler("your_type").
Each handler receives the full task payload dict and returns a result dict.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# Registry: taskType -> async handler(payload) -> result dict
_handlers: dict[str, Callable[[dict], Awaitable[dict]]] = {}


def taskHandler(taskType: str):
    """Decorator to register an async function as a handler for a task type."""

    def decorator(fn: Callable[[dict], Awaitable[dict]]):
        _handlers[taskType] = fn
        logger.debug("Registered handler for task type: %s", taskType)
        return fn

    return decorator


async def executeTask(taskType: str, payload: dict) -> dict:
    """Run the handler for taskType with the given payload.

    Returns a result dict on success.
    Raises RuntimeError if taskType is unknown.
    Propagates any exception thrown by the handler.
    """

    handler = _handlers.get(taskType)
    if handler is None:
        raise RuntimeError(
            f"No handler registered for task type '{taskType}'. "
            f"Known types: {list(_handlers.keys())}"
        )

    logger.info("Executing task type: %s", taskType)
    startTime = time.monotonic()
    result = await handler(payload)
    elapsed = time.monotonic() - startTime
    logger.info("Task type '%s' completed in %.3fs", taskType, elapsed)
    return result


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------

@taskHandler("echo")
async def _handleEcho(payload: dict) -> dict:
    """Return the payload back as-is. Useful for smoke testing."""
    return {"echo": payload}


@taskHandler("sleep")
async def _handleSleep(payload: dict) -> dict:
    """Sleep for requested seconds (default 1). Simulates compute work."""
    seconds = float(payload.get("seconds", 1))
    await asyncio.sleep(seconds)
    return {"slept": seconds}


@taskHandler("image_preprocess")
async def _handleImagePreprocess(payload: dict) -> dict:
    """Stub for image preprocessing — replace with real logic later."""
    await asyncio.sleep(float(payload.get("simulatedDurationSeconds", 0.5)))
    return {
        "status": "preprocessed",
        "inputPath": payload.get("inputPath", "<none>"),
        "outputPath": payload.get("outputPath", "<none>"),
    }


@taskHandler("inference")
async def _handleInference(payload: dict) -> dict:
    """Stub for AI inference — replace with real model call later."""
    await asyncio.sleep(float(payload.get("simulatedDurationSeconds", 1.0)))
    return {
        "status": "inferred",
        "modelId": payload.get("modelId", "<none>"),
        "predictions": [],
    }


@taskHandler("training_step")
async def _handleTrainingStep(payload: dict) -> dict:
    """Stub for a single training step — replace with real training loop later."""
    await asyncio.sleep(float(payload.get("simulatedDurationSeconds", 2.0)))
    return {
        "status": "step_complete",
        "epoch": payload.get("epoch", 0),
        "loss": None,
    }
