import { clsx } from 'clsx';

export function cn(...inputs) {
  return clsx(inputs);
}

export function formatUptime(seconds) {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatCost(usd) {
  return `$${usd.toFixed(2)}`;
}

export function timeAgo(timestamp) {
  if (!timestamp) return '—';
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export function statusColor(status) {
  switch (status) {
    case 'completed': return 'text-emerald-400';
    case 'processing': return 'text-blue-400';
    case 'queued': return 'text-amber-400';
    case 'failed': return 'text-red-400';
    default: return 'text-zinc-400';
  }
}

export function statusBg(status) {
  switch (status) {
    case 'completed': return 'bg-emerald-500/10 border-emerald-500/20';
    case 'processing': return 'bg-blue-500/10 border-blue-500/20';
    case 'queued': return 'bg-amber-500/10 border-amber-500/20';
    case 'failed': return 'bg-red-500/10 border-red-500/20';
    default: return 'bg-zinc-500/10 border-zinc-500/20';
  }
}
