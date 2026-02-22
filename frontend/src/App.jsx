import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import {
  Send, Settings, Database, MessageSquare, Users, Play, Loader2,
  CheckCircle2, XCircle, Clock, Bot, User, Key, Eye, EyeOff, Info,
  Shield, Activity, ChevronDown, Zap, Search, LogOut, Plus, Trash2,
  GitBranch, FolderOpen, Cloud, ExternalLink, Monitor, Code2,
  Folder, FileCode, Copy, RefreshCw,
} from 'lucide-react'
import { signInWithGoogle, logOut, onAuthChange, getIdToken } from './firebase'

const DEFAULT_CLOUD_API = 'https://ai-factory-orchestrator-664984131730.us-central1.run.app'
const API = import.meta.env.VITE_API_BASE_URL || DEFAULT_CLOUD_API

/* ─── Authenticated fetch helper ─── */
async function api(path, options = {}) {
  const token = await getIdToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json'
  } else if (options.body && typeof options.body === 'object') {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(options.body)
  }
  const res = await fetch(`${API}${path}`, { ...options, headers })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

/* ─── Model catalog ─── */
const MODEL_CATALOG = {
  'Factory Aliases': {
    'factory/architect': { label: 'Factory Architect', desc: 'Strategic planning (Gemini Flash)', color: '#7c3aed', keyRequired: false },
    'factory/coder':    { label: 'Factory Coder', desc: 'Code generation (Gemini Flash)', color: '#2563eb', keyRequired: false },
    'factory/fast':     { label: 'Factory Fast', desc: 'Quick responses (Gemini Flash)', color: '#059669', keyRequired: false },
    'factory/cheap':    { label: 'Factory Economy', desc: 'Cost-effective (Gemini Flash)', color: '#d97706', keyRequired: false },
  },
  'Google Gemini': {
    'gemini/gemini-2.0-flash':               { label: 'Gemini 2.0 Flash', desc: 'Fast multimodal model', color: '#4285f4', keyRequired: 'GEMINI_API_KEY' },
    'gemini/gemini-2.5-pro-preview-06-05':   { label: 'Gemini 2.5 Pro', desc: 'Most capable Gemini', color: '#4285f4', keyRequired: 'GEMINI_API_KEY' },
    'gemini/gemini-2.5-flash-preview-05-20': { label: 'Gemini 2.5 Flash', desc: 'Fast + thinking', color: '#4285f4', keyRequired: 'GEMINI_API_KEY' },
  },
  'OpenAI': {
    'openai/gpt-4o':      { label: 'GPT-4o', desc: 'Flagship multimodal', color: '#10a37f', keyRequired: 'OPENAI_API_KEY' },
    'openai/gpt-4o-mini': { label: 'GPT-4o Mini', desc: 'Fast and affordable', color: '#10a37f', keyRequired: 'OPENAI_API_KEY' },
    'openai/gpt-4.1':     { label: 'GPT-4.1', desc: 'Coding + instructions', color: '#10a37f', keyRequired: 'OPENAI_API_KEY' },
    'openai/o3-mini':     { label: 'o3-mini', desc: 'Reasoning model', color: '#10a37f', keyRequired: 'OPENAI_API_KEY' },
  },
  'Anthropic': {
    'anthropic/claude-sonnet-4-20250514':  { label: 'Claude Sonnet 4', desc: 'Speed + intelligence', color: '#d97706', keyRequired: 'ANTHROPIC_API_KEY' },
    'anthropic/claude-3-5-haiku-20241022': { label: 'Claude 3.5 Haiku', desc: 'Fastest Claude', color: '#d97706', keyRequired: 'ANTHROPIC_API_KEY' },
  },
  'AWS Bedrock': {
    'bedrock/anthropic.claude-sonnet-4-20250514-v1:0': { label: 'Claude Sonnet 4 (Bedrock)', desc: 'Via AWS', color: '#ff9900', keyRequired: 'AWS credentials' },
    'bedrock/amazon.nova-pro-v1:0':                     { label: 'Amazon Nova Pro', desc: 'AWS native', color: '#ff9900', keyRequired: 'AWS credentials' },
  },
  'Azure OpenAI': {
    'azure/gpt-4o':      { label: 'GPT-4o (Azure)', desc: 'Via Azure', color: '#0078d4', keyRequired: 'AZURE_API_KEY' },
    'azure/gpt-4o-mini': { label: 'GPT-4o Mini (Azure)', desc: 'Via Azure', color: '#0078d4', keyRequired: 'AZURE_API_KEY' },
  },
}
const MODEL_FLAT = {}
Object.values(MODEL_CATALOG).forEach(group => { Object.assign(MODEL_FLAT, group) })

const ALL_TEAMS = [
  'product_mgmt','biz_analysis','solution_arch','api_design','ux_ui',
  'frontend_eng','backend_eng','database_eng','data_eng','ml_eng',
  'security_eng','compliance','devops','qa_eng','sre_ops','docs_team','feature_eng',
]

const NAV_DESCRIPTIONS = {
  chat: 'Chat with your AI coworker about the project.',
  pipeline: 'Describe a requirement — AI picks the right teams and runs the pipeline.',
  group: 'Multi-team discussion on a topic.',
  preview: 'Live code preview of the last pipeline run — like Google AI Studio.',
  memory: 'Interactive knowledge graph of all artifacts.',
  settings: 'Configure AI models, budgets, API keys, and Git.',
}

const formatTeamName = (key) => {
  if (!key) return ''
  return key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
const formatModelName = (k) => MODEL_FLAT[k]?.label || (k?.split('/')?.pop() ?? k)
const getModelInfo = (k) => MODEL_FLAT[k] || { label: k, desc: '', color: '#94a3b8', keyRequired: false }


/* ═══════════════════════════════════════════════════════════
   SVG Memory Graph
   ═══════════════════════════════════════════════════════════ */
function MemoryGraph({ data, onNodeClick }) {
  const [hoveredNode, setHoveredNode] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  const graphLayout = useMemo(() => {
    if (!data?.nodes?.length) return { nodes: [], edges: [] }
    const nodes = data.nodes.map((n, i) => {
      const angle = (i / data.nodes.length) * 2 * Math.PI
      const radius = 180 + (n.items || 1) * 20
      return { ...n, x: 400 + radius * Math.cos(angle) + (Math.random() - 0.5) * 40,
        y: 300 + radius * Math.sin(angle) + (Math.random() - 0.5) * 40,
        r: Math.max(20, Math.min(50, 12 + (n.items || 0) * 8)),
        displayName: formatTeamName(n.team) }
    })
    for (let iter = 0; iter < 30; iter++) {
      for (let i = 0; i < nodes.length; i++)
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y
          const dist = Math.max(1, Math.hypot(dx, dy))
          const minDist = nodes[i].r + nodes[j].r + 60
          if (dist < minDist) {
            const f = (minDist - dist) / dist * 0.3
            nodes[i].x -= dx * f; nodes[i].y -= dy * f
            nodes[j].x += dx * f; nodes[j].y += dy * f
          }
        }
      nodes.forEach(n => { n.x += (400 - n.x) * 0.02; n.y += (300 - n.y) * 0.02 })
    }
    const nodeMap = {}; nodes.forEach(n => { nodeMap[n.id] = n })
    const edges = (data.edges || []).map(e => ({ ...e, source: nodeMap[e.from], target: nodeMap[e.to] })).filter(e => e.source && e.target)
    return { nodes, edges }
  }, [data])

  const filtered = useMemo(() => {
    if (!searchQuery) return graphLayout.nodes
    const q = searchQuery.toLowerCase()
    return graphLayout.nodes.filter(n => n.displayName.toLowerCase().includes(q) || n.team.includes(q))
  }, [graphLayout.nodes, searchQuery])

  const COLORS = ['#2563eb','#7c3aed','#059669','#d97706','#dc2626','#0891b2','#4f46e5','#c026d3']

  if (!data?.nodes?.length) return (
    <div className="emptyState"><Database size={32} /><p>No memory data yet.</p><span>Run a pipeline first to populate the knowledge graph.</span></div>
  )

  return (
    <div className="graphContainer">
      <div className="graphToolbar">
        <div className="graphSearch"><Search size={14} />
          <input placeholder="Search teams..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        </div>
        <div className="graphStats"><span>{data.summary?.banks || 0} teams</span><span>{data.summary?.items || 0} artifacts</span></div>
      </div>
      <svg viewBox="0 0 800 600" className="graphSvg">
        <defs>
          {COLORS.map((c, i) => (
            <filter key={i} id={`glow-${i}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          ))}
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#94a3b8" />
          </marker>
        </defs>
        {graphLayout.edges.map((e, i) => (
          <g key={`e-${i}`}>
            <line x1={e.source.x} y1={e.source.y} x2={e.target.x} y2={e.target.y} stroke="#cbd5e1" strokeWidth="1.5" opacity="0.6" markerEnd="url(#arrowhead)" />
          </g>
        ))}
        {filtered.map((node, i) => {
          const color = COLORS[i % COLORS.length], hov = hoveredNode === node.id
          return (
            <g key={node.id} onMouseEnter={() => setHoveredNode(node.id)} onMouseLeave={() => setHoveredNode(null)} onClick={() => onNodeClick?.(node)} style={{ cursor: 'pointer' }}>
              <circle cx={node.x} cy={node.y} r={node.r} fill={color} fillOpacity={hov ? 0.25 : 0.12} stroke={color} strokeWidth={hov ? 2.5 : 1.5} filter={hov ? `url(#glow-${i % COLORS.length})` : undefined} />
              <text x={node.x} y={node.y - 4} textAnchor="middle" fontSize="11" fontWeight="600" fill="#1e293b">{node.displayName}</text>
              <text x={node.x} y={node.y + 10} textAnchor="middle" fontSize="9" fill="#64748b">{node.items} item{node.items !== 1 ? 's' : ''}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Agent Activity Panel
   ═══════════════════════════════════════════════════════════ */
function AgentActivityPanel({ taskStatus }) {
  if (!taskStatus) return null
  const { status, current_team, activities = [] } = taskStatus
  const completed = activities.filter(a => a.status === 'complete').length
  const total = activities.length
  const pct = total ? Math.round((completed / total) * 100) : 0

  const toolIcon = (tool) => {
    const icons = { google_docs: '📄', google_sheets: '📊', mermaid: '📐', tavily_search: '🔍', git: '🔀', gcs: '☁️', google_drive: '📁' }
    return icons[tool] || '🔧'
  }

  const toolLabel = (tool) => {
    const labels = { google_docs: 'Docs', google_sheets: 'Sheets', mermaid: 'Diagram', tavily_search: 'Research', git: 'Git', gcs: 'Storage', google_drive: 'Drive' }
    return labels[tool] || tool
  }

  return (
    <div className="activityPanel">
      <div className="activityHeader">
        <div className="activityTitle"><Activity size={16} /><span>Agent Activity</span></div>
        <div className="activityProgress">
          <div className="progressBar"><div className="progressFill" style={{ width: `${pct}%` }} /></div>
          <span className="progressText">{completed}/{total}</span>
        </div>
      </div>
      {current_team && status === 'running' && (
        <div className="currentAgent"><Loader2 size={14} className="spin" /><span>Active: <strong>{formatTeamName(current_team)}</strong></span></div>
      )}
      <div className="activityGrid">
        {activities.map((a, i) => (
          <div key={i} className={`activityItem status-${a.status}`}>
            <div className="activityItemHeader">
              {a.status === 'complete' ? <CheckCircle2 size={13} /> : a.status === 'in_progress' ? <Loader2 size={13} className="spin" /> : a.status === 'failed' ? <XCircle size={13} /> : <Clock size={13} />}
              <span className="activityTeam">{formatTeamName(a.team)}</span>
            </div>
            {a.action && <p className="activityAction">{a.action}</p>}
            {a.tools_used && a.tools_used.length > 0 && (
              <div className="toolBadges">
                {a.tools_used.map((t, j) => (
                  <span key={j} className={`toolBadge ${t.success ? 'toolSuccess' : 'toolFailed'}`} title={t.action || t.tool}>
                    <span className="toolEmoji">{toolIcon(t.tool)}</span>
                    <span className="toolName">{toolLabel(t.tool)}</span>
                    {t.result?.doc_url && <a href={t.result.doc_url} target="_blank" rel="noopener noreferrer" className="toolLink" onClick={e => e.stopPropagation()}>↗</a>}
                    {t.result?.sheet_url && <a href={t.result.sheet_url} target="_blank" rel="noopener noreferrer" className="toolLink" onClick={e => e.stopPropagation()}>↗</a>}
                    {t.result?.preview_url && <a href={t.result.preview_url} target="_blank" rel="noopener noreferrer" className="toolLink" onClick={e => e.stopPropagation()}>↗</a>}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Preview Panel — Live app execution (Google AI Studio-style)
   ═══════════════════════════════════════════════════════════ */
function PreviewPanel({ taskStatus, onRunPipeline }) {
  const [viewMode, setViewMode] = useState('preview')
  const [selectedFile, setSelectedFile] = useState(null)

  const result = taskStatus?.result || {}
  const codeFiles = result.code_files || {}         // {team: {filename: content}}
  const mdArtifacts = result.artifacts || {}        // {team: metadata-text}

  // Build flat file list for the code tab
  const allFiles = []
  Object.entries(codeFiles).forEach(([team, files]) => {
    Object.entries(files || {}).forEach(([fname, content]) => {
      allFiles.push({ team, fname, content, key: `${team}/${fname}` })
    })
  })

  // Build folder tree for display
  const buildTree = () => {
    const tree = {}  // { 'team/dir': { _files: [...], _dirs: {} } }
    allFiles.forEach(f => {
      const parts = f.fname.split('/')
      const dir = parts.length > 1 ? `${f.team}/${parts.slice(0, -1).join('/')}` : f.team
      if (!tree[dir]) tree[dir] = { label: dir, files: [] }
      tree[dir].files.push(f)
    })
    // Group by team root
    const teams = {}
    Object.values(tree).forEach(({ label, files }) => {
      const teamKey = label.split('/')[0]
      if (!teams[teamKey]) teams[teamKey] = { dirs: {}, files: [] }
      const subPath = label.split('/').slice(1).join('/')
      if (!subPath) {
        teams[teamKey].files.push(...files)
      } else {
        if (!teams[teamKey].dirs[subPath]) teams[teamKey].dirs[subPath] = []
        teams[teamKey].dirs[subPath].push(...files)
      }
    })
    return teams
  }
  const fileTree = buildTree()

  // Pick first file by default
  useEffect(() => {
    if (allFiles.length > 0 && !selectedFile) setSelectedFile(allFiles[0].key)
  }, [taskStatus]) // eslint-disable-line

  const currentFile = allFiles.find(f => f.key === selectedFile)

  // ── Build runnable preview document from frontend_eng code ──
  const buildRunnable = () => {
    const feFiles = codeFiles.frontend_eng || {}
    const appJsx = feFiles['src/App.jsx'] || feFiles['src/app.jsx'] || feFiles['App.jsx'] || ''
    const allJsx = Object.values(feFiles).filter(c => c && (c.includes('function ') || c.includes('=>') || c.includes('const '))).join('\n\n')
    const jsxCode = appJsx || allJsx

    // Extract CSS if any
    const cssMatch = jsxCode.match(/<style[^>]*>([\s\S]*?)<\/style>/i)
    const inlineStyle = cssMatch ? cssMatch[1] : ''
    const codeWithoutStyle = jsxCode.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')

    // Strip ES module syntax and markdown fences before handing to Babel
    const cleanCode = codeWithoutStyle
      .replace(/^```[a-zA-Z0-9]*\s*\n?/gm, '')            // ``` ```jsx ```tsx etc.
      .replace(/^```\s*$/gm, '')                           // closing ```
      .replace(/import\s+type\s+[\s\S]*?;?\n?/g, '')      // import type ...
      .replace(/import\s+[\s\S]*?from\s+['"][^'"]+['"];?\n?/g, '') // import ... from '...'
      .replace(/import\s+['"][^'"]+['"];?\n?/g, '')       // import '...'
      .replace(/export\s+default\s+/g, '')                // export default
      .replace(/export\s+\{[^}]*\};?\n?/g, '')            // export { Foo, Bar }
      .replace(/^export\s+/gm, '')                        // export function/const

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Factory Preview</title>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; }
    #root { max-width: 900px; margin: 0 auto; }
    ${inlineStyle}
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    /* React/ReactDOM available as globals from CDN */
    const { useState, useEffect, useCallback, useMemo, useRef } = React;

    ${cleanCode}

    /* \u2500\u2500 Mount: typeof checks work in Babel strict mode; eval() does NOT \u2500\u2500 */
    try {
      const __comp =
        typeof App         === 'function' ? App         :
        typeof Calculator  === 'function' ? Calculator  :
        typeof TodoApp     === 'function' ? TodoApp     :
        typeof Main        === 'function' ? Main        :
        typeof Page        === 'function' ? Page        :
        typeof Application === 'function' ? Application :
        typeof Dashboard   === 'function' ? Dashboard   :
        typeof Component   === 'function' ? Component   :
        null;

      const __root = ReactDOM.createRoot(document.getElementById('root'));
      if (__comp) {
        __root.render(React.createElement(__comp));
      } else {
        __root.render(
          React.createElement('div', { style: { padding: '32px', textAlign: 'center', color: '#64748b' } },
            React.createElement('h2', null, '\u26a0\ufe0f No Component Found'),
            React.createElement('p', null, 'Expected a root component named: App, Calculator, Main, Page, Dashboard, etc.'),
            React.createElement('p', { style: { fontSize: '12px', color: '#94a3b8' } }, 'Check the Code tab for the generated source.')
          )
        );
      }
    } catch (e) {
      ReactDOM.createRoot(document.getElementById('root')).render(
        React.createElement('div', { style: { padding: '32px', color: '#dc2626' } },
          React.createElement('h2', null, '\u274c Runtime Error'),
          React.createElement('pre', {
            style: { background: '#fee2e2', padding: '12px', borderRadius: '6px', fontSize: '12px', whiteSpace: 'pre-wrap', overflowX: 'auto' }
          }, String(e))
        )
      );
    }
  </script>
</body>
</html>`
  }

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Factory Preview</title>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; }
    #root { max-width: 900px; margin: 0 auto; }
    ${inlineStyle}
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    /* React/ReactDOM available as globals from CDN */
    const { useState, useEffect, useCallback, useMemo, useRef } = React;

    ${cleanCode}

    /* ── Mount: typeof checks work in Babel strict mode; eval() does NOT ── */
    try {
      const __comp =
        typeof App         === 'function' ? App         :
        typeof Calculator  === 'function' ? Calculator  :
        typeof TodoApp     === 'function' ? TodoApp     :
        typeof Main        === 'function' ? Main        :
        typeof Page        === 'function' ? Page        :
        typeof Application === 'function' ? Application :
        typeof Dashboard   === 'function' ? Dashboard   :
        typeof Component   === 'function' ? Component   :
        null;

      const __root = ReactDOM.createRoot(document.getElementById('root'));
      if (__comp) {
        __root.render(React.createElement(__comp));
      } else {
        __root.render(
          React.createElement('div', { style: { padding: '32px', textAlign: 'center', color: '#64748b' } },
            React.createElement('h2', null, '\u26a0\ufe0f No Component Found'),
            React.createElement('p', null, 'Expected a root component named: App, Calculator, Main, Page, Dashboard, etc.'),
            React.createElement('p', { style: { fontSize: '12px', color: '#94a3b8' } }, 'Check the Code tab for the generated source.')
          )
        );
      }
    } catch (e) {
      ReactDOM.createRoot(document.getElementById('root')).render(
        React.createElement('div', { style: { padding: '32px', color: '#dc2626' } },
          React.createElement('h2', null, '\u274c Runtime Error'),
          React.createElement('pre', {
            style: { background: '#fee2e2', padding: '12px', borderRadius: '6px', fontSize: '12px', whiteSpace: 'pre-wrap', overflowX: 'auto' }
          }, String(e))
        )
      );
    }
  </script>
</body>
</html>`
  }

  const hasCode = allFiles.length > 0
  const hasFrontend = !!(codeFiles.frontend_eng && Object.keys(codeFiles.frontend_eng).length > 0)

  // Team label for code tab
  const teamLabel = (key) => key.split('/')[0].replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

  const status = taskStatus?.status

  return (
    <div className="previewPanel">
      {/* Toolbar */}
      <div className="previewToolbar">
        <div className="previewLeft">
          <span className="previewTitle"><Monitor size={15} /> Live Preview</span>
          {status === 'completed' && (
            <span className="previewMeta">
              {Object.keys(codeFiles).length} team{Object.keys(codeFiles).length !== 1 ? 's' : ''} · {allFiles.length} file{allFiles.length !== 1 ? 's' : ''}
              {hasFrontend && <span className="previewTag">React App</span>}
            </span>
          )}
        </div>
        <div className="previewViewToggle">
          <button className={`previewToggleBtn ${viewMode === 'preview' ? 'active' : ''}`}
            onClick={() => setViewMode('preview')} disabled={!hasFrontend}>
            <Eye size={13} /> App
          </button>
          <button className={`previewToggleBtn ${viewMode === 'code' ? 'active' : ''}`}
            onClick={() => setViewMode('code')} disabled={!hasCode}>
            <Code2 size={13} /> Code
          </button>
          <button className={`previewToggleBtn ${viewMode === 'artifacts' ? 'active' : ''}`}
            onClick={() => setViewMode('artifacts')} disabled={Object.keys(mdArtifacts).length === 0}>
            <Activity size={13} /> Artifacts
          </button>
        </div>
      </div>

      {/* No run yet */}
      {!status && (
        <div className="previewEmpty">
          <Monitor size={48} className="previewEmptyIcon" />
          <h3>No run yet</h3>
          <p>Run a pipeline to see your application rendered live here — like Google AI Studio.</p>
          {onRunPipeline && (
            <button className="previewGoBtn" onClick={onRunPipeline}>
              <Play size={14} /> Go to Pipeline
            </button>
          )}
          <span className="previewHint">
            Generated React code renders in a live sandboxed iframe. Code files and artifacts are also browseable.
          </span>
        </div>
      )}

      {/* Running state */}
      {status === 'running' && (
        <div className="previewEmpty">
          <Loader2 size={40} className="spin previewEmptyIcon" style={{ color: '#2563eb' }} />
          <h3>Pipeline running…</h3>
          <p>Preview will appear here when the pipeline completes.</p>
        </div>
      )}

      {/* App preview */}
      {status === 'completed' && viewMode === 'preview' && (
        hasFrontend ? (
          <iframe
            key={JSON.stringify(codeFiles.frontend_eng).slice(0, 40)}
            className="previewFrame"
            srcDoc={buildRunnable()}
            sandbox="allow-scripts allow-forms allow-modals allow-popups"
            title="Live App Preview"
          />
        ) : (
          <div className="previewEmpty">
            <Monitor size={40} className="previewEmptyIcon" />
            <h3>No frontend code</h3>
            <p>This run did not produce frontend code. Switch to <strong>Artifacts</strong> to see the team outputs.</p>
          </div>
        )
      )}

      {/* Code browser — folder tree */}
      {status === 'completed' && viewMode === 'code' && (
        <div className="previewCodeLayout">
          <div className="previewFileTree">
            <div className="previewFileTreeHeader">
              <FolderOpen size={13} style={{ marginRight: 4 }} />
              Project Structure
            </div>
            {Object.keys(fileTree).length === 0 && (
              <div className="previewNoFiles">No code files yet</div>
            )}
            {Object.entries(fileTree).map(([teamKey, { dirs, files: rootFiles }]) => (
              <div key={teamKey} className="previewTreeTeam">
                {/* Team root folder */}
                <div className="previewTreeDir previewTreeRoot">
                  <Folder size={13} style={{ color: '#f59e0b', marginRight: 4, flexShrink: 0 }} />
                  <span>{teamKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                </div>
                {/* Root-level files */}
                {rootFiles.map(f => (
                  <button key={f.key}
                    className={`previewFileBtn previewFileDepth1 ${selectedFile === f.key ? 'active' : ''}`}
                    onClick={() => setSelectedFile(f.key)}>
                    <FileCode size={12} style={{ color: '#64748b', marginRight: 4, flexShrink: 0 }} />
                    <span className="previewFileName">{f.fname.split('/').pop()}</span>
                  </button>
                ))}
                {/* Sub-directories */}
                {Object.entries(dirs).map(([dirPath, dirFiles]) => (
                  <div key={dirPath}>
                    <div className="previewTreeDir previewFileDepth1">
                      <Folder size={12} style={{ color: '#f59e0b', marginRight: 4, flexShrink: 0 }} />
                      <span>{dirPath}</span>
                    </div>
                    {dirFiles.map(f => (
                      <button key={f.key}
                        className={`previewFileBtn previewFileDepth2 ${selectedFile === f.key ? 'active' : ''}`}
                        onClick={() => setSelectedFile(f.key)}>
                        <FileCode size={12} style={{ color: '#64748b', marginRight: 4, flexShrink: 0 }} />
                        <span className="previewFileName">{f.fname.split('/').pop()}</span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="previewCodePane">
            {currentFile ? (
              <>
                <div className="previewCodeHeader">
                  <span className="previewCodePath">{currentFile.key}</span>
                  <button className="previewCopyBtn" title="Copy" onClick={() => navigator.clipboard?.writeText(currentFile.content)}>
                    <Copy size={12} />
                  </button>
                </div>
                <pre className="previewCode">{currentFile.content}</pre>
              </>
            ) : (
              <div className="previewNoFiles" style={{ padding: '32px', textAlign: 'center' }}>
                <FolderOpen size={32} style={{ color: '#cbd5e1', marginBottom: 8 }} />
                <p>Select a file from the tree</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Artifacts (markdown team summaries) */}
      {status === 'completed' && viewMode === 'artifacts' && (
        <div className="previewArtifactsPane">
          {Object.entries(mdArtifacts).map(([team, content]) => (
            <div key={team} className="previewArtifactCard">
              <div className="previewArtifactTeam">{team.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</div>
              <pre className="previewArtifactContent">{content}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Multi-select Team Picker
   ═══════════════════════════════════════════════════════════ */
function TeamMultiSelect({ selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])
  const toggle = t => {
    const s = new Set(selected); s.has(t) ? s.delete(t) : s.add(t); onChange(Array.from(s))
  }
  return (
    <div className="multiSelect" ref={ref}>
      <button type="button" className="multiSelectTrigger" onClick={() => setOpen(!open)}>
        <div className="multiSelectTags">
          {selected.length === 0 && <span className="multiSelectPlaceholder">Select teams...</span>}
          {selected.map(t => <span key={t} className="teamTag">{formatTeamName(t)}<button type="button" onClick={e => { e.stopPropagation(); toggle(t) }}>&times;</button></span>)}
        </div>
        <ChevronDown size={16} className={`multiSelectChevron ${open ? 'rotated' : ''}`} />
      </button>
      {open && (
        <div className="multiSelectDropdown">
          <div className="multiSelectActions">
            <button type="button" onClick={() => onChange([...ALL_TEAMS])}>Select All</button>
            <button type="button" onClick={() => onChange([])}>Clear All</button>
          </div>
          {ALL_TEAMS.map(t => <label key={t} className="multiSelectOption"><input type="checkbox" checked={selected.includes(t)} onChange={() => toggle(t)} /><span>{formatTeamName(t)}</span></label>)}
        </div>
      )}
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Login Page
   ═══════════════════════════════════════════════════════════ */
function LoginPage({ onLogin, loading: parentLoading }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async () => {
    setLoading(true); setError('')
    try { await signInWithGoogle() }
    catch (e) { setError(e.message || 'Sign-in failed') }
    finally { setLoading(false) }
  }

  return (
    <div className="loginPage">
      <div className="loginCard">
        <div className="loginBrand">
          <Bot size={40} className="brandIcon" />
          <h1>AI Factory</h1>
          <p>Your AI-Powered Software Delivery Team</p>
        </div>
        <div className="loginFeatures">
          <div className="loginFeature"><Cloud size={16} /><span>17 specialized AI teams</span></div>
          <div className="loginFeature"><GitBranch size={16} /><span>Git integration for artifacts</span></div>
          <div className="loginFeature"><Shield size={16} /><span>Your own private workspace</span></div>
        </div>
        <button className="loginBtn" onClick={handleLogin} disabled={loading || parentLoading}>
          {loading || parentLoading ? <Loader2 size={20} className="spin" /> : (
            <>
              <svg width="20" height="20" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59A14.5 14.5 0 019.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.9 23.9 0 000 24c0 3.77.9 7.33 2.44 10.49l8.09-5.9z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
              Sign in with Google
            </>
          )}
        </button>
        {error && <div className="loginError"><XCircle size={14} /> {error}</div>}
      </div>
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Project Selector
   ═══════════════════════════════════════════════════════════ */
function ProjectSelector({ user, onSelect, onLogout }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [gitUrl, setGitUrl] = useState('')
  const [gitToken, setGitToken] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => { loadProjects() }, [])

  async function loadProjects() {
    setLoading(true)
    try {
      const data = await api('/api/projects')
      setProjects(data.projects || [])
    } catch { setProjects([]) }
    finally { setLoading(false) }
  }

  async function createProject(e) {
    e.preventDefault()
    if (!newName.trim()) return
    setCreating(true)
    try {
      const body = { name: newName.trim() }
      if (gitUrl.trim()) { body.git_url = gitUrl.trim(); body.git_token = gitToken.trim() || null }
      const project = await api('/api/projects', { method: 'POST', body: JSON.stringify(body) })
      setNewName(''); setGitUrl(''); setGitToken('')
      await loadProjects()
      onSelect(project.id || project.project_id)
    } catch (e) { alert(e.message) }
    finally { setCreating(false) }
  }

  async function deleteProject(pid) {
    if (!confirm(`Delete project "${pid}"?`)) return
    try { await api(`/api/projects/${pid}`, { method: 'DELETE' }); await loadProjects() }
    catch (e) { alert(e.message) }
  }

  return (
    <div className="projectSelectorPage">
      <div className="projectSelectorHeader">
        <div className="projectSelectorBrand">
          <Bot size={28} className="brandIcon" />
          <h2>AI Factory</h2>
        </div>
        <div className="userBadge">
          <img src={user.photoURL} alt="" className="userAvatar" referrerPolicy="no-referrer" />
          <span>{user.displayName || user.email}</span>
          <button className="iconBtn" onClick={onLogout} title="Sign out"><LogOut size={16} /></button>
        </div>
      </div>

      <div className="projectSelectorBody">
        <div className="projectsList">
          <h3><FolderOpen size={18} /> Your Projects</h3>
          {loading && <div className="loadingState"><Loader2 size={20} className="spin" /> Loading...</div>}
          {!loading && projects.length === 0 && (
            <div className="emptyState"><FolderOpen size={32} /><p>No projects yet</p><span>Create your first project below.</span></div>
          )}
          {projects.map(p => (
            <div key={p.id} className="projectCard" onClick={() => onSelect(p.id)}>
              <div className="projectCardLeft">
                <FolderOpen size={18} />
                <div>
                  <div className="projectCardName">{p.name || p.id}</div>
                  <div className="projectCardMeta">
                    {p.updated_at && <span>Updated: {new Date(p.updated_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              </div>
              <div className="projectCardActions">
                <button className="iconBtn danger" onClick={e => { e.stopPropagation(); deleteProject(p.id) }} title="Delete"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>

        <div className="newProjectCard">
          <h3><Plus size={18} /> Create New Project</h3>
          <form onSubmit={createProject}>
            <div className="fieldRow">
              <label>Project Name</label>
              <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="e.g. kanban-app" required />
            </div>
            <div className="fieldRow">
              <label className="labelWithIcon"><GitBranch size={14} /> Git Repository <span className="labelOptional">(optional)</span></label>
              <p className="fieldHint">If set, pipeline artifacts are pushed to Git instead of cloud storage.</p>
              <input value={gitUrl} onChange={e => setGitUrl(e.target.value)} placeholder="https://github.com/you/repo.git" />
            </div>
            {gitUrl && (
              <div className="fieldRow">
                <label className="labelWithIcon"><Key size={14} /> Git Token <span className="labelOptional">(for private repos)</span></label>
                <input type="password" value={gitToken} onChange={e => setGitToken(e.target.value)} placeholder="Personal Access Token" />
              </div>
            )}
            <button type="submit" className="primaryBtn" disabled={creating || !newName.trim()}>
              {creating ? <Loader2 size={16} className="spin" /> : <><Plus size={16} /> Create Project</>}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════
   Main App
   ═══════════════════════════════════════════════════════════ */
export default function App() {
  /* ─── Auth state ─── */
  const [firebaseUser, setFirebaseUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [projectId, setProjectId] = useState('')

  useEffect(() => {
    const unsub = onAuthChange(user => { setFirebaseUser(user); setAuthLoading(false) })
    return unsub
  }, [])

  const handleLogout = async () => { await logOut(); setFirebaseUser(null); setProjectId('') }

  /* ─── Not authenticated ─── */
  if (authLoading) return (
    <div className="loginPage"><div className="loadingState"><Loader2 size={32} className="spin" /><p>Loading...</p></div></div>
  )
  if (!firebaseUser) return <LoginPage loading={authLoading} />
  if (!projectId) return <ProjectSelector user={firebaseUser} onSelect={setProjectId} onLogout={handleLogout} />

  /* ─── Workspace ─── */
  return <Workspace user={firebaseUser} projectId={projectId} onChangeProject={() => setProjectId('')} onLogout={handleLogout} />
}


/* ═══════════════════════════════════════════════════════════
   Workspace (authenticated + project selected)
   ═══════════════════════════════════════════════════════════ */
function Workspace({ user, projectId, onChangeProject, onLogout }) {
  const [activeTab, setActiveTab] = useState('chat')
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [chatHistory, setChatHistory] = useState([{ id: 1, role: 'assistant', text: 'Hello! How can I help you with your project today?' }])
  const [pipelineHistory, setPipelineHistory] = useState([{ id: 1, role: 'assistant', text: 'Describe the requirement to build, and I\'ll run the delivery pipeline.' }])
  const [groupHistory, setGroupHistory] = useState([{ id: 1, role: 'assistant', text: 'Select teams and enter a topic to start a discussion.' }])

  const [governance, setGovernance] = useState(null)
  const [selectedTeam, setSelectedTeam] = useState('')
  const [teamModel, setTeamModel] = useState('factory/cheap')
  const [teamBudget, setTeamBudget] = useState('0.50')
  const [teamApiKey, setTeamApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)

  const [memoryMap, setMemoryMap] = useState(null)
  const [selectedMemoryNode, setSelectedMemoryNode] = useState(null)
  const [groupParticipants, setGroupParticipants] = useState(['backend_eng','qa_eng','docs_team'])
  const [trackedTaskId, setTrackedTaskId] = useState('')
  const [taskStatus, setTaskStatus] = useState(null)

  /* Git config for this project */
  const [gitConfig, setGitConfig] = useState(null)
  const [gitUrl, setGitUrl] = useState('')
  /* User-level GitHub PAT — stored once, used for all projects */
  const [userGitTokenSet, setUserGitTokenSet] = useState(false)
  const [gitPatInput, setGitPatInput] = useState('')
  const [showPat, setShowPat] = useState(false)

  const messagesEndRef = useRef(null)
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatHistory, pipelineHistory, groupHistory, taskStatus])

  /* Load git config on workspace mount so the storage indicator is correct */
  useEffect(() => {
    api(`/api/projects/${projectId}/git`)
      .then(gc => { setGitConfig(gc); setGitUrl(gc.git_url || '') })
      .catch(() => setGitConfig(null))
    api('/api/user/git-token')
      .then(r => setUserGitTokenSet(r.token_set || false))
      .catch(() => {})
  }, [projectId])

  /* Restore session (chat history + last pipeline run) on project load */
  useEffect(() => {
    api(`/api/projects/${projectId}/session`)
      .then(session => {
        if (session.chat_history && session.chat_history.length > 0) {
          setChatHistory([
            { id: 1, role: 'assistant', text: '👋 Welcome back! Previous conversation restored.' },
            ...session.chat_history.map((m, i) => ({ id: i + 2, role: m.role, text: m.text })),
          ])
        }
        if (session.last_run) {
          const run = session.last_run
          const taskId = session.last_task_id
          setTaskStatus({ status: run.status || 'completed', result: run })
          if (taskId) setTrackedTaskId(taskId)
          setPipelineHistory([
            { id: 1, role: 'assistant', text: '🔄 Last pipeline run restored from session.' },
            {
              id: 2, role: 'assistant',
              text: `✅ **${run.project_id || projectId}** — run \`${taskId}\` restored.`,
              result: run,
            },
          ])
        }
      })
      .catch(() => { /* silently ignore — fresh session */ })
  }, [projectId])

  const navItems = [
    { key: 'chat', label: 'Project Chat', icon: MessageSquare },
    { key: 'pipeline', label: 'Run Pipeline', icon: Play },
    { key: 'preview', label: 'Live Preview', icon: Monitor },
    { key: 'group', label: 'Group Chat', icon: Users },
    { key: 'memory', label: 'Memory Map', icon: Database },
    { key: 'settings', label: 'Settings', icon: Settings },
  ]

  async function handleApi(fn) {
    setLoading(true); setError('')
    try { return await fn() }
    catch (e) { setError(e?.message || 'Request failed'); return null }
    finally { setLoading(false) }
  }

  /* ─── Pipeline ─── */
  async function startPipeline(requirement) {
    const isFollowup = !!(taskStatus?.result?.code_files && Object.keys(taskStatus.result.code_files).length > 0)
    const body = {
      project_id: projectId,
      requirement,
      ...(isFollowup && {
        is_followup: true,
        existing_code: taskStatus.result.code_files,
      }),
    }
    setPipelineHistory(prev => [...prev, {
      id: Date.now(), role: 'user',
      text: isFollowup ? `✏️ Follow-up: ${requirement}` : requirement,
    }])
    const data = await handleApi(() => api('/api/pipelines/full/run/async', {
      method: 'POST', body: JSON.stringify(body),
    }))
    if (!data?.task_id) { setPipelineHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: 'Failed to start.' }]); return }
    setTrackedTaskId(data.task_id)
    setTaskStatus({ status: 'running', activities: [] })
    setPipelineHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: `Pipeline started — ${data.task_id}`, taskId: data.task_id }])
  }

  useEffect(() => {
    if (!trackedTaskId) return
    let cancelled = false
    const timer = setInterval(async () => {
      if (cancelled) return
      try {
        const data = await api(`/api/tasks/${trackedTaskId}`)
        setTaskStatus(data)
        if (data.status === 'completed') {
          setPipelineHistory(prev => [...prev, {
            id: Date.now(), role: 'assistant',
            text: `Pipeline completed! Artifacts stored: ${data.result?.storage?.type || 'cloud'}`,
            result: data.result,
          }])
          loadMemoryMap()
          clearInterval(timer); setTrackedTaskId('')
        }
        if (data.status === 'failed') {
          setPipelineHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: `Failed: ${data.error}` }])
          clearInterval(timer); setTrackedTaskId('')
        }
      } catch {}
    }, 1000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [trackedTaskId])

  /* ─── Governance ─── */
  async function loadGovernance() {
    const data = await handleApi(() => api('/api/governance/budgets'))
    if (!data) return
    setGovernance(data)
    const first = Object.keys(data.teams || {})[0] || ''
    if (first) chooseTeam(first, data)
    // Also load Git config
    try {
      const gc = await api(`/api/projects/${projectId}/git`)
      setGitConfig(gc); setGitUrl(gc.git_url || '')
    } catch { setGitConfig(null) }
  }

  function chooseTeam(team, gov) {
    const g = gov || governance
    setSelectedTeam(team)
    if (!g?.teams?.[team]) return
    setTeamModel(g.teams[team].model)
    setTeamBudget(String(g.teams[team].limit_usd))
    setTeamApiKey(''); setShowApiKey(false)
  }

  async function saveTeamSettings() {
    if (!selectedTeam) return
    const body = { model: teamModel, budget_usd: Number(teamBudget) }
    if (teamApiKey.trim()) body.api_key = teamApiKey.trim()
    const data = await handleApi(() => api(`/api/governance/teams/${selectedTeam}`, { method: 'PUT', body: JSON.stringify(body) }))
    if (data) { setTeamApiKey(''); setShowApiKey(false); await loadGovernance() }
  }

  async function saveGitConfig() {
    if (!gitUrl.trim()) return
    await handleApi(() => api(`/api/projects/${projectId}/git`, {
      method: 'PUT', body: JSON.stringify({ git_url: gitUrl.trim() }),
    }))
    try { const gc = await api(`/api/projects/${projectId}/git`); setGitConfig(gc) } catch {}
  }

  async function removeGitConfig() {
    await handleApi(() => api(`/api/projects/${projectId}/git`, { method: 'DELETE' }))
    setGitConfig(null); setGitUrl('')
  }

  async function savePat() {
    if (!gitPatInput.trim()) return
    const r = await handleApi(() => api('/api/user/git-token', {
      method: 'PUT', body: JSON.stringify({ token: gitPatInput.trim() }),
    }))
    if (r) { setUserGitTokenSet(true); setGitPatInput(''); setShowPat(false) }
  }

  async function deletePat() {
    await handleApi(() => api('/api/user/git-token', { method: 'DELETE' }))
    setUserGitTokenSet(false)
  }

  /* ─── Memory ─── */
  async function loadMemoryMap() {
    const data = await handleApi(() => api(`/api/projects/${projectId}/memory-map`))
    if (data) setMemoryMap(data)
  }

  /* ─── Chat ─── */
  async function sendChat(message) {
    setChatHistory(prev => [...prev, { id: Date.now(), role: 'user', text: message }])
    const data = await handleApi(() => api(`/api/projects/${projectId}/chat`, {
      method: 'POST', body: JSON.stringify({ message }),
    }))
    setChatHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: data?.answer || 'Sorry, error occurred.' }])
  }

  /* ─── Group Chat ─── */
  async function runGroupChat(topic) {
    setGroupHistory(prev => [...prev, { id: Date.now(), role: 'user', text: topic }])
    const data = await handleApi(() => api(`/api/projects/${projectId}/group-chat`, {
      method: 'POST', body: JSON.stringify({ topic, participants: groupParticipants }),
    }))
    if (data) setGroupHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: 'Group chat completed.', result: data }])
    else setGroupHistory(prev => [...prev, { id: Date.now(), role: 'assistant', text: 'Error occurred.' }])
  }

  const handleSubmit = e => {
    e.preventDefault(); if (!inputMessage.trim() || loading) return
    const msg = inputMessage.trim(); setInputMessage('')
    if (activeTab === 'chat') sendChat(msg)
    else if (activeTab === 'pipeline') startPipeline(msg)
    else if (activeTab === 'group') runGroupChat(msg)
  }

  const renderMessage = msg => {
    const isUser = msg.role === 'user'
    return (
      <div key={msg.id} className={`messageWrapper ${isUser ? 'user' : 'assistant'}`}>
        <div className="messageAvatar">{isUser ? <User size={18} /> : <Bot size={18} />}</div>
        <div className="messageContent">
          <div className="messageText">{msg.text}</div>
          {msg.result && <div className="resultBox"><h4>Result</h4><pre>{JSON.stringify(msg.result, null, 2)}</pre></div>}
        </div>
      </div>
    )
  }

  const renderModelSelect = () => (
    <div className="modelSelectWrapper">
      <select value={teamModel} onChange={e => setTeamModel(e.target.value)}>
        {Object.entries(MODEL_CATALOG).map(([group, models]) => (
          <optgroup key={group} label={group}>
            {Object.entries(models).map(([key, info]) => (
              <option key={key} value={key}>{info.label} {info.keyRequired ? `(needs ${info.keyRequired})` : ''}</option>
            ))}
          </optgroup>
        ))}
      </select>
      {MODEL_FLAT[teamModel] && (
        <div className="modelMeta">
          <span className="modelDot" style={{ background: MODEL_FLAT[teamModel].color }} />
          <span className="modelDesc">{MODEL_FLAT[teamModel].desc}</span>
          {MODEL_FLAT[teamModel].keyRequired && <span className="modelKeyHint"><Key size={11} /> Requires {MODEL_FLAT[teamModel].keyRequired}</span>}
        </div>
      )}
    </div>
  )

  /* ═══════ RENDER ═══════ */
  return (
    <main className="page appShell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand"><Bot size={24} className="brandIcon" /><div><div className="brandTitle">AI Factory</div><div className="brandSub">Your AI Coworker</div></div></div>

        {/* User info */}
        <div className="sidebarUser">
          <img src={user.photoURL} alt="" className="userAvatarSmall" referrerPolicy="no-referrer" />
          <div className="sidebarUserInfo">
            <span className="sidebarUserName">{user.displayName || user.email}</span>
            <button className="linkBtn" onClick={onLogout}><LogOut size={12} /> Sign out</button>
          </div>
        </div>

        {/* Project */}
        <div className="projectSelector">
          <label>Project</label>
          <div className="projectSelectorRow">
            <span className="projectName">{projectId}</span>
            <button className="linkBtn" onClick={onChangeProject}>Switch</button>
          </div>
          {/* Storage indicator */}
          <div className="storageIndicator">
            {gitConfig?.git_url ? (
              <><GitBranch size={12} /> <span>Git: {gitConfig.git_url.split('/').pop()?.replace('.git','')}</span>{userGitTokenSet ? null : <span style={{color:'#f59e0b', marginLeft:4}}>⚠ no PAT</span>}</>
            ) : (
              <><Cloud size={12} /> <span>Cloud Storage (GCS)</span></>
            )}
          </div>
        </div>

        <nav className="sideNav">
          {navItems.map(item => {
            const Icon = item.icon
            return (
              <button key={item.key} className={`navBtn ${activeTab === item.key ? 'active' : ''}`}
                onClick={() => { setActiveTab(item.key); if (item.key === 'settings') loadGovernance(); if (item.key === 'memory') loadMemoryMap() }}
                title={NAV_DESCRIPTIONS[item.key]}>
                <Icon size={18} />{item.label}
              </button>
            )
          })}
        </nav>

        {/* Live pipeline indicator */}
        {taskStatus?.status === 'running' && (
          <div className="sidebarActivity">
            <div className="sidebarActivityHeader"><Loader2 size={13} className="spin" /><span>Pipeline Running</span></div>
            <div className="sidebarActivityTeam"><Zap size={12} /> {formatTeamName(taskStatus.current_team)}</div>
            <div className="sidebarActivityBar">
              <div className="sidebarActivityFill" style={{ width: `${taskStatus.activities?.length ? Math.round(taskStatus.activities.filter(a => a.status === 'complete').length / taskStatus.activities.length * 100) : 0}%` }} />
            </div>
          </div>
        )}

        <div className="sidebarFooter"><div className="statusDot" /><span>Connected</span></div>
      </aside>

      {/* Main */}
      <section className="mainArea">
        <header className="topbar">
          <div className="topbarLeft">
            <h2>{navItems.find(i => i.key === activeTab)?.label}</h2>
            <p className="topbarDesc">{NAV_DESCRIPTIONS[activeTab]}</p>
          </div>
          {error && <div className="errorBadge"><XCircle size={14} /> {error}</div>}
        </header>

        <div className="contentArea">
          {/* Chat */}
          {activeTab === 'chat' && (
            <div className="chatContainer"><div className="messagesList">{chatHistory.map(renderMessage)}<div ref={messagesEndRef} /></div></div>
          )}

          {/* Pipeline */}
          {activeTab === 'pipeline' && (
            <div className="pipelineLayoutWrapper">
              {taskStatus?.status === 'completed' && (
                <div className="previewBanner">
                  <CheckCircle2 size={15} />
                  <span>Pipeline complete! Generated code is ready to preview.</span>
                  <button className="previewBannerBtn" onClick={() => setActiveTab('preview')}>
                    <Monitor size={13} /> View Live Preview →
                  </button>
                </div>
              )}
              <div className="pipelineLayout">
                <div className="chatContainer pipelineChat"><div className="messagesList">{pipelineHistory.map(renderMessage)}<div ref={messagesEndRef} /></div></div>
                {taskStatus && <AgentActivityPanel taskStatus={taskStatus} />}
              </div>
            </div>
          )}

          {/* Live Preview */}
          {activeTab === 'preview' && (
            <PreviewPanel taskStatus={taskStatus} onRunPipeline={() => setActiveTab('pipeline')} />
          )}

          {/* Group Chat */}
          {activeTab === 'group' && (
            <div className="chatContainer">
              <div className="groupConfig">
                <label>Select Participants</label>
                <TeamMultiSelect selected={groupParticipants} onChange={setGroupParticipants} />
              </div>
              <div className="messagesList">{groupHistory.map(renderMessage)}<div ref={messagesEndRef} /></div>
            </div>
          )}

          {/* Memory */}
          {activeTab === 'memory' && (
            <div className="settingsPanel">
              <div className="settingsHeader">
                <div><h3>Knowledge Graph</h3><p>Artifacts and team outputs for <strong>{projectId}</strong>.</p></div>
                <button className="primaryBtn" onClick={loadMemoryMap} disabled={loading}>{loading ? <Loader2 size={16} className="spin" /> : 'Refresh'}</button>
              </div>
              <MemoryGraph data={memoryMap} onNodeClick={node => setSelectedMemoryNode(node)} />
              {selectedMemoryNode && (
                <div className="nodeDetail">
                  <div className="nodeDetailHeader">
                    <h4>{selectedMemoryNode.displayName || formatTeamName(selectedMemoryNode.team)}</h4>
                    <button className="iconBtn" onClick={() => setSelectedMemoryNode(null)}><XCircle size={16} /></button>
                  </div>
                  <p>Bank: <code>{selectedMemoryNode.id}</code></p>
                  <p>Artifacts: <strong>{selectedMemoryNode.items}</strong></p>
                </div>
              )}
            </div>
          )}

          {/* Settings */}
          {activeTab === 'settings' && (
            <div className="settingsPanel">
              <div className="settingsHeader">
                <div><h3>Team & Project Configuration</h3><p>Models, budgets, API keys, and Git settings.</p></div>
                {!governance && <button className="primaryBtn" onClick={loadGovernance}>Load Settings</button>}
              </div>
              {governance && (
                <div className="settingsLayout">
                  {/* GitHub PAT — user-level, set once for all projects */}
                  <div className="card gitCard">
                    <div className="cardHeader"><Key size={18} /><h4>GitHub Token (PAT)</h4></div>
                    <p className="fieldHint">Your Personal Access Token — stored once for your account and used across all projects when pushing to GitHub.</p>
                    {userGitTokenSet ? (
                      <div className="gitActiveBox">
                        <div className="gitActiveInfo">
                          <Key size={16} />
                          <div>
                            <strong>Token saved</strong>
                            <span className="gitUrlDisplay" style={{ color: '#64748b', fontSize: '12px' }}>github.com PAT · applies to all projects</span>
                          </div>
                        </div>
                        <button className="dangerBtn" onClick={deletePat}><Trash2 size={14} /> Remove Token</button>
                      </div>
                    ) : (
                      <div className="gitSetupForm">
                        <p className="fieldHint" style={{ color: '#f59e0b' }}>⚠ No token set — Git push will fail for private repos.</p>
                        <p className="fieldHint">Generate at <strong>github.com → Settings → Developer Settings → Personal access tokens</strong>. Needs <code>repo</code> scope.</p>
                        <div className="fieldRow">
                          <label className="labelWithIcon"><Key size={14} /> Personal Access Token</label>
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <input
                              type={showPat ? 'text' : 'password'}
                              value={gitPatInput}
                              onChange={e => setGitPatInput(e.target.value)}
                              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                              style={{ flex: 1 }}
                            />
                            <button className="iconBtn" onClick={() => setShowPat(v => !v)} title="Toggle visibility">
                              {showPat ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                          </div>
                        </div>
                        <button className="primaryBtn" onClick={savePat} disabled={!gitPatInput.trim() || loading}>
                          <Key size={14} /> Save Token
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Git Config Card — repo URL per project */}
                  <div className="card gitCard">
                    <div className="cardHeader"><GitBranch size={18} /><h4>Artifact Storage</h4></div>
                    <p className="fieldHint">Choose where pipeline outputs are saved for <strong>{projectId}</strong>. Git mode pushes to your repo. Cloud mode saves to GCS.</p>
                    {gitConfig?.git_url ? (
                      <div className="gitActiveBox">
                        <div className="gitActiveInfo">
                          <GitBranch size={16} />
                          <div>
                            <strong>Git Mode Active</strong>
                            <span className="gitUrlDisplay">{gitConfig.git_url}</span>
                            {userGitTokenSet
                              ? <span className="gitTokenBadge"><Key size={11} /> Token ready</span>
                              : <span className="gitTokenBadge" style={{ background: '#fef3c7', color: '#b45309' }}><Key size={11} /> No token</span>
                            }
                          </div>
                        </div>
                        <button className="dangerBtn" onClick={removeGitConfig}><Trash2 size={14} /> Remove Git</button>
                      </div>
                    ) : (
                      <div className="gitSetupForm">
                        <div className="gitSetupInfo"><Cloud size={16} /><span>Currently using <strong>Cloud Storage (GCS)</strong></span></div>
                        <div className="fieldRow">
                          <label>Git Repository URL</label>
                          <input value={gitUrl} onChange={e => setGitUrl(e.target.value)} placeholder="https://github.com/you/repo.git" />
                        </div>
                        {!userGitTokenSet && (
                          <p className="fieldHint" style={{ color: '#f59e0b' }}>⚠ Save your GitHub Token above first.</p>
                        )}
                        <button className="primaryBtn" onClick={saveGitConfig} disabled={!gitUrl.trim() || loading}>
                          <GitBranch size={14} /> Enable Git Mode
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Team Edit Card */}
                  <div className="card editCard">
                    <div className="cardHeader"><Settings size={18} /><h4>Team — {formatTeamName(selectedTeam)}</h4></div>
                    <div className="fieldRow">
                      <label>Team</label>
                      <select value={selectedTeam} onChange={e => chooseTeam(e.target.value)}>
                        {Object.keys(governance.teams || {}).map(t => <option key={t} value={t}>{formatTeamName(t)}</option>)}
                      </select>
                    </div>
                    <div className="fieldRow"><label>AI Model</label>{renderModelSelect()}</div>
                    <div className="fieldRow">
                      <label>Budget (USD)</label>
                      <div className="inputWithIcon"><span className="currencyIcon">$</span><input type="number" step="0.01" value={teamBudget} onChange={e => setTeamBudget(e.target.value)} /></div>
                    </div>
                    <div className="fieldRow">
                      <label className="labelWithIcon"><Key size={14} /> API Key <span className="labelOptional">(for non-Factory models)</span></label>
                      <div className="apiKeyInputRow">
                        <div className="inputWithIcon apiKeyInput">
                          <input type={showApiKey ? 'text' : 'password'} value={teamApiKey} onChange={e => setTeamApiKey(e.target.value)}
                            placeholder={governance.teams[selectedTeam]?.has_custom_key ? 'Key set — enter new to replace' : 'Paste API key'} />
                          <button type="button" className="iconBtn" onClick={() => setShowApiKey(!showApiKey)}>{showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                        </div>
                      </div>
                      {governance.teams[selectedTeam]?.has_custom_key && <div className="keyStatus active"><Shield size={13} /><span>Custom key: {governance.teams[selectedTeam].api_key}</span></div>}
                      {!governance.teams[selectedTeam]?.has_custom_key && <div className="keyStatus default"><Info size={13} /><span>Using system default key</span></div>}
                    </div>
                    <button className="primaryBtn" onClick={saveTeamSettings} disabled={loading}>{loading ? <Loader2 size={16} className="spin" /> : 'Save Changes'}</button>
                  </div>

                  {/* Overview Card */}
                  <div className="card overviewCard">
                    <div className="cardHeader"><Shield size={18} /><h4>Governance Overview</h4></div>
                    <div className="govStats">
                      <div className="stat"><span className="statLabel">Status</span><span className={`statBadge ${governance.enabled ? 'enabled' : 'disabled'}`}>{governance.enabled ? 'Enabled' : 'Disabled'}</span></div>
                      <div className="stat"><span className="statLabel">Models</span><span className="statValue">{governance.available_models?.length || 0}</span></div>
                    </div>
                    <h5 className="tableTitle">Team Allocations</h5>
                    <div className="tableContainer">
                      <table className="govTable">
                        <thead><tr><th>Team</th><th>Model</th><th>Budget</th><th>Spent</th><th>Key</th></tr></thead>
                        <tbody>
                          {Object.entries(governance.teams || {}).map(([tk, d]) => {
                            const mi = getModelInfo(d.model)
                            return (
                              <tr key={tk} className={tk === selectedTeam ? 'rowSelected' : ''} onClick={() => chooseTeam(tk)}>
                                <td className="teamCell">{formatTeamName(tk)}</td>
                                <td><span className="modelBadge" style={{ borderColor: mi.color }}>{formatModelName(d.model)}</span></td>
                                <td>${d.limit_usd.toFixed(2)}</td>
                                <td>${d.spent_usd.toFixed(2)}</td>
                                <td>{d.has_custom_key ? <span className="keyBadge custom"><Key size={12} /> Custom</span> : <span className="keyBadge default">Default</span>}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        {['chat','pipeline','group'].includes(activeTab) && (
          <div className="inputArea">
            {activeTab === 'pipeline' && taskStatus?.result?.code_files && Object.keys(taskStatus.result.code_files).length > 0 && (
              <div className="followupBanner">
                <RefreshCw size={12} />
                <span>Follow-up mode — your next request will extend the existing code</span>
              </div>
            )}
            <form onSubmit={handleSubmit} className="inputForm">
              <input type="text" value={inputMessage} onChange={e => setInputMessage(e.target.value)}
                placeholder={
                  activeTab === 'chat' ? 'Ask about the project...' :
                  activeTab === 'pipeline'
                    ? (taskStatus?.result?.code_files && Object.keys(taskStatus.result.code_files).length > 0
                        ? 'Describe a change or fix to apply...'
                        : 'Describe a requirement to build...')
                    : 'Enter a topic...'
                }
                disabled={loading} />
              <button type="submit" disabled={!inputMessage.trim() || loading} className="sendBtn">
                {loading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
              </button>
            </form>
          </div>
        )}
      </section>
    </main>
  )
}
