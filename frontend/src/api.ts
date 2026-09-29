const API = import.meta.env.VITE_API_URL || '/api';
export const token = () => localStorage.getItem('mf_token') || '';

// Global API Activity Tracker for Universal Live Loading Animation
let activeRequestCount = 0;
const activityListeners = new Set<(count: number) => void>();

export function subscribeApiActivity(cb: (count: number) => void) {
  activityListeners.add(cb);
  cb(activeRequestCount);
  return () => {
    activityListeners.delete(cb);
  };
}

function notifyActivity(delta: number) {
  activeRequestCount = Math.max(0, activeRequestCount + delta);
  activityListeners.forEach((cb) => {
    try {
      cb(activeRequestCount);
    } catch {
      // ignore
    }
  });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('api_activity', { detail: { activeCount: activeRequestCount } }));
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  notifyActivity(1);
  try {
    const h = new Headers(init.headers);
    if (!h.has('Content-Type')) h.set('Content-Type', 'application/json');
    if (token()) h.set('Authorization', `Bearer ${token()}`);
    const r = await fetch(`${API}${path}`, { ...init, headers: h });
    const payload = await r.json().catch(() => ({ detail: r.statusText }));
    if (r.status === 401) {
      localStorage.removeItem('mf_token');
      window.dispatchEvent(new Event('auth_expired'));
    }
    if (!r.ok) throw new Error(payload.detail || r.statusText);
    return payload as T;
  } finally {
    notifyActivity(-1);
  }
}

export async function downloadApi(path: string, filenameFallback = 'migration-log.csv') {
  notifyActivity(1);
  try {
    const h = new Headers();
    if (token()) h.set('Authorization', `Bearer ${token()}`);
    const r = await fetch(`${API}${path}`, { headers: h });
    if (!r.ok) {
      const payload = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(payload.detail || r.statusText);
    }
    const blob = await r.blob();
    const cd = r.headers.get('content-disposition') || '';
    const m = cd.match(/filename="?([^";]+)"?/i);
    const name = m?.[1] || filenameFallback;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } finally {
    notifyActivity(-1);
  }
}
