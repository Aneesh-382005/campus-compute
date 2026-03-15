'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from 'recharts';

const initialState = {
  nodes: [
    { node_id: 'node-1', cpu: { total: 16, used: 6 }, ram: { total: 64000, used: 24000 }, gpu: { available: true }, status: 'online' },
    { node_id: 'node-2', cpu: { total: 16, used: 9 }, ram: { total: 64000, used: 38000 }, gpu: { available: false }, status: 'busy' },
    { node_id: 'node-3', cpu: { total: 16, used: 3 }, ram: { total: 64000, used: 18000 }, gpu: { available: true }, status: 'idle' },
    { node_id: 'node-4', cpu: { total: 16, used: 12 }, ram: { total: 64000, used: 52000 }, gpu: { available: false }, status: 'online' },
  ],
  tasks: [
    { task_id: 'task-1', worker_id: 'node-1', cpu: 2, ram: 1024, status: 'running' },
    { task_id: 'task-2', worker_id: 'node-2', cpu: 4, ram: 4096, status: 'running' },
    { task_id: 'task-3', worker_id: 'node-3', cpu: 1, ram: 512, status: 'queued' },
    { task_id: 'task-4', worker_id: 'node-4', cpu: 6, ram: 8192, status: 'completed' },
  ],
  summary: {
    totalCpu: 16 * 4,
    totalRam: 64000 * 4,
    gpuNodes: 2,
  },
};

const buildSummary = (nodes) => {
  const totalCpu = nodes.reduce((s, n) => s + n.cpu.total, 0);
  const totalRam = nodes.reduce((s, n) => s + n.ram.total, 0);
  const gpuNodes = nodes.filter((n) => n.gpu.available).length;
  return { totalCpu, totalRam, gpuNodes };
};

const makeHistoryEntry = (nodes) => ({
  time: new Date().toLocaleTimeString(),
  cpuUsage: Math.round(nodes.reduce((s, n) => s + n.cpu.used, 0) / Math.max(nodes.length, 1)),
  ramUsage: Math.round(nodes.reduce((s, n) => s + n.ram.used, 0) / Math.max(nodes.length, 1)),
});

export default function ClusterDashboard() {
  const [state, setState] = useState(initialState);
  const [history, setHistory] = useState([]);
  const [endpoint, setEndpoint] = useState('ws://localhost:4000');
  const [job, setJob] = useState({ name: '', cpu: 1, ram: 512, gpu: false });
  const [wsConnected, setWsConnected] = useState(false);

  const connectWebSocket = useCallback(() => {
    const ws = new WebSocket(endpoint);

    ws.onopen = () => {
      setWsConnected(true);
      console.log('WebSocket connected');
    };

    ws.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'cluster_snapshot') {
          const nodes = payload.nodes || [];
          const tasks = payload.tasks || [];
          const summary = buildSummary(nodes);
          setState({ nodes, tasks, summary });
          setHistory((prev) => [...prev.slice(-29), makeHistoryEntry(nodes)]);
        } else if (payload.type === 'node_update') {
          const nodes = payload.nodes || state.nodes;
          const tasks = payload.tasks || state.tasks;
          const summary = buildSummary(nodes);
          setState({ nodes, tasks, summary });
          setHistory((prev) => [...prev.slice(-29), makeHistoryEntry(nodes)]);
        }
      } catch (error) {
        console.error('Invalid WS payload', error);
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      console.log('WebSocket closed. reconnecting in 2s');
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('WS error', err);
      ws.close();
    };
  }, [endpoint, state.nodes, state.tasks]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      // window cleanup can be improved with ref to ws
    };
  }, [connectWebSocket]);

  const submitJob = (event) => {
    event.preventDefault();
    const payload = {
      type: 'submit_job',
      job,
    };
    fetch('/api/submit-job', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setJob({ name: '', cpu: 1, ram: 512, gpu: false });
  };

  const nodeRows = state.nodes.length ? state.nodes : [];
  const taskRows = state.tasks.length ? state.tasks : [];

  const insightData = useMemo(() => {
    return nodeRows.map((node) => ({
      name: node.node_id,
      cpu: node.cpu.used,
      ram: node.ram.used,
    }));
  }, [nodeRows]);

  return (
    <div className="container mx-auto p-4 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Realtime Cluster Dashboard</h1>
        <span className={`px-3 py-1 rounded ${wsConnected ? 'bg-emerald-500' : 'bg-rose-500'}`}>
          {wsConnected ? 'WS Connected' : 'Disconnected'}
        </span>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-lg font-semibold">Total CPU Cores</h2>
          <p className="text-4xl mt-2">{state.summary.totalCpu}</p>
        </div>
        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-lg font-semibold">Total RAM (MB)</h2>
          <p className="text-4xl mt-2">{state.summary.totalRam}</p>
        </div>
        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-lg font-semibold">GPU Nodes</h2>
          <p className="text-4xl mt-2">{state.summary.gpuNodes}</p>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-xl font-semibold mb-3">Node List</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="px-2 py-3">Node ID</th>
                  <th className="px-2 py-3">CPU</th>
                  <th className="px-2 py-3">RAM</th>
                  <th className="px-2 py-3">GPU</th>
                  <th className="px-2 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {nodeRows.map((node) => (
                  <tr key={node.node_id} className="border-b border-slate-700">
                    <td className="px-2 py-2">{node.node_id}</td>
                    <td className="px-2 py-2">{node.cpu.used}/{node.cpu.total}</td>
                    <td className="px-2 py-2">{node.ram.used}/{node.ram.total}</td>
                    <td className="px-2 py-2">{node.gpu.available ? 'available' : 'unavailable'}</td>
                    <td className="px-2 py-2">{node.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-xl font-semibold mb-3">Active Tasks</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  <th className="px-2 py-3">Task ID</th>
                  <th className="px-2 py-3">Worker</th>
                  <th className="px-2 py-3">CPU</th>
                  <th className="px-2 py-3">RAM</th>
                  <th className="px-2 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {taskRows.map((task) => (
                  <tr key={task.task_id} className="border-b border-slate-700">
                    <td className="px-2 py-2">{task.task_id}</td>
                    <td className="px-2 py-2">{task.worker_id}</td>
                    <td className="px-2 py-2">{task.cpu}</td>
                    <td className="px-2 py-2">{task.ram}</td>
                    <td className="px-2 py-2">{task.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-xl font-semibold mb-3">Cluster Resource Trend</h2>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={history}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="cpuUsage" stroke="#22d3ee" name="CPU avg" />
                <Line type="monotone" dataKey="ramUsage" stroke="#fb7185" name="RAM avg" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl bg-slate-800 p-4">
          <h2 className="text-xl font-semibold mb-3">CPU/GPU by Node</h2>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={insightData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="cpu" fill="#22d3ee" name="CPU used" />
                <Bar dataKey="ram" fill="#f472b6" name="RAM used" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="rounded-xl bg-slate-800 p-4">
        <h2 className="text-xl font-semibold mb-3">Submit Job</h2>
        <form className="space-y-3 max-w-md" onSubmit={submitJob}>
          <div>
            <label className="block text-sm text-slate-300">Job name</label>
            <input
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 p-2"
              value={job.name}
              onChange={(e) => setJob((prev) => ({ ...prev, name: e.target.value }))}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-sm text-slate-300">CPU cores</label>
              <input
                type="number"
                min={1}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 p-2"
                value={job.cpu}
                onChange={(e) => setJob((prev) => ({ ...prev, cpu: Number(e.target.value) }))}
              />
            </div>
            <div>
              <label className="block text-sm text-slate-300">RAM (MB)</label>
              <input
                type="number"
                min={128}
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 p-2"
                value={job.ram}
                onChange={(e) => setJob((prev) => ({ ...prev, ram: Number(e.target.value) }))}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="gpu"
              checked={job.gpu}
              onChange={(e) => setJob((prev) => ({ ...prev, gpu: e.target.checked }))}
            />
            <label htmlFor="gpu" className="text-sm text-slate-300">
              GPU required
            </label>
          </div>
          <button className="rounded-md bg-cyan-600 px-4 py-2 font-semibold" type="submit">
            Submit
          </button>
        </form>
      </section>
    </div>
  );
}
