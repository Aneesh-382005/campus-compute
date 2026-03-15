# Cluster Dashboard

Real-time coordinator + worker cluster dashboard (Next.js + TailwindCSS + Recharts).

## Setup

1. Start coordinator backend at `http://127.0.0.1:8000`.
2. In this folder:
	- `npm install`
	- `npm run dev`
3. Open `http://localhost:3000`

## Environment variables (optional)

- `NEXT_PUBLIC_COORDINATOR_WS` (default: `ws://127.0.0.1:8000/ws`)
- `NEXT_PUBLIC_COORDINATOR_HTTP` (default: `http://127.0.0.1:8000`)
- `COORDINATOR_HTTP_BASE_URL` for server-side API proxy routes

## What you can do

- Monitor cluster nodes (CPU, RAM, GPU vendor/backend, status)
- See active tasks by worker in real time
- Use **Worker View** to inspect every task received by a selected worker
- View capacity and task status charts
- Submit jobs from the UI
