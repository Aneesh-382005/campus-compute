const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 4000 });

const createNode = (id) => ({
  node_id: `node-${id}`,
  cpu: { total: 16, used: Math.floor(Math.random() * 16) },
  ram: { total: 64000, used: Math.floor(Math.random() * 64000) },
  gpu: { available: Math.random() > 0.5 },
  status: ['online', 'idle', 'busy'][Math.floor(Math.random() * 3)],
});

const createTask = (id, node) => ({
  task_id: `task-${id}`,
  worker_id: node.node_id,
  cpu: Math.ceil(Math.random() * 4),
  ram: 256 * Math.ceil(Math.random() * 8),
  status: ['running', 'queued', 'completed'][Math.floor(Math.random() * 3)],
});

let nodes = [
  {
    node_id: 'node-1',
    cpu: { total: 16, used: 6 },
    ram: { total: 64000, used: 24000 },
    gpu: { available: true },
    status: 'online',
  },
  {
    node_id: 'node-2',
    cpu: { total: 16, used: 9 },
    ram: { total: 64000, used: 38000 },
    gpu: { available: false },
    status: 'busy',
  },
  {
    node_id: 'node-3',
    cpu: { total: 16, used: 3 },
    ram: { total: 64000, used: 18000 },
    gpu: { available: true },
    status: 'idle',
  },
  {
    node_id: 'node-4',
    cpu: { total: 16, used: 12 },
    ram: { total: 64000, used: 52000 },
    gpu: { available: false },
    status: 'online',
  },
];
let taskId = 5;
let tasks = [
  { task_id: 'task-1', worker_id: 'node-1', cpu: 2, ram: 1024, status: 'running' },
  { task_id: 'task-2', worker_id: 'node-2', cpu: 4, ram: 4096, status: 'running' },
  { task_id: 'task-3', worker_id: 'node-3', cpu: 1, ram: 512, status: 'queued' },
  { task_id: 'task-4', worker_id: 'node-4', cpu: 6, ram: 8192, status: 'completed' },
];

function broadcast(payload) {
  const payloadStr = JSON.stringify(payload);
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payloadStr);
    }
  });
}

wss.on('connection', (ws) => {
  ws.send(JSON.stringify({ type: 'cluster_snapshot', nodes, tasks }));

  const interval = setInterval(() => {
    nodes = nodes.map((node) => ({
      ...node,
      cpu: {
        total: node.cpu.total,
        used: Math.min(node.cpu.total, Math.max(0, node.cpu.used + Math.floor(Math.random() * 5 - 2))),
      },
      ram: {
        total: node.ram.total,
        used: Math.min(node.ram.total, Math.max(0, node.ram.used + Math.floor(Math.random() * 4000 - 2000))),
      },
      status: ['online', 'idle', 'busy'][Math.floor(Math.random() * 3)],
    }));

    if (Math.random() > 0.6) {
      const target = nodes[Math.floor(Math.random() * nodes.length)];
      tasks.push(createTask(taskId++, target));
    }
    tasks = tasks.filter(() => Math.random() > 0.1).slice(-30);

    broadcast({ type: 'cluster_snapshot', nodes, tasks });
  }, 2000);

  ws.on('close', () => clearInterval(interval));
});

console.log('WebSocket server running at ws://localhost:4000');
