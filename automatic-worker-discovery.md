# Add Automatic Worker Discovery

## Goal

Workers should join the cluster without manually entering the coordinator IP.

## Approach

Use LAN broadcast discovery.

## Discovery Flow

```text
Worker starts
      |
broadcast discovery packet
      |
Coordinator responds
      |
Worker connects via WebSocket
```

This is a common pattern in distributed systems for local cluster discovery.

## Technologies Used

- UDP broadcast
- Python socket
- Local network discovery

## Discovery Architecture

```text
Coordinator
   |
UDP Discovery Server
   |
----------------------------
| Worker | Worker | Worker |
----------------------------
```

## Protocol Flow

- Worker sends: `DISCOVER_COORDINATOR`
- Coordinator responds: `COORDINATOR_IP`
- Worker connects to WebSocket

## Discovery Ports

Use fixed ports:

- UDP Discovery Port: `9999`
- Coordinator API Port: `8000`

## Worker Discovery Process

Worker boot sequence:

```text
start worker
↓
detect hardware
↓
send UDP broadcast
↓
receive coordinator address
↓
connect WebSocket
↓
register node
```

Example broadcast:

```text
DISCOVER_CLUSTER
```

Coordinator reply:

```text
COORDINATOR:192.168.1.10
```

Worker then connects to:

```text
ws://192.168.1.10:8000/ws
```

## Discovery Implementation

### Coordinator UDP Listener

Responsibilities:

- Listen for broadcasts
- Respond with coordinator IP

Python concept:

```python
socket.recvfrom()
socket.sendto()
```

### Worker Broadcast

Responsibilities:

- Send discovery packet
- Wait for response

Worker sends broadcast to:

```text
255.255.255.255:9999
```

## Final Locked Architecture

After adding discovery, do not expand scope further.

System components:

1. Discovery service
2. Coordinator
3. Worker nodes
4. Container executor
5. Distributed tasks
6. Dashboard

Constraints:

- No additional features
- No autoscaling
- No cloud deployment
- Focus on a working cluster demo

## Final Repository Structure

```text
campus-compute/
├── README.md
├── requirements.txt
├── coordinator/
│   ├── server.py
│   ├── node_registry.py
│   ├── scheduler.py
│   ├── job_manager.py
│   └── discovery_server.py
├── worker/
│   ├── worker.py
│   ├── hardware.py
│   ├── executor.py
│   ├── docker_runner.py
│   └── discovery_client.py
├── tasks/
│   ├── image_tile/
│   │   ├── Dockerfile
│   │   └── process_tile.py
│   └── monte_carlo/
│       ├── Dockerfile
│       └── simulate.py
├── shared/
│   ├── messages.py
│   └── models.py
├── frontend/
│   └── dashboard/
└── docs/
    └── architecture.md
```

## Builder Prompts for Each Component

These prompts can be given to teammates or used with an AI coding tool.

### Component 1: Coordinator Core

Files:

- `coordinator/server.py`
- `coordinator/node_registry.py`
- `coordinator/scheduler.py`
- `coordinator/job_manager.py`

Builder prompt:

> Build a distributed compute coordinator using Python and FastAPI.
>
> Features:
>
> 1. WebSocket server at `/ws` for workers and dashboard clients.
> 2. Worker registration system. Workers send `REGISTER` message containing:
>    - `node_id`
>    - `cpu_cores`
>    - `ram_gb`
>    - `gpu_available`
> 3. Maintain a node registry storing all connected workers.
> 4. Implement a task queue.
> 5. Scheduler assigns tasks to workers based on hardware metadata.
> 6. Receive `TASK_RESULT` messages from workers.
> 7. Track job progress and completed tasks.
> 8. Broadcast cluster state updates to dashboard clients.
>
> Use `asyncio` for concurrency and Pydantic models for message schemas.
>
> Code structure should separate:
> - server logic
> - node registry
> - task scheduler
> - job manager

### Component 2: Discovery Service

Files:

- `coordinator/discovery_server.py`
- `worker/discovery_client.py`

Builder prompt:

> Implement automatic cluster discovery using UDP broadcast.
>
> Coordinator side:
> Run a UDP server listening on port `9999`.
> When receiving message `"DISCOVER_CLUSTER"`, respond with the coordinator's IP and API port.
>
> Worker side:
> Send UDP broadcast message `"DISCOVER_CLUSTER"` to `255.255.255.255:9999`.
> Wait for coordinator response.
> Extract coordinator IP and WebSocket port.
>
> Return connection address so worker can connect to `ws://COORDINATOR_IP:8000/ws`.
>
> Ensure timeout handling if no coordinator responds.

### Component 3: Worker Node

Files:

- `worker/worker.py`
- `worker/hardware.py`
- `worker/executor.py`

Builder prompt:

> Build a distributed compute worker client in Python.
>
> Responsibilities:
>
> 1. Discover coordinator using UDP broadcast.
> 2. Detect system hardware using `psutil`:
>    - CPU cores
>    - RAM
> 3. Detect GPU availability using `torch.cuda.is_available()`.
> 4. Connect to coordinator WebSocket endpoint.
> 5. Send `REGISTER` message with hardware metadata.
> 6. Wait for `TASK_ASSIGN` messages.
> 7. Execute tasks using the executor module.
> 8. Send `TASK_RESULT` messages with output.
>
> Worker should continuously request tasks when idle.
>
> Ensure robust reconnect logic if connection drops.

### Component 4: Docker Task Executor

Files:

- `worker/docker_runner.py`
- `worker/executor.py`

Builder prompt:

> Implement container-based task execution for distributed workers.
>
> Tasks contain:
> - Docker image
> - command
> - input data path
>
> Worker execution flow:
>
> 1. Pull Docker image if not available locally.
> 2. Run container using `docker run`.
> 3. Mount input and output directories.
> 4. If GPU is available, allow GPU access using `--gpus all`.
> 5. Capture container stdout and exit code.
> 6. Return result to coordinator.
>
> Use Python `subprocess` to run Docker commands.
> Ensure containers are removed after execution using `--rm`.

### Component 5: Task Implementations

Files:

- `tasks/image_tile/`
- `tasks/monte_carlo/`

Builder prompt:

> Create containerized tasks for distributed execution.
>
> Task 1: image tile processing
> - Input: large image
> - Split image into tiles
> - Each worker processes a tile
> - Return processed tile
>
> Task 2: Monte Carlo simulation
> - Input: number of simulations
> - Worker performs subset of simulations
> - Return aggregated result
>
> Each task should have:
> - Dockerfile
> - Python execution script
>
> Ensure container outputs results to mounted output directory.

### Component 6: Dashboard

Files:

- `frontend/dashboard/`

Builder prompt:

> Build a real-time cluster dashboard using React or Next.js.
>
> Features:
>
> 1. Connect to coordinator using WebSocket.
> 2. Display cluster nodes:
>    - `node_id`
>    - `cpu`
>    - `ram`
>    - `gpu availability`
>    - `status`
> 3. Show active tasks running on each worker.
> 4. Show cluster capacity summary:
>    - total CPU cores
>    - total RAM
>    - GPU nodes
> 5. Provide simple job submission form.
>
> Use TailwindCSS for UI and Recharts or Chart.js for visualization.
> Ensure real-time updates using WebSocket events.

## Final Build Order

Build components in this order:

1. Discovery service
2. Coordinator WebSocket server
3. Worker registration
4. Docker executor
5. Simple task execution
6. Dashboard visualization

If step 4 works, the system is already a functional distributed compute cluster.

## What the Judges Will See

Demo sequence:

1. Start coordinator
2. Start workers on multiple machines
3. Workers auto-discover cluster
4. Dashboard shows nodes joining
5. Submit distributed job
6. Containers run across machines
7. Results aggregated

This clearly demonstrates distributed container orchestration across a local compute cluster.
