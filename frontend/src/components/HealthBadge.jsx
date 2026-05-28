import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Activity } from 'lucide-react';

export function HealthBadge() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const check = () => {
      api.health()
        .then(setHealth)
        .catch(() => setHealth(null));
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, []);

  const ok = health?.status === 'ok';

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
      <div className="relative flex items-center justify-center">
        <Activity size={14} className={ok ? 'text-emerald-400' : 'text-red-400'} />
        {ok && (
          <span className="absolute inline-flex h-3 w-3 rounded-full bg-emerald-400/40 animate-ping" />
        )}
      </div>
      <span className="text-xs font-medium text-zinc-400">
        {ok ? 'API Online' : 'API Offline'}
      </span>
      {health && (
        <span className="text-[10px] text-zinc-600 tabular-nums">
          v{health.version}
        </span>
      )}
    </div>
  );
}
