const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function fetchTreasuryState() {
  const res = await fetch(`${API_BASE}/api/treasury/state`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function fetchRecentTransactions(limit = 10) {
  const res = await fetch(`${API_BASE}/api/transactions/recent?limit=${limit}`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function fetchMetrics() {
  const res = await fetch(`${API_BASE}/api/metrics`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function setSimulationScenario(scenario, intensity = 1.0) {
  const res = await fetch(`${API_BASE}/api/simulation/scenario`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario, intensity })
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}
