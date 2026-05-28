import { GlassCard } from './ui';
import {
  Terminal, BookOpen, FileJson, Plug, FileText, Zap, ArrowRight,
} from 'lucide-react';

const ENDPOINTS = [
  { method: 'POST', path: '/api/v1/transcribe', desc: 'Submit media URL for transcription', color: 'text-emerald-400' },
  { method: 'POST', path: '/api/v1/transcribe/upload', desc: 'Upload media file (max 100 MB)', color: 'text-emerald-400' },
  { method: 'GET', path: '/api/v1/jobs/{job_id}', desc: 'Poll job status and retrieve results', color: 'text-blue-400' },
  { method: 'POST', path: '/api/v1/keys', desc: 'Create an API key', color: 'text-emerald-400' },
  { method: 'GET', path: '/api/v1/usage', desc: 'Get usage and remaining quota', color: 'text-blue-400' },
  { method: 'GET', path: '/health', desc: 'Service health check', color: 'text-blue-400' },
];

const DISCOVERABILITY = [
  { icon: FileJson, label: 'OpenAPI', path: '/openapi.json', desc: 'Full API specification', color: 'text-emerald-400' },
  { icon: FileText, label: 'llms.txt', path: '/llms.txt', desc: 'Agent discoverability standard', color: 'text-blue-400' },
  { icon: Plug, label: 'MCP Server', path: 'mcp_server.py', desc: 'Model Context Protocol tools', color: 'text-purple-400' },
  { icon: Zap, label: 'AI Plugin', path: '/.well-known/ai-plugin.json', desc: 'OpenAI plugin manifest', color: 'text-amber-400' },
];

const CURL_EXAMPLES = [
  {
    label: 'Submit transcription',
    code: `curl -X POST http://localhost:8000/api/v1/transcribe \\
  -H "X-API-Key: kf_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com/video.mp4"}'`,
  },
  {
    label: 'Poll for result',
    code: `curl http://localhost:8000/api/v1/jobs/JOB_ID \\
  -H "X-API-Key: kf_YOUR_KEY"`,
  },
  {
    label: 'Check usage',
    code: `curl http://localhost:8000/api/v1/usage \\
  -H "X-API-Key: kf_YOUR_KEY"`,
  },
];

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={copy} className="...">...</button>
  );
}

import { useState } from 'react';

export function DevExperiencePanel() {
  const [copiedIdx, setCopiedIdx] = useState(-1);

  const copyCode = (code, idx) => {
    navigator.clipboard.writeText(code);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(-1), 1500);
  };

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <BookOpen size={14} className="text-zinc-500" />
        Developer Experience
      </h3>

      {/* Endpoint cards */}
      <div className="space-y-2">
        {ENDPOINTS.map(ep => (
          <div key={ep.path} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] group hover:border-white/[0.08] transition-colors">
            <span className={`text-[10px] font-bold font-mono ${ep.color} w-10`}>{ep.method}</span>
            <code className="text-xs font-mono text-zinc-300 flex-1">{ep.path}</code>
            <span className="text-[10px] text-zinc-600 hidden sm:block">{ep.desc}</span>
          </div>
        ))}
      </div>

      {/* Agent discoverability badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {DISCOVERABILITY.map(d => (
          <GlassCard key={d.label} className="p-3 flex flex-col items-center text-center gap-2">
            <d.icon size={18} className={d.color} />
            <span className="text-xs font-medium text-white">{d.label}</span>
            <span className="text-[10px] text-zinc-500">{d.desc}</span>
          </GlassCard>
        ))}
      </div>

      {/* cURL examples */}
      <div className="space-y-3">
        <p className="text-xs text-zinc-500 font-medium uppercase tracking-wider flex items-center gap-2">
          <Terminal size={12} />
          Quick Start
        </p>
        {CURL_EXAMPLES.map((ex, i) => (
          <div key={i} className="relative group">
            <div className="flex items-center justify-between px-3 py-1.5 bg-black/40 rounded-t-lg border border-b-0 border-white/[0.06]">
              <span className="text-[10px] text-zinc-500 font-medium">{ex.label}</span>
              <button
                onClick={() => copyCode(ex.code, i)}
                className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1"
              >
                {copiedIdx === i ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <pre className="px-4 py-3 bg-black/20 rounded-b-lg border border-white/[0.06] text-xs text-zinc-300 overflow-x-auto font-mono leading-relaxed">
              {ex.code}
            </pre>
          </div>
        ))}
      </div>

      {/* SDK hint */}
      <GlassCard className="p-4 flex items-center gap-4" hover={false}>
        <div className="p-2.5 rounded-xl bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/20">
          <ArrowRight size={16} className="text-blue-400" />
        </div>
        <div className="flex-1">
          <p className="text-xs font-medium text-white">Python SDK included</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            <code className="text-zinc-400">from sdk import KeyFrameClient</code> — auto-polling, typed errors, file upload
          </p>
        </div>
      </GlassCard>
    </div>
  );
}
