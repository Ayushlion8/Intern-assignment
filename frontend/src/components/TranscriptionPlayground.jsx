import { useState } from 'react';
import { api } from '../api/client';
import { usePollJob } from '../hooks/usePollJob';
import { GlassCard, MetricCard } from './ui';
import { cn, statusColor, statusBg } from '../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, Loader2, AlertCircle, CheckCircle2, Clock,
  Languages, AudioLines, FileText, User, Brain, MessageSquare,
} from 'lucide-react';

const SPEAKER_ICONS = {
  creator: User,
  ai: Brain,
  narrator: MessageSquare,
  'on-screen-ocr': FileText,
};

export function TranscriptionPlayground() {
  const [url, setUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [activeJobId, setActiveJobId] = useState(null);

  const { job, error: pollError, polling, startPolling } = usePollJob(activeJobId, apiKey);

  const submit = async () => {
    if (!url.trim() || !apiKey.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const data = await api.transcribe(url, model || null, apiKey);
      setActiveJobId(data.job_id);
      startPolling();
    } catch (e) {
      setSubmitError(e);
    }
    setSubmitting(false);
  };

  const result = job?.result;

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Play size={14} className="text-blue-400" />
        Transcription Playground
      </h3>

      {/* Input Section */}
      <GlassCard className="p-5 space-y-4" hover={false}>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-1.5 block">
            Media URL
          </label>
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://example.com/video.mp4"
            className="w-full px-4 py-2.5 rounded-xl bg-black/30 border border-white/[0.06] text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-blue-500/40 focus:ring-1 focus:ring-blue-500/20 transition-all"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-1.5 block">
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="kf_..."
              className="w-full px-4 py-2.5 rounded-xl bg-black/30 border border-white/[0.06] text-white placeholder-zinc-600 text-sm font-mono focus:outline-none focus:border-blue-500/40 focus:ring-1 focus:ring-blue-500/20 transition-all"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-1.5 block">
              Model <span className="text-zinc-600">(optional)</span>
            </label>
            <input
              type="text"
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder="gemini-2.5-flash"
              className="w-full px-4 py-2.5 rounded-xl bg-black/30 border border-white/[0.06] text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-blue-500/40 focus:ring-1 focus:ring-blue-500/20 transition-all"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={submit}
            disabled={submitting || !url.trim() || !apiKey.trim()}
            className={cn(
              'flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all',
              'bg-gradient-to-r from-blue-600 to-purple-600 text-white',
              'hover:from-blue-500 hover:to-purple-500',
              'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:from-blue-600 disabled:hover:to-purple-600',
              'shadow-lg shadow-blue-500/20',
            )}
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {submitting ? 'Submitting...' : 'Transcribe'}
          </button>
          {activeJobId && (
            <span className="text-xs text-zinc-500 font-mono">
              Job: {activeJobId}
            </span>
          )}
        </div>

        {/* Submit error */}
        <AnimatePresence>
          {submitError && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20"
            >
              <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs text-red-300 font-medium">{submitError.code}</p>
                <p className="text-xs text-red-400/70 mt-0.5">{submitError.message}</p>
                <p className="text-[10px] text-red-400/50 mt-1">Action: {submitError.action}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </GlassCard>

      {/* Status + Results */}
      <AnimatePresence>
        {job && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            {/* Status Bar */}
            <div className={cn('flex items-center gap-3 px-4 py-3 rounded-xl border', statusBg(job.status))}>
              {job.status === 'completed' && <CheckCircle2 size={16} className="text-emerald-400" />}
              {job.status === 'processing' && <Loader2 size={16} className="text-blue-400 animate-spin" />}
              {job.status === 'queued' && <Clock size={16} className="text-amber-400" />}
              {job.status === 'failed' && <AlertCircle size={16} className="text-red-400" />}
              <span className={cn('text-sm font-medium', statusColor(job.status))}>
                {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
              </span>
              {polling && (
                <span className="text-[10px] text-zinc-500">Polling for updates...</span>
              )}
            </div>

            {/* Result metrics */}
            {result && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard label="Language" value={result.detectedLanguageName || result.detectedLanguage || '—'} icon={Languages} accent="text-purple-400" />
                <MetricCard label="Audio Mode" value={result.audioMode || '—'} icon={AudioLines} accent="text-amber-400" />
                <MetricCard label="Translated" value={result.isTranslated ? 'Yes' : 'No'} icon={Languages} accent="text-cyan-400" />
                <MetricCard label="Segments" value={result.diarizedTranscript?.length || 0} icon={FileText} accent="text-emerald-400" />
              </div>
            )}

            {/* Full text */}
            {result?.text && (
              <GlassCard className="p-4" hover={false}>
                <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-2">Full Transcript</p>
                <p className="text-sm text-zinc-200 leading-relaxed">{result.text}</p>
              </GlassCard>
            )}

            {/* Diarized segments */}
            {result?.diarizedTranscript?.length > 0 && (
              <GlassCard className="p-4" hover={false}>
                <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-3">Diarized Segments</p>
                <div className="space-y-3">
                  {result.diarizedTranscript.map((seg, i) => {
                    const Icon = SPEAKER_ICONS[seg.speaker] || User;
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.06 }}
                        className="flex gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]"
                      >
                        <div className="shrink-0 mt-0.5">
                          <div className={cn(
                            'p-1.5 rounded-lg',
                            seg.speaker === 'creator' && 'bg-blue-500/10 text-blue-400',
                            seg.speaker === 'ai' && 'bg-purple-500/10 text-purple-400',
                            seg.speaker === 'narrator' && 'bg-emerald-500/10 text-emerald-400',
                            seg.speaker === 'on-screen-ocr' && 'bg-amber-500/10 text-amber-400',
                            !SPEAKER_ICONS[seg.speaker] && 'bg-zinc-500/10 text-zinc-400',
                          )}>
                            <Icon size={12} />
                          </div>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-semibold text-white">{seg.speaker}</span>
                            <span className="text-[10px] text-zinc-500">{seg.languageName}</span>
                          </div>
                          <p className="text-sm text-zinc-200">{seg.text}</p>
                          {seg.originalText && seg.originalText !== seg.text && (
                            <p className="text-xs text-zinc-500 mt-1 italic">{seg.originalText}</p>
                          )}
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </GlassCard>
            )}

            {/* Error */}
            {job.status === 'failed' && job.error && (
              <GlassCard className="p-4 border-red-500/20" hover={false}>
                <p className="text-xs text-red-400 font-medium">{job.error.code}</p>
                <p className="text-sm text-red-300/70 mt-1">{job.error.message}</p>
                {job.error.action && (
                  <p className="text-xs text-red-400/50 mt-2">Suggested action: {job.error.action}</p>
                )}
              </GlassCard>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
