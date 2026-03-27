# Campus Compute

Campus Compute is a LAN distributed compute platform with one coordinator, multiple workers, and a Next.js real-time dashboard.

> [!NOTE]
> This project is still a prototype and is actively evolving.
> Issues and improvement ideas are welcome, and collaborators are welcome.

## What This Project Does

- Auto-discovers the coordinator on local networks (UDP discovery).
- Lets workers register machine capabilities (CPU, RAM, GPU info).
- Accepts job submissions and routes tasks to available workers.
- Tracks task lifecycle (pending, running, completed, failed).
- Streams live updates to the dashboard over WebSocket.

## High-Level Flow

1. Worker starts and discovers coordinator.
2. Worker connects to coordinator WebSocket and sends REGISTER.
3. User submits job from API/dashboard.
4. Coordinator schedules task to an idle worker.
5. Worker executes task and sends TASK_RESULT.
6. Coordinator updates state and broadcasts CLUSTER_STATE.

## Main Components

- coordinator/: FastAPI server, worker registry, scheduler, task state, discovery server.
- worker/: worker runtime, discovery client, hardware detection, task execution loop.
- frontend/dashboard/: Next.js UI for live status and job submission.

## Run (Quick)

> [!IMPORTANT]
> Coordinator and workers must be on the same network, and the network must allow device-to-device discovery (no client/AP isolation).
> For the hackathon demo, we used a phone hotspot so all nodes could discover each other.

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Start coordinator:

```bash
uvicorn coordinator.server:app --host 0.0.0.0 --port 8000 --reload
```

3. Start worker on a different computer but the same Network:

```bash
python -m worker.worker
```

4. Start dashboard:

```bash
cd frontend/dashboard
npm install
npm run dev
```

Open http://localhost:3000