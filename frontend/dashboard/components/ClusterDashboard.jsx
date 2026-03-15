'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const WS_ENDPOINT_DEFAULT = process.env.NEXT_PUBLIC_COORDINATOR_WS || 'ws://127.0.0.1:8000/ws';

const emptyCluster = {
  nodes: [],
  tasks: [],
  jobs: {
    total: 0,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
  },
};

const makeHistoryEntry = (nodes, jobs) => ({
  time: new Date().toLocaleTimeString(),
  activeNodes: nodes.length,
  runningTasks: jobs.running || 0,
  pendingTasks: jobs.pending || 0,
});

export default function ClusterDashboard() {
  const [cluster, setCluster] = useState(emptyCluster);
  const [history, setHistory] = useState([]);
  const [endpoint, setEndpoint] = useState(WS_ENDPOINT_DEFAULT);
  const [selectedWorker, setSelectedWorker] = useState('');
  const [wsConnected, setWsConnected] = useState(false);
  const [submitState, setSubmitState] = useState({ sending: false, error: '', ok: '' });
  const [jobForm, setJobForm] = useState({
    taskType: 'sleep',
    payloadText: JSON.stringify({ seconds: 2 }, null, 2),
  });

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  const refreshSnapshot = useCallback(async () => {
    try {
      const response = await fetch('/api/status', { cache: 'no-store' });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      const nodes = payload.nodes || [];
      const tasks = payload.tasks || [];
      const jobs = payload.jobs || emptyCluster.jobs;
      setCluster({ nodes, tasks, jobs });
      setHistory((prev) => [...prev.slice(-29), makeHistoryEntry(nodes, jobs)]);
    } catch (_error) {
      // WebSocket will eventually sync state.
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) {
      wsRef.current.close();
    }

    const ws = new WebSocket(endpoint);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      ws.send(JSON.stringify({ type: 'SUBSCRIBE_DASHBOARD' }));
      setSubmitState((prev) => ({ ...prev, error: '' }));
    };

    ws.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'CLUSTER_STATE') {
          const nodes = payload.nodes || [];
          const tasks = payload.tasks || [];
          const jobs = payload.jobs || emptyCluster.jobs;
          setCluster({ nodes, tasks, jobs });
          setHistory((prev) => [...prev.slice(-29), makeHistoryEntry(nodes, jobs)]);
        }
      } catch (error) {
        console.error('Invalid WS payload', error);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onclose = () => {
      setWsConnected(false);
      reconnectTimerRef.current = window.setTimeout(() => {
        connectWebSocket();
      }, 2000);
    };
  }, [endpoint]);

  useEffect(() => {
    connectWebSocket();
    refreshSnapshot();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connectWebSocket, refreshSnapshot]);

  const submitJob = async (event) => {
    event.preventDefault();

    let parsedPayload;
    try {
      parsedPayload = JSON.parse(jobForm.payloadText || '{}');
    } catch (_error) {
      setSubmitState({ sending: false, error: 'Payload must be valid JSON.', ok: '' });
      return;
    }

    setSubmitState({ sending: true, error: '', ok: '' });

    try {
      const response = await fetch('/api/submit-job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          taskType: jobForm.taskType,
          payload: parsedPayload,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.error || 'Job submission failed');
      }
      setSubmitState({ sending: false, error: '', ok: `Job queued: ${result.taskId}` });
      await refreshSnapshot();
    } catch (error) {
      setSubmitState({
        sending: false,
        error: error instanceof Error ? error.message : 'Unexpected submission error',
        ok: '',
      });
    }
  };

  const nodeRows = cluster.nodes;
  const taskRows = cluster.tasks;

  useEffect(() => {
    if (!selectedWorker && nodeRows.length > 0) {
      setSelectedWorker(nodeRows[0].nodeId);
    }
    if (selectedWorker && !nodeRows.some((n) => n.nodeId === selectedWorker)) {
      setSelectedWorker(nodeRows[0]?.nodeId || '');
    }
  }, [nodeRows, selectedWorker]);

  const runningTasks = useMemo(
    () => taskRows.filter((task) => task.status === 'running'),
    [taskRows]
  );

  const workerTaskRows = useMemo(() => {
    if (!selectedWorker) {
      return [];
    }
    return taskRows
      .filter((task) => task.assignedTo === selectedWorker)
      .sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
  }, [taskRows, selectedWorker]);

  const workerSummary = useMemo(() => {
    const total = workerTaskRows.length;
    const running = workerTaskRows.filter((t) => t.status === 'running').length;
    const completed = workerTaskRows.filter((t) => t.status === 'completed').length;
    const failed = workerTaskRows.filter((t) => t.status === 'failed').length;
    return { total, running, completed, failed };
  }, [workerTaskRows]);

  const capacitySummary = useMemo(() => {
    const totalCpuCores = nodeRows.reduce((sum, n) => sum + (n.cpuCores || 0), 0);
    const totalRamGb = nodeRows.reduce((sum, n) => sum + (n.ramGb || 0), 0);
    const gpuNodes = nodeRows.filter((n) => n.gpuAvailable).length;
    return {
      totalCpuCores,
      totalRamGb: Number(totalRamGb.toFixed(2)),
      gpuNodes,
    };
  }, [nodeRows]);

  const capacityChartData = useMemo(
    () =>
      nodeRows.map((node) => ({
        name: node.nodeId,
        cpu: node.cpuCores,
        ram: node.ramGb,
      })),
    [nodeRows]
  );

  const taskStatusPie = useMemo(
    () => [
      { name: 'Pending', value: cluster.jobs.pending || 0, color: '#f59e0b' },
      { name: 'Running', value: cluster.jobs.running || 0, color: '#0ea5e9' },
      { name: 'Completed', value: cluster.jobs.completed || 0, color: '#16a34a' },
      { name: 'Failed', value: cluster.jobs.failed || 0, color: '#dc2626' },
    ],
    [cluster.jobs]
  );

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8 space-y-6">
      <header className="rounded-3xl border border-slate-200 bg-white/70 backdrop-blur px-5 py-4 md:px-8 md:py-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-3xl md:text-4xl font-black tracking-tight text-slate-900">Campus Compute Dashboard</h1>
            <p className="text-slate-600 mt-1">Real-time cluster telemetry and job control</p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-semibold ${wsConnected ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
            {wsConnected ? 'WebSocket live' : 'Reconnecting'}
          </span>
        </div>
        <div className="mt-4 flex flex-col md:flex-row gap-3 md:items-center">
          <label className="text-sm text-slate-600">WS Endpoint</label>
          <input
            className="w-full md:w-[440px] rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-900"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="ws://127.0.0.1:8000/ws"
          />
          <button
            type="button"
            onClick={connectWebSocket}
            className="rounded-xl bg-cyan-600 text-white px-4 py-2 font-semibold hover:bg-cyan-700"
          >
            Reconnect
          </button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total CPU Cores" value={capacitySummary.totalCpuCores} />
        <MetricCard label="Total RAM (GB)" value={capacitySummary.totalRamGb} />
        <MetricCard label="GPU Nodes" value={capacitySummary.gpuNodes} />
        <MetricCard label="Active Tasks" value={cluster.jobs.running || 0} />
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Worker View</h2>
            <p className="text-sm text-slate-600">Select a worker to see every task it received.</p>
          </div>
          <div className="w-full md:w-96">
            <label className="block text-sm text-slate-600 mb-1">Worker Node</label>
            <select
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-slate-900"
              value={selectedWorker}
              onChange={(e) => setSelectedWorker(e.target.value)}
            >
              {nodeRows.length === 0 ? <option value="">No connected workers</option> : null}
              {nodeRows.map((node) => (
                <option key={node.nodeId} value={node.nodeId}>
                  {node.nodeId}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <MetricMini label="Received" value={workerSummary.total} />
          <MetricMini label="Running" value={workerSummary.running} />
          <MetricMini label="Completed" value={workerSummary.completed} />
          <MetricMini label="Failed" value={workerSummary.failed} />
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm text-slate-700">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="px-2 py-3">Task ID</th>
                <th className="px-2 py-3">Type</th>
                <th className="px-2 py-3">Status</th>
                <th className="px-2 py-3">Created</th>
                <th className="px-2 py-3">Completed</th>
              </tr>
            </thead>
            <tbody>
              {workerTaskRows.length === 0 ? (
                <tr>
                  <td className="px-2 py-3 text-slate-500" colSpan={5}>
                    No tasks received by this worker yet.
                  </td>
                </tr>
              ) : workerTaskRows.map((task) => (
                <tr key={task.taskId} className="border-b border-slate-100">
                  <td className="px-2 py-2 font-mono text-xs md:text-sm">{task.taskId}</td>
                  <td className="px-2 py-2">{task.taskType}</td>
                  <td className="px-2 py-2"><StatusPill value={task.status} /></td>
                  <td className="px-2 py-2">{formatTime(task.createdAt)}</td>
                  <td className="px-2 py-2">{formatTime(task.completedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
          <h2 className="text-xl font-bold mb-3 text-slate-900">Cluster Nodes</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-700">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="px-2 py-3">Node ID</th>
                  <th className="px-2 py-3">CPU</th>
                  <th className="px-2 py-3">RAM</th>
                  <th className="px-2 py-3">GPU</th>
                  <th className="px-2 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {nodeRows.map((node) => (
                  <tr key={node.nodeId} className="border-b border-slate-100">
                    <td className="px-2 py-2 font-medium text-slate-900">{node.nodeId}</td>
                    <td className="px-2 py-2">{node.cpuCores} cores</td>
                    <td className="px-2 py-2">{node.ramGb} GB</td>
                    <td className="px-2 py-2">
                      {node.gpuAvailable ? `${node.gpuVendor || 'gpu'} (${node.gpuBackend || 'n/a'})` : 'No GPU'}
                    </td>
                    <td className="px-2 py-2">
                      <StatusPill value={node.isBusy ? 'busy' : 'idle'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
          <h2 className="text-xl font-bold mb-3 text-slate-900">Active Tasks By Worker</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-700">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="px-2 py-3">Task ID</th>
                  <th className="px-2 py-3">Worker</th>
                  <th className="px-2 py-3">Type</th>
                  <th className="px-2 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {runningTasks.length === 0 ? (
                  <tr>
                    <td className="px-2 py-3 text-slate-500" colSpan={4}>No active tasks</td>
                  </tr>
                ) : runningTasks.map((task) => (
                  <tr key={task.taskId} className="border-b border-slate-100">
                    <td className="px-2 py-2 font-mono text-xs md:text-sm">{task.taskId}</td>
                    <td className="px-2 py-2">{task.assignedTo || '-'}</td>
                    <td className="px-2 py-2">{task.taskType}</td>
                    <td className="px-2 py-2"><StatusPill value={task.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
          <h2 className="text-xl font-bold mb-3 text-slate-900">Cluster Activity Trend</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <AreaChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="runningTasks" stroke="#0284c7" fill="#bae6fd" name="Running" />
                <Area type="monotone" dataKey="pendingTasks" stroke="#d97706" fill="#fde68a" name="Pending" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
          <h2 className="text-xl font-bold mb-3 text-slate-900">Capacity + Job Status</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={capacityChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="cpu" fill="#0ea5e9" name="CPU Cores" />
                  <Bar dataKey="ram" fill="#10b981" name="RAM GB" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={taskStatusPie} dataKey="value" nameKey="name" outerRadius={92}>
                    {taskStatusPie.map((item) => (
                      <Cell key={item.name} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 md:p-6 shadow-sm">
        <h2 className="text-xl font-bold mb-3 text-slate-900">Submit Job</h2>
        <form className="space-y-3 max-w-2xl" onSubmit={submitJob}>
          <div className="grid md:grid-cols-3 gap-3">
            <div>
              <label className="block text-sm text-slate-600 mb-1">Task Type</label>
              <select
                className="w-full rounded-xl border border-slate-300 bg-white p-2 text-slate-900"
                value={jobForm.taskType}
                onChange={(e) => setJobForm((prev) => ({ ...prev, taskType: e.target.value }))}
              >
                <option value="sleep">sleep</option>
                <option value="echo">echo</option>
                <option value="image_preprocess">image_preprocess</option>
                <option value="inference">inference</option>
                <option value="training_step">training_step</option>
                <option value="container_task">container_task</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm text-slate-600 mb-1">Payload JSON</label>
              <textarea
                rows={7}
                className="w-full rounded-xl border border-slate-300 bg-white p-2 font-mono text-sm text-slate-900"
                value={jobForm.payloadText}
                onChange={(e) => setJobForm((prev) => ({ ...prev, payloadText: e.target.value }))}
              />
            </div>
          </div>
          {submitState.error ? <p className="text-rose-600 text-sm">{submitState.error}</p> : null}
          {submitState.ok ? <p className="text-emerald-700 text-sm">{submitState.ok}</p> : null}
          <button
            className="rounded-xl bg-cyan-600 px-4 py-2 font-semibold text-white hover:bg-cyan-700 disabled:opacity-60"
            type="submit"
            disabled={submitState.sending}
          >
            {submitState.sending ? 'Submitting...' : 'Submit Job'}
          </button>
        </form>
      </section>
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-extrabold text-slate-900">{value}</p>
    </div>
  );
}

function MetricMini({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

function formatTime(value) {
  if (!value) {
    return '-';
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return '-';
  }
  return d.toLocaleString();
}

function StatusPill({ value }) {
  const normalized = String(value || '').toLowerCase();
  const palette = normalized === 'running' || normalized === 'busy'
    ? 'bg-amber-100 text-amber-700'
    : normalized === 'completed' || normalized === 'idle'
      ? 'bg-emerald-100 text-emerald-700'
      : normalized === 'failed'
        ? 'bg-rose-100 text-rose-700'
        : 'bg-slate-100 text-slate-600';

  return (
    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${palette}`}>
      {value}
    </span>
  );
}
