import { useState } from 'react';
import { motion } from 'framer-motion';
import { HealthBadge } from './components/HealthBadge';
import { ApiKeyPanel } from './components/ApiKeyPanel';
import { TranscriptionPlayground } from './components/TranscriptionPlayground';
import { DevExperiencePanel } from './components/DevExperiencePanel';
import { UsagePanel } from './components/UsagePanel';
import { GlassCard } from './components/ui';
import {
  AudioLines, Sparkles, Code2, Shield, Cpu, Globe,
} from 'lucide-react';

const FEATURES = [
  { icon: AudioLines, title: 'Speaker Diarization', desc: 'Creator / AI / Narrator / OCR labels' },
  { icon: Globe, title: 'Language Detection', desc: 'Auto-detect + translate to English' },
  { icon: Cpu, title: 'Agent-First Design', desc: 'OpenAPI, MCP, llms.txt built in' },
  { icon: Shield, title: 'API Key Auth', desc: 'Per-key rate limits & usage tracking' },
  { icon: Code2, title: 'SDK & CLI', desc: 'Python client + command-line tool' },
  { icon: Sparkles, title: 'Structured Output', desc: 'Typed TranscriptionResult schema' },
];

export default function App() {
  const [apiKey, setApiKey] = useState('');

  return (
    <div className="min-h-screen bg-[#09090b] text-white antialiased">
      {/* Subtle gradient bg */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-gradient-to-b from-blue-600/8 via-purple-600/5 to-transparent rounded-full blur-3xl" />
      </div>

      {/* Content */}
      <div className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">

        {/* Header */}
        <header className="flex items-center justify-between mb-12">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <AudioLines size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">KeyFrame</h1>
              <p className="text-[10px] text-zinc-500 -mt-0.5 tracking-wide">TRANSCRIPTION API</p>
            </div>
          </div>
          <HealthBadge />
        </header>

        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-16"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 mb-6">
            <Sparkles size={12} className="text-blue-400" />
            <span className="text-xs text-blue-300 font-medium">Agent-First Transcription API</span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight bg-gradient-to-r from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
            Transcribe. Diarize. Translate.
          </h2>
          <p className="text-base text-zinc-400 mt-4 max-w-xl mx-auto leading-relaxed">
            Video and audio transcription with speaker labeling, language detection,
            and English translation — designed for AI agents and developer workflows.
          </p>
        </motion.div>

        {/* Feature pills */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-16">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3 }}
            >
              <GlassCard className="p-3 text-center">
                <f.icon size={16} className="mx-auto text-zinc-400 mb-2" />
                <p className="text-xs font-medium text-white">{f.title}</p>
                <p className="text-[10px] text-zinc-500 mt-0.5">{f.desc}</p>
              </GlassCard>
            </motion.div>
          ))}
        </div>

        {/* Main grid: Playground + Sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-12">
          {/* Left: Playground (2 cols) */}
          <div className="lg:col-span-2 space-y-6">
            <TranscriptionPlayground />
            <UsagePanel apiKey={apiKey} />
          </div>

          {/* Right: Sidebar */}
          <div className="space-y-6">
            <ApiKeyPanel />
            <DevExperiencePanel />
          </div>
        </div>

        {/* Bottom: Pricing overview */}
        <GlassCard className="p-6" hover={false}>
          <h3 className="text-sm font-semibold text-white mb-4">Pricing</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { tier: 'Free', quota: '5/mo', price: '$0.00', rpm: '5 RPM', accent: 'text-zinc-400' },
              { tier: 'Starter', quota: '100/mo', price: '$0.10', rpm: '30 RPM', accent: 'text-blue-400' },
              { tier: 'Pro', quota: '1,000/mo', price: '$0.08', rpm: '60 RPM', accent: 'text-purple-400' },
              { tier: 'Enterprise', quota: 'Unlimited', price: '$0.06', rpm: '120 RPM', accent: 'text-emerald-400' },
            ].map(p => (
              <div key={p.tier} className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center">
                <p className={`text-xs font-semibold ${p.accent}`}>{p.tier}</p>
                <p className="text-2xl font-bold text-white mt-1">{p.price}</p>
                <p className="text-[10px] text-zinc-500 mt-0.5">per video</p>
                <p className="text-[10px] text-zinc-600 mt-1">{p.quota} &middot; {p.rpm}</p>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Footer */}
        <footer className="mt-16 pb-8 text-center">
          <p className="text-xs text-zinc-600">
            KeyFrame Transcription API &middot; Agent-first by design &middot;{' '}
            <a href="/openapi.json" className="text-zinc-500 hover:text-zinc-300 transition-colors">OpenAPI</a>
            {' '}&middot;{' '}
            <a href="/llms.txt" className="text-zinc-500 hover:text-zinc-300 transition-colors">llms.txt</a>
          </p>
        </footer>
      </div>
    </div>
  );
}
