# Cluster Dashboard

A real-time cluster monitoring dashboard (Next.js + TailwindCSS + Recharts). 

## Setup

1. `cd dashboard`
2. `npm install`
3. From one terminal: `npm run ws-server`
4. From another terminal: `npm run dev`

Open http://localhost:3000

## Features

- WebSocket connection to coordinator (`ws://localhost:4000`)
- Nodes table (node_id, cpu, ram, gpu availability, status)
- Active tasks listing
- Cluster capacity summary
- Live charts for CPU/RAM usage
- Simple job form POST to `/api/submit-job`

## Notes

This demo currently uses a local WS simulator in `ws-server.js`. Replace with your real coordinator endpoint as needed.
