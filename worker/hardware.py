"""Hardware detection utilities using psutil, torch, and GPU CLI fallbacks."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HardwareProfile:
    """Snapshot of local machine hardware capabilities."""

    nodeId: str
    cpuCores: int
    ramGb: float
    gpuAvailable: bool
    gpuVendor: str | None
    gpuBackend: str | None
    gpuRuntimeVersion: str | None
    gpuCount: int
    gpuDevices: list[dict]

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
        }


def detectHardware(nodeId: str) -> HardwareProfile:
    """Detect CPU cores, RAM, and GPU availability on the local machine."""

    cpuCores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
    ramGb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    gpuInfo = _detectGpuInfo()

    profile = HardwareProfile(
        nodeId=nodeId,
        cpuCores=cpuCores,
        ramGb=ramGb,
        gpuAvailable=gpuInfo["gpuAvailable"],
        gpuVendor=gpuInfo["gpuVendor"],
        gpuBackend=gpuInfo["gpuBackend"],
        gpuRuntimeVersion=gpuInfo["gpuRuntimeVersion"],
        gpuCount=gpuInfo["gpuCount"],
        gpuDevices=gpuInfo["gpuDevices"],
    )

    logger.info(
        "Hardware detected: CPU=%d cores  RAM=%.2fGB  GPU=%s  vendor=%s  backend=%s  runtime=%s  devices=%d",
        cpuCores,
        ramGb,
        profile.gpuAvailable,
        profile.gpuVendor,
        profile.gpuBackend,
        profile.gpuRuntimeVersion,
        profile.gpuCount,
    )
    return profile


def _detectGpuInfo() -> dict:
    """Detect GPU availability, backend (CUDA/ROCm), and VRAM details.

    Notes:
    - PyTorch uses torch.cuda APIs for both CUDA and ROCm builds.
    - On ROCm builds, torch.version.hip is usually populated.
    """
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            # Torch installed but no active CUDA/ROCm device.
            return _fallbackGpuInfo()

        backend = "cuda"
        runtimeVersion = getattr(torch.version, "cuda", None)
        if getattr(torch.version, "hip", None):
            backend = "rocm"
            runtimeVersion = getattr(torch.version, "hip", None)

        devices: list[dict] = []
        deviceCount = torch.cuda.device_count()
        for idx in range(deviceCount):
            props = torch.cuda.get_device_properties(idx)
            totalVramBytes = int(getattr(props, "total_memory", 0))
            totalVramGb = round(totalVramBytes / (1024 ** 3), 2)
            deviceName = torch.cuda.get_device_name(idx)

            freeVramBytes = None
            freeVramGb = None
            try:
                if hasattr(torch.cuda, "mem_get_info"):
                    free, _total = torch.cuda.mem_get_info(idx)
                    freeVramBytes = int(free)
                    freeVramGb = round(freeVramBytes / (1024 ** 3), 2)
            except Exception:
                # Non-fatal; some backends/environments do not expose per-device free VRAM.
                pass

            deviceInfo = {
                "index": idx,
                "name": deviceName,
                "vendor": _inferVendor(deviceName, backend),
                "totalVramBytes": totalVramBytes,
                "totalVramGb": totalVramGb,
                "freeVramBytes": freeVramBytes,
                "freeVramGb": freeVramGb,
            }
            devices.append(deviceInfo)

        vendor = devices[0].get("vendor") if devices else _inferVendor("", backend)
        logger.info(
            "GPU detected via torch: vendor=%s backend=%s runtime=%s devices=%d",
            vendor,
            backend,
            runtimeVersion,
            len(devices),
        )
        return {
            "gpuAvailable": True,
            "gpuVendor": vendor,
            "gpuBackend": backend,
            "gpuRuntimeVersion": runtimeVersion,
            "gpuCount": len(devices),
            "gpuDevices": devices,
        }
    except ImportError:
        logger.debug("torch not installed — trying CLI fallback detection")
        return _fallbackGpuInfo()
    except Exception as exc:
        logger.warning("GPU detection error (torch path): %s", exc)
        return _fallbackGpuInfo()


def _fallbackGpuInfo() -> dict:
    """Fallback GPU detection via vendor CLIs if torch path is unavailable."""

    nvidiaInfo = _detectViaNvidiaSmi()
    if nvidiaInfo is not None:
        return nvidiaInfo

    rocmInfo = _detectViaRocmSmi()
    if rocmInfo is not None:
        return rocmInfo

    return {
        "gpuAvailable": False,
        "gpuVendor": None,
        "gpuBackend": None,
        "gpuRuntimeVersion": None,
        "gpuCount": 0,
        "gpuDevices": [],
    }


def _detectViaNvidiaSmi() -> dict | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None

    try:
        cmd = [
            exe,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception as exc:
        logger.debug("nvidia-smi detection failed: %s", exc)
        return None

    devices: list[dict] = []
    for idx, line in enumerate(completed.stdout.strip().splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, totalMbRaw, driverVersion = parts[0], parts[1], parts[2]
        try:
            totalMb = int(float(totalMbRaw))
        except ValueError:
            totalMb = 0
        totalBytes = totalMb * 1024 * 1024
        devices.append(
            {
                "index": idx,
                "name": name,
                "vendor": "nvidia",
                "totalVramBytes": totalBytes,
                "totalVramGb": round(totalBytes / (1024 ** 3), 2),
                "driverVersion": driverVersion,
            }
        )

    if not devices:
        return None

    return {
        "gpuAvailable": True,
        "gpuVendor": "nvidia",
        "gpuBackend": "cuda",
        "gpuRuntimeVersion": devices[0].get("driverVersion"),
        "gpuCount": len(devices),
        "gpuDevices": devices,
    }


def _detectViaRocmSmi() -> dict | None:
    exe = shutil.which("rocm-smi")
    if not exe:
        return None

    # rocm-smi output is distro/version dependent. Keep parser permissive.
    try:
        completed = subprocess.run(
            [exe, "--showproductname"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception as exc:
        logger.debug("rocm-smi detection failed: %s", exc)
        return None

    devices: list[dict] = []
    for line in completed.stdout.splitlines():
        lower = line.lower()
        if "card" in lower and ("gpu" in lower or "product" in lower):
            devices.append(
                {
                    "index": len(devices),
                    "name": line.strip(),
                    "vendor": "amd",
                    # rocm-smi parsing for VRAM varies widely; unknown if not available.
                    "totalVramBytes": None,
                    "totalVramGb": None,
                }
            )

    if not devices:
        return None

    return {
        "gpuAvailable": True,
        "gpuVendor": "amd",
        "gpuBackend": "rocm",
        "gpuRuntimeVersion": None,
        "gpuCount": len(devices),
        "gpuDevices": devices,
    }


def _inferVendor(deviceName: str, backend: str | None) -> str:
    lower = deviceName.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "amd" in lower or "radeon" in lower:
        return "amd"
    if "intel" in lower:
        return "intel"
    if backend == "rocm":
        return "amd"
    if backend == "cuda":
        return "nvidia"
    return "unknown"
