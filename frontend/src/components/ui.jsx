import { motion } from 'framer-motion';
import { cn } from '../lib/utils';

export function GlassCard({ children, className, hover = true, ...props }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        'rounded-2xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-xl shadow-lg shadow-black/20',
        hover && 'transition-colors hover:border-white/[0.1] hover:bg-white/[0.05]',
        className,
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function MetricCard({ label, value, sub, icon: Icon, accent = 'text-white' }) {
  return (
    <GlassCard className="p-5 flex items-start gap-4">
      <div className={cn('p-2.5 rounded-xl bg-white/[0.05]', accent)}>
        {Icon && <Icon size={18} />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-semibold text-white mt-0.5 tabular-nums">{value}</p>
        {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
      </div>
    </GlassCard>
  );
}
