import { useState } from 'react';
import { api } from '../api/client';
import { GlassCard } from './ui';
import { Key, Copy, Check, Plus, Trash2, Eye, EyeOff } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export function ApiKeyPanel() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newKey, setNewKey] = useState(null);
  const [showKey, setShowKey] = useState({});
  const [copied, setCopied] = useState('');

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await api.listKeys();
      setKeys(data);
    } catch { }
    setLoading(false);
  };

  const createKey = async (tier = 'free') => {
    try {
      const data = await api.createKey(`key-${Date.now().toString(36)}`, tier);
      setNewKey(data);
      loadKeys();
    } catch { }
  };

  const copyText = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(''), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Key size={14} className="text-zinc-500" />
          API Keys
        </h3>
        <button
          onClick={() => createKey('free')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/20 transition-colors"
        >
          <Plus size={12} />
          Create Key
        </button>
      </div>

      <AnimatePresence>
        {newKey && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <GlassCard className="p-4 border-blue-500/20 bg-blue-500/5" hover={false}>
              <p className="text-xs text-blue-400 font-medium mb-2">New API Key — copy now, won't be shown again</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs bg-black/30 px-3 py-2 rounded-lg text-emerald-300 font-mono overflow-x-auto">
                  {showKey['new'] ? newKey.key : newKey.key.slice(0, 12) + '••••••••'}
                </code>
                <button onClick={() => setShowKey(p => ({ ...p, new: !p.new }))} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400">
                  {showKey['new'] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                <button onClick={() => copyText(newKey.key, 'new')} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-400">
                  {copied === 'new' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                </button>
              </div>
              <div className="flex gap-3 mt-2 text-[10px] text-zinc-500">
                <span>ID: {newKey.key_id}</span>
                <span>Tier: {newKey.tier}</span>
                <span>Quota: {newKey.monthly_quota === -1 ? 'Unlimited' : newKey.monthly_quota}/mo</span>
                <span>RPM: {newKey.rate_limit_rpm}</span>
              </div>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-2">
        {(keys.length === 0 && !loading) && (
          <div className="text-center py-6 text-zinc-600 text-xs">
            No keys yet. Click "Create Key" to get started.
          </div>
        )}
        {keys.map(k => (
          <div key={k.key_id} className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04]">
            <div className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full ${k.enabled ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span className="text-xs font-mono text-zinc-300">{k.key_id}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-zinc-500">{k.tier}</span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-zinc-500">
              <span>{k.usage_count}/{k.monthly_quota === -1 ? '∞' : k.monthly_quota}</span>
            </div>
          </div>
        ))}
      </div>

      {keys.length === 0 && !newKey && (
        <button
          onClick={loadKeys}
          className="w-full py-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Load existing keys
        </button>
      )}
    </div>
  );
}
