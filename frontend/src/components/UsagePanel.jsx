import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { GlassCard, MetricCard } from './ui';
import { formatCost } from '../lib/utils';
import { Activity, Zap, Clock, DollarSign, BarChart3, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

export function UsagePanel({ apiKey }) {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadUsage = async () => {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getUsage(apiKey);
      setUsage(data);
    } catch (e) {
      setError(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (apiKey) loadUsage();
  }, [apiKey]);

  if (!apiKey) {
    return (
      <GlassCard className="p-5 text-center" hover={false}>
        <p className="text-xs text-zinc-500">Enter an API key in the playground to view usage</p>
      </GlassCard>
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 size={20} className="text-zinc-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <GlassCard className="p-5" hover={false}>
        <p className="text-xs text-red-400">{error.message}</p>
      </GlassCard>
    );
  }

  if (!usage) return null;

  const quotaPct = usage.monthly_quota === -1 ? 0 : Math.min(100, (usage.usage_count / usage.monthly_quota) * 100);

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <BarChart3 size={14} className="text-zinc-500" />
        Usage & Quota
      </h3>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Used" value={usage.usage_count} icon={Zap} accent="text-blue-400" />
        <MetricCard label="Remaining" value={usage.monthly_quota === -1 ? '∞' : usage.remaining} icon={Clock} accent="text-emerald-400" />
        <MetricCard label="Quota" value={usage.monthly_quota === -1 ? 'Unlimited' : `${usage.monthly_quota}/mo`} icon={Activity} accent="text-amber-400" />
        <MetricCard label="Cost" value={formatCost(usage.cost_usd)} icon={DollarSign} accent="text-purple-400" />
      </div>

      {/* Quota bar */}
      {usage.monthly_quota !== -1 && (
        <GlassCard className="p-4" hover={false}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium">Monthly Quota</span>
            <span className="text-xs text-zinc-400 tabular-nums">{usage.usage_count} / {usage.monthly_quota}</span>
          </div>
          <div className="h-2 rounded-full bg-white/5 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${quotaPct}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
              className={cn(
                'h-full rounded-full',
                quotaPct > 90 ? 'bg-gradient-to-r from-red-500 to-red-400' :
                quotaPct > 70 ? 'bg-gradient-to-r from-amber-500 to-amber-400' :
                'bg-gradient-to-r from-blue-500 to-purple-500',
              )}
            />
          </div>
        </GlassCard>
      )}

      <div className="flex items-center justify-between text-[10px] text-zinc-600">
        <span>Tier: {usage.tier}</span>
        <span>Period: {usage.usage_month}</span>
        <span>Key: {usage.key_id}</span>
      </div>
    </div>
  );
}

function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}
