import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import {
  Send, Settings, Database, MessageSquare, Users, Play, Loader2,
  CheckCircle2, XCircle, Clock, Bot, User, Key, Eye, EyeOff, Info,
  Shield, Activity, ChevronDown, ChevronRight, Zap, Search, LogOut, Plus, Trash2,
  GitBranch, FolderOpen, Cloud, ExternalLink, Monitor, Code2,
  Folder, FileCode, Copy, RefreshCw, GitMerge, Bell, AlertTriangle, CheckSquare,
  BookOpen, ArrowDownToLine, MessageCircle, FileText, List, Hash, Radio, Download,
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

// Alias map mirrors the backend TEAM_ALIASES — used by @mention detection in group chat
const TEAM_ALIASES = {
  solarch: 'solution_arch', sol_arch: 'solution_arch', solution_arch: 'solution_arch',
  arch: 'solution_arch', architect: 'solution_arch',
  backend: 'backend_eng', backend_eng: 'backend_eng', be: 'backend_eng',
  frontend: 'frontend_eng', frontend_eng: 'frontend_eng', fe: 'frontend_eng', ui: 'frontend_eng',
  pm: 'product_mgmt', product: 'product_mgmt', product_mgmt: 'product_mgmt',
  ba: 'biz_analysis', biz: 'biz_analysis', biz_analysis: 'biz_analysis',
  api: 'api_design', api_design: 'api_design',
  ux: 'ux_ui', ux_ui: 'ux_ui', design: 'ux_ui',
  db: 'database_eng', database: 'database_eng', database_eng: 'database_eng',
  data: 'data_eng', data_eng: 'data_eng',
  ml: 'ml_eng', ml_eng: 'ml_eng',
  security: 'security_eng', security_eng: 'security_eng', sec: 'security_eng',
  compliance: 'compliance',
  devops: 'devops', ops: 'devops',
  sre: 'sre_ops', sre_ops: 'sre_ops',
  qa: 'qa_eng', qa_eng: 'qa_eng', test: 'qa_eng',
  docs: 'docs_team', docs_team: 'docs_team',
  feature: 'feature_eng', features: 'feature_eng', feature_eng: 'feature_eng',
}

/** Return canonical team names extracted from @mention tokens in text. */
function parseMentions(text) {
  const found = [], seen = new Set()
  const matches = text.match(/@([A-Za-z0-9_]+)/g) || []
  for (const m of matches) {
    const key = m.slice(1).toLowerCase()
    const canonical = TEAM_ALIASES[key]
    if (canonical && !seen.has(canonical)) { found.push(canonical); seen.add(canonical) }
  }
  return found
}

const NAV_DESCRIPTIONS = {
  chat: 'Chat with your AI coworker about the project.',
  pipeline: 'Describe a requirement — AI picks the right teams and runs the pipeline.',
  group: 'Multi-team discussion on a topic.',
  comms: 'Live feed of agent-to-agent communications: handoffs, context sharing, and clarifications.',
  preview: 'Live code preview of the last pipeline run — like Google AI Studio.',
  memory: 'Interactive knowledge graph of all artifacts.',
  settings: 'Configure AI models, budgets, API keys, and Git.',
  merge: 'View branches, review AI-generated code, and merge to main or dev.',
  selfheal: 'Autonomous watchdog: detects errors, runs fixes, collects agent sign-offs.',
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
function PreviewPanel({ taskStatus, onRunPipeline, onLoadGit, repoFiles, repoLoading, repoBranch, onChangeBranch }) {
  const [viewMode, setViewMode] = useState('preview')
  const [selectedFile, setSelectedFile] = useState(null)

  const result = taskStatus?.result || {}
  const codeFiles = result.code_files || {}         // {team: {filename: content}}
  // Prefer repo files (pulled from git) over pipeline-cached files
  const unifiedCode = repoFiles || result.unified_code || null
  const fileAttribution = repoFiles ? {} : (result.file_attribution || {})
  const mdArtifacts = result.artifacts || {}        // {team: metadata-text}

  // Build flat file list — prefer unified tree, fall back to per-team
  const allFiles = []
  if (unifiedCode && Object.keys(unifiedCode).length > 0) {
    Object.entries(unifiedCode).forEach(([fname, content]) => {
      allFiles.push({ team: fileAttribution[fname] || 'project', fname, content, key: fname })
    })
  } else {
    Object.entries(codeFiles).forEach(([team, files]) => {
      Object.entries(files || {}).forEach(([fname, content]) => {
        allFiles.push({ team, fname, content, key: `${team}/${fname}` })
      })
    })
  }

  // Build folder tree for display — unified project structure
  const buildTree = () => {
    const root = { dirs: {}, files: [] }
    allFiles.forEach(f => {
      const parts = f.fname.split('/')
      if (parts.length === 1) {
        root.files.push(f)
      } else {
        const dirPath = parts.slice(0, -1).join('/')
        if (!root.dirs[dirPath]) root.dirs[dirPath] = []
        root.dirs[dirPath].push(f)
      }
    })
    return root
  }
  const fileTree = buildTree()

  const [collapsedFolders, setCollapsedFolders] = useState(new Set())
  const toggleFolder = id => setCollapsedFolders(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })
  const fileIconColor = name => {
    const ext = (name.split('.').pop() || '').toLowerCase()
    if (['jsx','tsx'].includes(ext)) return '#f0a048'
    if (['js','ts'].includes(ext)) return '#cbcb41'
    if (['py'].includes(ext)) return '#4584b6'
    if (['css','scss','less'].includes(ext)) return '#519aba'
    if (['json'].includes(ext)) return '#cbcb41'
    if (['md','mdx'].includes(ext)) return '#519aba'
    if (['html'].includes(ext)) return '#e44d26'
    if (['yaml','yml'].includes(ext)) return '#cb171e'
    if (['sh','bash','zsh'].includes(ext)) return '#89e051'
    if (name.toLowerCase() === 'dockerfile') return '#0db7ed'
    return '#9dacbb'
  }

  // Pick first file by default; auto-switch to code tab if no renderable frontend
  useEffect(() => {
    if (allFiles.length > 0) {
      if (!selectedFile) setSelectedFile(allFiles[0].key)
      if (!hasFrontend && viewMode === 'preview') setViewMode('code')
    }
  }, [taskStatus]) // eslint-disable-line

  const currentFile = allFiles.find(f => f.key === selectedFile)

  // ── Build runnable preview document from any jsx/js files ──
  const buildRunnable = () => {
    // Collect all jsx/tsx/js files from unified or per-team
    const jsxMap = {}
    allFiles.forEach(f => {
      if (f.fname.endsWith('.jsx') || f.fname.endsWith('.tsx') || f.fname.endsWith('.js')) {
        jsxMap[f.fname] = f.content
      }
    })
    // Find best entry file: prefer App.jsx > index.jsx > first file with a component
    const entryOrder = ['src/App.jsx','App.jsx','src/app.jsx','src/index.jsx','index.jsx','src/main.jsx','main.jsx']
    let appJsx = ''
    for (const name of entryOrder) { if (jsxMap[name]) { appJsx = jsxMap[name]; break } }
    if (!appJsx) {
      // pick the largest jsx file (most likely the main component)
      const sorted = Object.entries(jsxMap).sort((a,b) => b[1].length - a[1].length)
      appJsx = sorted[0]?.[1] || ''
    }
    const allJsx = Object.values(jsxMap).filter(c => c && (c.includes('function ') || c.includes('=>') || c.includes('const '))).join('\n\n')
    const jsxCode = appJsx || allJsx

    // Extract CSS if any
    const cssMatch = jsxCode.match(/<style[^>]*>([\s\S]*?)<\/style>/i)
    const inlineStyle = cssMatch ? cssMatch[1] : ''
    const codeWithoutStyle = jsxCode.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')

    // Strip ES module syntax and markdown fences before handing to Babel
    const cleanCode = codeWithoutStyle
      .replace(/^\s*```[^\n]*\n?/gm, '')                   // strip all markdown fences (incl. indented)
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
      /* Auto-discover any exported React component — works regardless of what LLM named it */
      const __names = ['App','Calculator','TodoApp','Counter','Timer','Weather','Notes',
        'Expenses','Budget','Dashboard','Main','Page','Application','Component',
        'Form','List','Quiz','Game','Chat','Search','Table','Chart','Profile','Settings'];
      const __comp = __names.reduce((found, n) => found || (typeof window[n]==='function' ? window[n] : null), null);

      const __root = ReactDOM.createRoot(document.getElementById('root'));
      if (__comp) {
        __root.render(React.createElement(__comp));
      } else {
        __root.render(
          React.createElement('div', { style: { padding: '32px', textAlign: 'center', color: '#64748b' } },
            React.createElement('h2', null, '\u26a0\ufe0f No Component Found'),
            React.createElement('p', null, 'Expected a root component — switch to the Code tab to view the source.'),
            React.createElement('p', { style: { fontSize: '12px', color: '#94a3b8' } }, 'Tip: Run the pipeline again with a frontend requirement.')
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
  // hasFrontend = any .jsx/.tsx file present — LLM may name it anything (Calculator.jsx, App.jsx, etc.)
  const hasFrontend = allFiles.some(f => f.fname.endsWith('.jsx') || f.fname.endsWith('.tsx'))
  const hasPython = !hasFrontend && allFiles.some(f => f.fname.endsWith('.py'))
  const hasTS = !hasFrontend && !hasPython && allFiles.some(f => f.fname.endsWith('.ts'))
  const hasGo = !hasFrontend && !hasPython && allFiles.some(f => f.fname.endsWith('.go'))
  const hasRust = !hasFrontend && !hasPython && allFiles.some(f => f.fname.endsWith('.rs'))
  const hasJava = !hasFrontend && !hasPython && allFiles.some(f => f.fname.endsWith('.java'))

  const status = taskStatus?.status

  return (
    <div className="previewPanel">
      {/* Toolbar */}
      <div className="previewToolbar">
        <div className="previewLeft">
          <span className="previewTitle"><Monitor size={15} /> Live Preview</span>
          <span className="previewMeta">
            {allFiles.length > 0 && <>{allFiles.length} file{allFiles.length !== 1 ? 's' : ''}</>}
            {repoFiles && <span className="previewTag" style={{ background: '#1e3a5f' }}>📦 From Git:{repoBranch}</span>}
            {hasFrontend && <span className="previewTag">⚛ React App</span>}
            {hasPython && <span className="previewTag" style={{ background: '#1a3a5c', color: '#79b8ff' }}>🐍 Python</span>}
            {hasTS && <span className="previewTag" style={{ background: '#1a2a3a', color: '#4fc3f7' }}>🔷 TypeScript</span>}
            {hasGo && <span className="previewTag" style={{ background: '#002d3a', color: '#00acd7' }}>🐹 Go</span>}
            {hasRust && <span className="previewTag" style={{ background: '#2a1a0a', color: '#f7a033' }}>🦀 Rust</span>}
            {hasJava && <span className="previewTag" style={{ background: '#1a2a1a', color: '#f89820' }}>☕ Java</span>}
            {!hasFrontend && !hasPython && !hasTS && !hasGo && !hasRust && !hasJava && allFiles.length > 0 && (
              <span className="previewTag" style={{ background: '#1a1a2a', color: '#aaa' }}>📄 Code</span>
            )}
          </span>
        </div>
        <div className="previewViewToggle">
          <button className={`previewToggleBtn ${viewMode === 'preview' ? 'active' : ''}`}
            onClick={() => setViewMode('preview')} disabled={!hasFrontend}
            title={!hasFrontend ? 'No React/JSX files detected — use Code tab' : 'Preview React app'}>
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
          {onLoadGit && (
            <>
              <input
                className="previewBranchInput"
                value={repoBranch || 'main'}
                onChange={e => onChangeBranch && onChangeBranch(e.target.value)}
                title="Branch"
                placeholder="main"
                style={{ width: 72, fontSize: 11, padding: '2px 6px', marginLeft: 4 }}
              />
              <button className="previewToggleBtn" onClick={() => { setViewMode('code'); onLoadGit() }} disabled={repoLoading}
                title="Pull all files from Git repo">
                {repoLoading ? <Loader2 size={13} className="spin" /> : <GitBranch size={13} />} Git
              </button>
            </>
          )}
        </div>
      </div>

      {/* No run yet */}
      {!status && (
        <div className="previewEmpty">
          <Monitor size={48} className="previewEmptyIcon" />
          <h3>No run yet</h3>
          <p>Run a pipeline to see code here, or load files directly from your Git repository.</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
            {onRunPipeline && (
              <button className="previewGoBtn" onClick={onRunPipeline}>
                <Play size={14} /> Run Pipeline
              </button>
            )}
            <button className="previewGoBtn" style={{ background: '#1e293b' }}
              onClick={() => { setViewMode('code'); onLoadGit && onLoadGit() }}
              disabled={!onLoadGit}>
              <GitBranch size={14} /> Load from Git
            </button>
          </div>
          <span className="previewHint">Generated React code renders in a live sandboxed iframe.</span>
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
            key={JSON.stringify(unifiedCode || codeFiles.frontend_eng || {}).slice(0, 40)}
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

      {/* Code browser — VS Code-style explorer */}
      {status === 'completed' && viewMode === 'code' && (
        <div className="previewCodeLayout">
          {/* Explorer sidebar */}
          <div className="vsExplorer">
            <div className="vsExplorerTitle"><FolderOpen size={12} style={{ marginRight: 5 }} />Explorer</div>
            <div className="vsExplorerSection">
              {allFiles.length === 0
                ? <div className="vsEmpty">No code files</div>
                : <>
                    {/* Root-level files */}
                    {fileTree.files.map(f => {
                      const name = f.fname.split('/').pop()
                      return (
                        <div key={f.key}
                          className={`vsRow vsDepth0 vsFile ${selectedFile === f.key ? 'vsActive' : ''}`}
                          onClick={() => setSelectedFile(f.key)}>
                          <span className="vsChevron" />
                          <FileCode size={13} className="vsIcon" style={{ color: fileIconColor(name), marginRight: 5, flexShrink: 0 }} />
                          <span className="vsLabel">{name}</span>
                        </div>
                      )
                    })}
                    {/* Directory folders */}
                    {Object.entries(fileTree.dirs).sort(([a],[b]) => a.localeCompare(b)).map(([dirPath, dirFiles]) => {
                      const dirId = `dir:${dirPath}`
                      const dirOpen = !collapsedFolders.has(dirId)
                      return (
                        <div key={dirPath}>
                          <div className="vsRow vsDepth0 vsFolder" onClick={() => toggleFolder(dirId)}>
                            <span className="vsChevron">{dirOpen ? <ChevronDown size={12}/> : <ChevronRight size={12}/>}</span>
                            <Folder size={14} className="vsIcon" style={{ color: dirOpen ? '#dcb67a' : '#c09050', marginRight: 5, flexShrink: 0 }} />
                            <span className="vsLabel vsLabelFolder">{dirPath}</span>
                          </div>
                          {dirOpen && dirFiles.map(f => {
                            const name = f.fname.split('/').pop()
                            return (
                              <div key={f.key}
                                className={`vsRow vsDepth1 vsFile ${selectedFile === f.key ? 'vsActive' : ''}`}
                                onClick={() => setSelectedFile(f.key)}>
                                <span className="vsChevron" />
                                <FileCode size={13} className="vsIcon" style={{ color: fileIconColor(name), marginRight: 5, flexShrink: 0 }} />
                                <span className="vsLabel">{name}</span>
                                {fileAttribution[f.fname] && (
                                  <span className="vsTeamBadge">{fileAttribution[f.fname].replace(/_/g, ' ')}</span>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      )
                    })}
                  </>
              }
            </div>
          </div>
          {/* Code pane */}
          <div className="previewCodePane">
            {currentFile ? (
              <>
                <div className="previewCodeHeader">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <FileCode size={13} style={{ color: fileIconColor(currentFile.key.split('/').pop()), flexShrink: 0 }} />
                    <span className="previewCodePath" title={currentFile.key}>{currentFile.key}</span>
                  </div>
                  <button className="previewCopyBtn" title="Copy" onClick={() => navigator.clipboard?.writeText(currentFile.content)}>
                    <Copy size={12} />
                  </button>
                </div>
                <pre className="previewCode">{currentFile.content}</pre>
              </>
            ) : (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#585b70', gap: 8 }}>
                <FolderOpen size={32} style={{ color: '#3a3a4e' }} />
                <span style={{ fontSize: 13 }}>Select a file</span>
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
    catch (e) {
      if (e?.code !== 'auth/popup-closed-by-user') setError(e.message || 'Sign-in failed')
    }
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
  const [groupMaxTurns, setGroupMaxTurns] = useState(1)
  const [trackedTaskId, setTrackedTaskId] = useState('')
  const [taskStatus, setTaskStatus] = useState(null)

  /* Git config for this project */
  const [gitConfig, setGitConfig] = useState(null)
  const [gitUrl, setGitUrl] = useState('')
  /* User-level GitHub PAT — stored once, used for all projects */
  const [userGitTokenSet, setUserGitTokenSet] = useState(false)
  const [gitPatInput, setGitPatInput] = useState('')
  const [showPat, setShowPat] = useState(false)

  /* Merge Team state */
  const [branches, setBranches] = useState([])
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [branchesError, setBranchesError] = useState('')
  const [mergeInProgress, setMergeInProgress] = useState('')  // branch name being merged
  const [mergeResults, setMergeResults] = useState({})  // { branchName: result }
  const [mergeTarget, setMergeTarget] = useState('main')
  const [mergingAll, setMergingAll] = useState(false)
  const [mergeAllResult, setMergeAllResult] = useState(null)

  /* Git repo files (for Live Preview code browser) */
  const [repoFiles, setRepoFiles] = useState(null)  // {filename: content} from repo
  const [repoLoading, setRepoLoading] = useState(false)
  const [repoBranch, setRepoBranch] = useState('main')

  /* Self Heal state */
  const [healStatus, setHealStatus] = useState(null)
  const [healLoading, setHealLoading] = useState(false)

  /* Notifications (from self-heal) */
  const [notifications, setNotifications] = useState([])

  /* Repo learning */
  const [repoLearning, setRepoLearning] = useState(false)
  const [repoLearned, setRepoLearned] = useState(null)

  /* Memory bank detail */
  const [bankDetail, setBankDetail] = useState(null)
  const [bankLoading, setBankLoading] = useState(false)

  /* Memory node decisions */
  const [nodeDecisions, setNodeDecisions] = useState(null)
  const [decisionsLoading, setDecisionsLoading] = useState(false)
  const [memoryDetailTab, setMemoryDetailTab] = useState('memory') // 'memory' | 'decisions'

  /* Agent Comms state */
  const [commsEvents, setCommsEvents] = useState([])
  const [commsOffset, setCommsOffset] = useState(0)
  const commsEndRef = useRef(null)
  useEffect(() => { commsEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [commsEvents])

  /* Clone Repo state */
  const [cloneUrl, setCloneUrl] = useState('')
  const [cloneLoading, setCloneLoading] = useState(false)
  const [cloneResult, setCloneResult] = useState(null)

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
          // Spread the full run so top-level fields (activities, current_team, etc.)
          // are accessible directly on taskStatus — same shape as live-poll response.
          setTaskStatus({ ...run, status: run.status || 'completed', result: run.result || run })
          // Don't re-poll a restored task — it's already complete and the service
          // may have restarted (in-memory task_runs wiped). Polling would 404 forever.
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
    { key: 'comms', label: 'Agent Comms', icon: Radio },
    { key: 'group', label: 'Group Chat', icon: Users },
    { key: 'merge', label: 'Merge Team', icon: GitMerge },
    { key: 'selfheal', label: 'Self Heal', icon: Activity },
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
    setCommsEvents([])  // clear previous comms when starting a new run
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
    let offset = 0
    const timer = setInterval(async () => {
      if (cancelled) return
      try {
        const data = await api(`/api/tasks/${trackedTaskId}`)
        setTaskStatus(data)
        // Poll comms log incrementally (best-effort)
        try {
          const comms = await api(`/api/tasks/${trackedTaskId}/comms?since=${offset}`)
          if (comms.events && comms.events.length > 0) {
            setCommsEvents(prev => [...prev, ...comms.events])
            offset += comms.events.length
          }
        } catch (commsErr) {
          console.debug('Comms polling error:', commsErr)
        }
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
      } catch (err) {
        // Stop polling if task no longer exists (service restart wiped in-memory store)
        if (err.message && (err.message.includes('404') || err.message.includes('task not found'))) {
          clearInterval(timer); setTrackedTaskId('')
        }
      }
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

  /* ─── Merge Team ─── */
  async function loadBranches() {
    setBranchesLoading(true); setBranchesError('')
    try {
      const data = await api(`/api/projects/${projectId}/git/branches`)
      if (data.error) { setBranchesError(data.error); setBranches([]) }
      else setBranches(data.branches || [])
    } catch (e) { setBranchesError(e?.message || 'Failed to load branches') }
    finally { setBranchesLoading(false) }
  }

  async function loadRepoFiles(branch) {
    setRepoLoading(true)
    try {
      const data = await api(`/api/projects/${projectId}/git/files?branch=${branch || repoBranch}`)
      if (data.error) { setError(data.error) }
      else { setRepoFiles(data.files || {}); setRepoBranch(data.branch || branch || repoBranch) }
    } catch (e) { setError(e?.message || 'Failed to load repo files') }
    finally { setRepoLoading(false) }
  }

  async function mergeAllBranches() {
    setMergingAll(true); setMergeAllResult(null)
    try {
      const result = await api(`/api/projects/${projectId}/git/merge-all?target=${mergeTarget}`, { method: 'POST' })
      setMergeAllResult(result)
      // Refresh branch list and clear individual merge results
      setMergeResults({})
      await loadBranches()
    } catch (e) { setMergeAllResult({ failed: [{ branch: '*', error: e?.message }] }) }
    finally { setMergingAll(false) }
  }

  async function doMerge(sourceBranch, targetBranch) {
    setMergeInProgress(sourceBranch)
    try {
      const result = await api(`/api/projects/${projectId}/git/merge`, {
        method: 'POST',
        body: JSON.stringify({ source_branch: sourceBranch, target_branch: targetBranch }),
      })
      setMergeResults(prev => ({ ...prev, [sourceBranch]: result }))
      if (result.status === 'merged' || result.status === 'already_merged') loadBranches()
    } catch (e) {
      setMergeResults(prev => ({ ...prev, [sourceBranch]: { status: 'failed', error: e?.message } }))
    } finally { setMergeInProgress('') }
  }

  /* ─── Self Heal ─── */
  async function loadHealStatus() {
    try {
      const data = await api(`/api/projects/${projectId}/selfheal/status`)
      setHealStatus(data)
      // Merge new backend notifications into local list
      if (data.notifications?.length) {
        setNotifications(prev => {
          const existing = new Set(prev.map(n => n.msg))
          const fresh = data.notifications
            .filter(msg => !existing.has(msg))
            .map(msg => ({ id: Date.now() + Math.random(), msg, ts: new Date().toISOString() }))
          return [...prev, ...fresh]
        })
      }
    } catch {}
  }

  async function startWatcher() {
    setHealLoading(true)
    try { await api(`/api/projects/${projectId}/selfheal/start`, { method: 'POST' }) }
    finally { setHealLoading(false); loadHealStatus() }
  }

  async function stopWatcher() {
    setHealLoading(true)
    try { await api(`/api/projects/${projectId}/selfheal/stop`, { method: 'POST' }) }
    finally { setHealLoading(false); loadHealStatus() }
  }

  async function triggerHeal() {
    setHealLoading(true)
    try { await api(`/api/projects/${projectId}/selfheal/trigger`, { method: 'POST' }) }
    finally { setHealLoading(false); loadHealStatus() }
  }

  // Poll heal status every 15 s when on the selfheal tab
  useEffect(() => {
    if (activeTab !== 'selfheal') return
    loadHealStatus()
    const t = setInterval(loadHealStatus, 15000)
    return () => clearInterval(t)
  }, [activeTab, projectId])

  /* ─── Learn Repo ─── */
  async function learnRepo() {
    setRepoLearning(true)
    try {
      const data = await api(`/api/projects/${projectId}/git/learn`, {
        method: 'POST', body: JSON.stringify({ branch: 'main' }),
      })
      setRepoLearned(data)
    } catch (e) { setError(e.message) }
    finally { setRepoLearning(false) }
  }

  /* ─── Clone External Repo ─── */
  async function cloneExternalRepo() {
    if (!cloneUrl.trim()) return
    setCloneLoading(true); setCloneResult(null)
    try {
      const data = await api(`/api/projects/${projectId}/git/clone`, {
        method: 'POST', body: JSON.stringify({ clone_url: cloneUrl.trim(), branch: 'main' }),
      })
      setCloneResult(data)
    } catch (e) { setError(e.message) }
    finally { setCloneLoading(false) }
  }

  /* ─── Memory Bank Detail ─── */
  async function loadBankDetail(bankId) {
    setBankLoading(true)
    try {
      const data = await api(`/api/projects/${projectId}/memory-map/${bankId}`)
      setBankDetail(data)
    } catch (e) { setError(e.message) }
    finally { setBankLoading(false) }
  }

  /* ─── Team Decision Log ─── */
  async function loadNodeDecisions(team) {
    setDecisionsLoading(true)
    try {
      const data = await api(`/api/projects/${projectId}/decisions?team=${encodeURIComponent(team)}`)
      setNodeDecisions(data?.decisions || [])
    } catch (e) {
      setNodeDecisions([])
    } finally {
      setDecisionsLoading(false)
    }
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
      method: 'POST', body: JSON.stringify({ topic, participants: groupParticipants, max_turns: groupMaxTurns }),
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
          {/* Group chat discussion cards */}
          {msg.result?.discussion && (
            <div className="groupDiscussion">
              {/* Agent turns — grouped by round if multi-turn */}
              {(() => {
                const turns = msg.result.discussion
                const isMultiRound = turns.some(d => d.round > 1)
                let lastRound = 0
                return turns.map((d, i) => {
                  const roundHeader = isMultiRound && d.round !== lastRound
                    ? (lastRound = d.round, <div key={`r${d.round}`} className="groupRoundLabel">Round {d.round}</div>)
                    : null
                  const wasTagged = msg.result.tagged_teams?.includes(d.team)
                  return (
                    <React.Fragment key={i}>
                      {roundHeader}
                      <div className={`groupDiscussionCard ${wasTagged ? 'groupCardTagged' : ''}`}>
                        <div className="groupDiscussionTeam">
                          <Users size={13} />
                          <strong>{formatTeamName(d.team)}</strong>
                          {wasTagged && <span className="groupTaggedBadge">@ mentioned</span>}
                          {d.source && d.source !== 'fallback' && (
                            <span className="groupSourceBadge">{d.source.split(':')[0]}</span>
                          )}
                        </div>
                        <div className="groupDiscussionText">{d.message || d.summary}</div>
                      </div>
                    </React.Fragment>
                  )
                })
              })()}

              {/* Consensus block */}
              {msg.result.consensus && (
                <div className="groupConsensusCard">
                  <div className="groupConsensusTitle"><CheckCircle2 size={13} /> Consensus</div>
                  <div className="groupConsensusText">{msg.result.consensus}</div>
                  {msg.result.action_items?.length > 0 && (
                    <div className="groupActions">
                      {msg.result.action_items.map((a, i) => (
                        <div key={i} className="groupActionItem">
                          <span className="groupActionNum">{i + 1}</span>
                          <span>{a}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Discussion plan */}
              {msg.result.plan && !msg.result.consensus && (
                <div className="groupPlanCard">
                  <div className="groupPlanTitle"><List size={13} /> Discussion Plan</div>
                  {msg.result.plan.map((step, i) => (
                    <div key={i} className="groupPlanStep">
                      <span className="groupPlanNum">{i + 1}</span>
                      <span>{step.replace(/-/g, ' ')}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* Pipeline completion summary */}
          {msg.result && !msg.result.discussion && (
            <div className="pipelineSummary">
              <div className="pipelineSummaryHeader">
                <CheckCircle2 size={15} />
                <strong>Pipeline Complete</strong>
              </div>
              {msg.result.stages && (
                <div className="pipelineSummaryTeams">
                  {msg.result.stages.map((s, i) => (
                    <div key={i} className="pipelineSummaryTeam">
                      <CheckCircle2 size={12} />
                      <span className="pipelineSummaryTeamName">{formatTeamName(s.team)}</span>
                      <span className="pipelineSummaryStatus">{s.status}</span>
                    </div>
                  ))}
                </div>
              )}
              {msg.result.storage && (
                <div className="pipelineSummaryStorage">
                  {msg.result.storage.type === 'git' ? (
                    <><GitBranch size={12} /> Pushed to branch: <code>{msg.result.storage.code_branch || msg.result.storage.branch}</code></>
                  ) : msg.result.storage.type === 'gcs' ? (
                    <><Cloud size={12} /> Stored in Cloud Storage</>
                  ) : (
                    <><Database size={12} /> Stored in memory</>
                  )}
                </div>
              )}
              {msg.result.unified_code && Object.keys(msg.result.unified_code).length > 0 ? (
                <div className="pipelineSummaryFiles">
                  <FileCode size={12} /> {Object.keys(msg.result.unified_code).length} code files in unified project structure
                </div>
              ) : msg.result.code_files && Object.keys(msg.result.code_files).length > 0 && (
                <div className="pipelineSummaryFiles">
                  <FileCode size={12} /> {Object.values(msg.result.code_files).reduce((a, t) => a + Object.keys(t).length, 0)} code files generated
                </div>
              )}
              {msg.result.overall_handoff_ok !== undefined && (
                <div className={`pipelineSummaryHandoff ${msg.result.overall_handoff_ok ? 'ok' : 'warn'}`}>
                  {msg.result.overall_handoff_ok ? <><CheckCircle2 size={12} /> All team handoffs validated</> : <><AlertTriangle size={12} /> Some handoff mismatches detected</>}
                </div>
              )}
              {msg.result.qa_verdict && msg.result.qa_verdict !== 'N/A' && (
                <div className={`qaValidationBanner ${msg.result.qa_verdict === 'PASS' ? 'pass' : 'fail'}`}>
                  {msg.result.qa_verdict === 'PASS'
                    ? <><CheckCircle2 size={14} /> <strong>QA Validation: PASS</strong> — All code checks passed</>
                    : <><AlertTriangle size={14} /> <strong>QA Validation: FAIL</strong> — Issues found</>
                  }
                </div>
              )}
              {msg.result.qa_issues && msg.result.qa_issues.length > 0 && (
                <ul className="qaIssueList">
                  {msg.result.qa_issues.map((issue, i) => <li key={i}>{issue}</li>)}
                </ul>
              )}
            </div>
          )}
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
                onClick={() => {
                  setActiveTab(item.key)
                  if (item.key === 'settings') loadGovernance()
                  if (item.key === 'memory') loadMemoryMap()
                  if (item.key === 'merge') loadBranches()
                  if (item.key === 'selfheal') loadHealStatus()
                }}
                title={NAV_DESCRIPTIONS[item.key]}>
                <Icon size={18} />{item.label}
                {item.key === 'comms' && commsEvents.length > 0 && (
                  <span className="notifBadge" style={{ marginLeft: 'auto', fontSize: 10 }}>{commsEvents.length}</span>
                )}
              </button>
            )
          })}
        </nav>

        {/* Notification bell */}
        {notifications.length > 0 && (
          <div className="notifBell" onClick={() => setActiveTab('selfheal')}>
            <Bell size={14} />
            <span className="notifBadge">{notifications.length}</span>
            <span className="notifBellLabel">Self-Heal Alerts</span>
          </div>
        )}

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
                  {commsEvents.length > 0 && (
                    <button className="previewBannerBtn" onClick={() => setActiveTab('comms')} style={{ background: '#7c3aed' }}>
                      <Radio size={13} /> {commsEvents.length} Comms Events →
                    </button>
                  )}
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
            <PreviewPanel
              taskStatus={taskStatus}
              onRunPipeline={() => setActiveTab('pipeline')}
              onLoadGit={() => loadRepoFiles(repoBranch)}
              repoFiles={repoFiles}
              repoLoading={repoLoading}
              repoBranch={repoBranch}
              onChangeBranch={b => setRepoBranch(b)}
            />
          )}

          {/* Group Chat */}
          {activeTab === 'group' && (
            <div className="chatContainer">
              <div className="groupConfig">
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <label>Select Participants</label>
                    <TeamMultiSelect selected={groupParticipants} onChange={setGroupParticipants} />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 4 }}>Discussion Rounds</label>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {[1, 2, 3].map(n => (
                        <button key={n}
                          className={`previewToggleBtn ${groupMaxTurns === n ? 'active' : ''}`}
                          onClick={() => setGroupMaxTurns(n)}
                          title={`${n} round${n > 1 ? 's' : ''} — each agent speaks ${n} time${n > 1 ? 's' : ''}`}>
                          {n}×
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              <div className="messagesList">{groupHistory.map(renderMessage)}<div ref={messagesEndRef} /></div>
            </div>
          )}

          {/* Agent Comms */}
          {activeTab === 'comms' && (
            <div className="commsContainer">
              {commsEvents.length === 0 ? (
                <div className="commsEmptyState">
                  <Radio size={36} style={{ color: '#cbd5e1', marginBottom: 8 }} />
                  <p style={{ fontWeight: 600, color: 'var(--text2)' }}>No communications yet</p>
                  <span>Run a pipeline to see live agent-to-agent handoffs, context sharing, and clarifications here.</span>
                  {taskStatus?.status === 'running' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--primary)', marginTop: 8 }}>
                      <Loader2 size={14} className="spin" /> Waiting for pipeline events…
                    </div>
                  )}
                </div>
              ) : (
                <div className="commsTimeline">
                  {commsEvents.map((evt, i) => {
                    const typeIcons = {
                      handoff: '→',
                      context: '📋',
                      status: '⚡',
                      clarification: '❓',
                    }
                    return (
                      <div key={i} className={`commsEvent type-${evt.type}`}>
                        <div className="commsEventIcon">{typeIcons[evt.type] || '💬'}</div>
                        <div className="commsEventBody">
                          <div className="commsEventHeader">
                            <span className="commsFrom">{formatTeamName(evt.from_team)}</span>
                            <span className="commsArrow">→</span>
                            <span className="commsTo">{evt.to_team === 'none' ? 'Done' : formatTeamName(evt.to_team)}</span>
                            <span className="commsTypeBadge">{evt.type}</span>
                            <span className="commsTs">{new Date(evt.ts).toLocaleTimeString()}</span>
                          </div>
                          <div className="commsMessage">{evt.message}</div>
                        </div>
                      </div>
                    )
                  })}
                  <div ref={commsEndRef} />
                </div>
              )}
              <div className="commsLiveIndicator">
                {taskStatus?.status === 'running'
                  ? <><div className="commsLiveDot" /> Live — updating as agents communicate</>
                  : <><Clock size={11} /> {commsEvents.length} events recorded</>
                }
                {commsEvents.length > 0 && (
                  <button className="linkBtn" style={{ marginLeft: 'auto' }}
                    onClick={() => { setCommsEvents([]); setCommsOffset(0) }}>
                    Clear
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Memory */}
          {activeTab === 'memory' && (
            <div className="settingsPanel">
              <div className="settingsHeader">
                <div><h3>Knowledge Graph</h3><p>Artifacts and team outputs for <strong>{projectId}</strong>.</p></div>
                <button className="primaryBtn" onClick={loadMemoryMap} disabled={loading}>{loading ? <Loader2 size={16} className="spin" /> : 'Refresh'}</button>
              </div>
              <MemoryGraph data={memoryMap} onNodeClick={node => {
                setSelectedMemoryNode(node)
                setBankDetail(null)
                setNodeDecisions(null)
                setMemoryDetailTab('memory')
                loadBankDetail(node.id)
                loadNodeDecisions(node.team)
              }} />
              {selectedMemoryNode && (
                <div className="nodeDetail">
                  <div className="nodeDetailHeader">
                    <h4>{selectedMemoryNode.displayName || formatTeamName(selectedMemoryNode.team)}</h4>
                    <button className="iconBtn" onClick={() => { setSelectedMemoryNode(null); setBankDetail(null); setNodeDecisions(null) }}><XCircle size={16} /></button>
                  </div>
                  <p className="nodeDetailMeta">Bank: <code>{selectedMemoryNode.id}</code> · Artifacts: <strong>{selectedMemoryNode.items}</strong></p>

                  {/* Tab switcher */}
                  <div className="nodeDetailTabs">
                    <button
                      className={`nodeDetailTab ${memoryDetailTab === 'memory' ? 'active' : ''}`}
                      onClick={() => setMemoryDetailTab('memory')}
                    >
                      <Database size={12} /> Memory Items
                    </button>
                    <button
                      className={`nodeDetailTab ${memoryDetailTab === 'decisions' ? 'active' : ''}`}
                      onClick={() => setMemoryDetailTab('decisions')}
                    >
                      <BookOpen size={12} /> Decisions
                      {nodeDecisions && nodeDecisions.length > 0 && (
                        <span className="nodeDetailTabBadge">{nodeDecisions.length}</span>
                      )}
                    </button>
                  </div>

                  {/* ── Memory tab ── */}
                  {memoryDetailTab === 'memory' && (
                    <>
                      {bankLoading && <div style={{ padding: '12px', textAlign: 'center' }}><Loader2 size={16} className="spin" /></div>}
                      {bankDetail && !bankLoading && (
                        <div className="bankDetailList">
                          {bankDetail.items.map((item, i) => (
                            <div key={i} className={`bankDetailItem bankDetail-${item.type}`}>
                              <div className="bankDetailType">
                                {item.type === 'knowledge' ? <BookOpen size={12} /> : item.type === 'file_index' ? <FileText size={12} /> : item.type === 'artifact' ? <Hash size={12} /> : item.type === 'decision' ? <ArrowDownToLine size={12} /> : <MessageCircle size={12} />}
                                <span>{item.type.replace('_', ' ')}</span>
                                {item.decision_type && <span className={`decisionTypePill decType-${item.decision_type}`}>{item.decision_type.replace('_', ' ')}</span>}
                              </div>
                              <div className="bankDetailContent">{item.content.substring(0, 400)}{item.content.length > 400 ? '...' : ''}</div>
                            </div>
                          ))}
                          {bankDetail.items.length === 0 && <p style={{ color: 'var(--text3)', fontSize: '13px', padding: '8px 0' }}>No items yet for this team.</p>}
                        </div>
                      )}
                    </>
                  )}

                  {/* ── Decisions tab ── */}
                  {memoryDetailTab === 'decisions' && (
                    <div className="decisionsPanel">
                      {decisionsLoading && <div style={{ padding: '12px', textAlign: 'center' }}><Loader2 size={16} className="spin" /></div>}
                      {!decisionsLoading && nodeDecisions && nodeDecisions.length === 0 && (
                        <div className="decisionsEmpty">
                          <BookOpen size={28} style={{ color: '#cbd5e1', marginBottom: 8 }} />
                          <p>No decisions logged yet for <strong>{formatTeamName(selectedMemoryNode.team)}</strong>.</p>
                          <span>Decisions are recorded when a pipeline run completes.</span>
                        </div>
                      )}
                      {!decisionsLoading && nodeDecisions && nodeDecisions.map(d => (
                        <div key={d.id} className="decisionCard">
                          <div className="decisionCardHeader">
                            <span className={`decisionTypeBadge decType-${d.decision_type}`}>
                              {d.decision_type?.replace(/_/g, ' ').toUpperCase() || 'DECISION'}
                            </span>
                            <span className="decisionTs">
                              <Clock size={11} />
                              {new Date(d.ts).toLocaleString()}
                            </span>
                          </div>
                          <div className="decisionTitle">{d.title}</div>
                          {d.rationale && (
                            <div className="decisionRationale">{d.rationale.substring(0, 400)}{d.rationale.length > 400 ? '…' : ''}</div>
                          )}
                          {d.artifact_ref && d.artifact_ref !== `memory://team-${d.team}` && (
                            <div className="decisionRef"><Hash size={11} /> {d.artifact_ref}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
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
                      <>
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
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <button className="secondaryBtn" onClick={learnRepo} disabled={repoLearning} title="Fetch and analyze existing repo code">
                              {repoLearning ? <Loader2 size={14} className="spin" /> : <BookOpen size={14} />}
                              {repoLearning ? 'Learning...' : 'Learn Repo'}
                            </button>
                            <button className="dangerBtn" onClick={removeGitConfig}><Trash2 size={14} /> Remove Git</button>
                          </div>
                        </div>
                        {repoLearned && (
                          <div className="repoLearnedBox">
                            <div className="repoLearnedHeader">
                              <CheckCircle2 size={14} />
                              <strong>Repo analyzed: {repoLearned.files_analyzed} files</strong>
                            </div>
                            <p className="repoLearnedPreview">{repoLearned.notes_preview}</p>
                            <div className="repoLearnedFiles">
                              {(repoLearned.file_tree || []).slice(0, 15).map((f, i) => (
                                <span key={i} className="repoFileTag">{f}</span>
                              ))}
                              {(repoLearned.file_tree || []).length > 15 && <span className="repoFileTag">+{repoLearned.file_tree.length - 15} more</span>}
                            </div>
                          </div>
                        )}
                      </>
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

                  {/* Clone External Repo Card */}
                  <div className="card gitCard cloneRepoBox">
                    <div className="cardHeader"><Download size={18} /><h4>Clone &amp; Build on Existing Repo</h4></div>
                    <p className="fieldHint">
                      Paste any public (or private, if token is set) GitHub repo URL. All pipeline agents will learn its
                      codebase, tech stack, and conventions before generating code so they can build on top of it.
                    </p>
                    <div className="fieldRow">
                      <label>External Repo URL</label>
                      <input
                        value={cloneUrl}
                        onChange={e => setCloneUrl(e.target.value)}
                        placeholder="https://github.com/owner/repo"
                      />
                    </div>
                    <button className="primaryBtn" onClick={cloneExternalRepo} disabled={!cloneUrl.trim() || cloneLoading}>
                      {cloneLoading ? <><Loader2 size={14} className="spin" /> Analyzing…</> : <><Download size={14} /> Clone &amp; Learn</>}
                    </button>
                    {cloneResult && (
                      <div className="cloneRepoResult">
                        <div className="cloneRepoResultHeader">
                          <CheckCircle2 size={14} />
                          <strong>{cloneResult.status === 'cloned' ? `✅ Analyzed ${cloneResult.files_analyzed} files from ${cloneResult.clone_url}` : `Error: ${cloneResult.error}`}</strong>
                        </div>
                        {cloneResult.notes_preview && <p className="repoLearnedPreview">{cloneResult.notes_preview}</p>}
                        {cloneResult.file_tree && (
                          <div className="repoLearnedFiles">
                            {cloneResult.file_tree.slice(0, 15).map((f, i) => <span key={i} className="repoFileTag">{f}</span>)}
                            {cloneResult.file_tree.length > 15 && <span className="repoFileTag">+{cloneResult.file_tree.length - 15} more</span>}
                          </div>
                        )}
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

        {/* Merge Team */}
        {activeTab === 'merge' && (
          <div className="settingsPanel">
            <div className="settingsHeader">
              <div>
                <h3>Merge Team</h3>
                <p>AI-generated branches are auto-merged after each pipeline run. Use <strong>Merge All</strong> to merge any pending branches manually.</p>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select className="mergeTargetSelect" value={mergeTarget} onChange={e => setMergeTarget(e.target.value)}>
                  <option value="main">→ main</option>
                  <option value="dev">→ dev</option>
                  <option value="staging">→ staging</option>
                </select>
                <button className="primaryBtn" style={{ background: '#16a34a' }}
                  onClick={mergeAllBranches} disabled={mergingAll || branchesLoading}>
                  {mergingAll ? <><Loader2 size={14} className="spin" /> Merging All…</> : <><GitMerge size={14} /> Merge All AI Branches</>}
                </button>
                <button className="secondaryBtn" onClick={loadBranches} disabled={branchesLoading}>
                  {branchesLoading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                </button>
              </div>
            </div>

            {/* Auto-merge summary from last pipeline run */}
            {taskStatus?.result?.auto_merge && (() => {
              const am = taskStatus.result.auto_merge
              return (
                <div style={{ margin: '0 0 12px', padding: '10px 14px', background: '#0f2a1a', borderRadius: 8, fontSize: 12, color: '#86efac', border: '1px solid #166534' }}>
                  <strong>⚡ Auto-merged after last pipeline:</strong>&nbsp;
                  {am.merged?.length > 0 && <span style={{ color: '#4ade80' }}>✅ {am.merged.length} merged</span>}
                  {am.skipped?.length > 0 && <span style={{ color: '#94a3b8', marginLeft: 8 }}>⏭ {am.skipped.length} already up-to-date</span>}
                  {am.failed?.length > 0 && <span style={{ color: '#f87171', marginLeft: 8 }}>❌ {am.failed.length} failed</span>}
                </div>
              )
            })()}

            {/* Merge All result */}
            {mergeAllResult && (
              <div style={{ margin: '0 0 12px', padding: '10px 14px', background: '#0f172a', borderRadius: 8, fontSize: 12, border: '1px solid #334155' }}>
                <strong style={{ color: '#e2e8f0' }}>Merge All result:</strong>&nbsp;
                {mergeAllResult.merged?.length > 0 && <span style={{ color: '#4ade80' }}>✅ {mergeAllResult.merged.length} merged ({mergeAllResult.merged.join(', ')})</span>}
                {mergeAllResult.skipped?.length > 0 && <span style={{ color: '#94a3b8', marginLeft: 8 }}>⏭ {mergeAllResult.skipped.length} already up-to-date</span>}
                {mergeAllResult.failed?.length > 0 && <span style={{ color: '#f87171', marginLeft: 8 }}>❌ {mergeAllResult.failed.map(f => f.branch + ': ' + f.error).join('; ')}</span>}
              </div>
            )}

            {branchesError && <div className="healAlert"><AlertTriangle size={14} /> {branchesError}</div>}

            {/* Branch counts */}
            {branches.length > 0 && (() => {
              const ai = branches.filter(b => b.is_ai)
              const normal = branches.filter(b => !b.is_ai && !b.protected)
              return (
                <div style={{ display: 'flex', gap: 10, margin: '0 0 12px', fontSize: 12, color: '#94a3b8' }}>
                  <span>Total: <strong style={{ color: '#e2e8f0' }}>{branches.length}</strong></span>
                  <span>🤖 AI branches: <strong style={{ color: '#60a5fa' }}>{ai.length}</strong></span>
                  <span>Other: <strong style={{ color: '#e2e8f0' }}>{normal.length}</strong></span>
                </div>
              )
            })()}

            {!branchesError && branches.length === 0 && !branchesLoading && (
              <div className="healEmpty">
                <GitMerge size={32} style={{ color: '#cbd5e1', marginBottom: 8 }} />
                <p>No branches found. Configure a Git repository in Settings first, or click Refresh.</p>
              </div>
            )}
            <div className="branchList">
              {branches.map(b => {
                const result = mergeResults[b.name]
                const isMerging = mergeInProgress === b.name
                return (
                  <div key={b.name} className={`branchCard ${b.is_ai ? 'branchCardAI' : ''}`}>
                    <div className="branchCardLeft">
                      <div className="branchName">
                        {b.is_ai && <span className="branchBadgeAI">🤖 AI</span>}
                        {b.protected && <span className="branchBadgeProt">🔒</span>}
                        <code>{b.name}</code>
                      </div>
                      {b.sha && <div className="branchMeta"><span className="branchSha">{b.sha}</span></div>}
                    </div>
                    <div className="branchCardRight">
                      {result && (
                        <span className={`mergePill ${result.status === 'merged' ? 'success' : result.status === 'already_merged' ? 'info' : 'fail'}`}>
                          {result.status === 'merged' ? '✅ Merged' : result.status === 'already_merged' ? '✔ Up to date' : `❌ ${result.error || 'Failed'}`}
                        </span>
                      )}
                      {!b.protected && (
                        <button className="mergeBtn" disabled={!!isMerging || !!mergeInProgress || mergingAll} onClick={() => doMerge(b.name, mergeTarget)}>
                          {isMerging ? <><Loader2 size={12} className="spin" /> Merging…</> : <><GitMerge size={12} /> Merge</>}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Self Heal */}
        {activeTab === 'selfheal' && (
          <div className="settingsPanel">
            <div className="settingsHeader">
              <div>
                <h3>Self-Heal Watchdog</h3>
                <p>Monitors pipeline errors, auto-generates fixes, collects agent sign-offs, and merges to <code>dev</code>.</p>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {healStatus?.running
                  ? <button className="dangerBtn" onClick={stopWatcher} disabled={healLoading}>
                      {healLoading ? <Loader2 size={14} className="spin" /> : '⏹ Stop Watchdog'}
                    </button>
                  : <button className="primaryBtn" onClick={startWatcher} disabled={healLoading}>
                      {healLoading ? <Loader2 size={14} className="spin" /> : '▶ Start Watchdog'}
                    </button>
                }
                <button className="secondaryBtn" onClick={triggerHeal} disabled={healLoading} title="Manually trigger self-heal on current errors">
                  {healLoading ? <Loader2 size={14} className="spin" /> : <><Zap size={14} /> Trigger Now</>}
                </button>
                <button className="secondaryBtn" onClick={loadHealStatus}><RefreshCw size={14} /></button>
              </div>
            </div>

            <div className="healStatusRow">
              <span className={`healPill ${healStatus?.running ? 'running' : 'stopped'}`}>
                <span className="healDot" /> {healStatus?.running ? 'Watchdog Running — polls every 60 s' : 'Watchdog Stopped'}
              </span>
              {notifications.length > 0 && (
                <button className="linkBtn" style={{ color: '#dc2626' }} onClick={() => setNotifications([])}>
                  Clear {notifications.length} notification{notifications.length !== 1 ? 's' : ''}
                </button>
              )}
            </div>

            {notifications.length > 0 && (
              <div className="healSection">
                <div className="healSectionTitle"><Bell size={13} /> Notifications</div>
                {[...notifications].reverse().map(n => (
                  <div key={n.id} className={`healNotif ${n.msg.startsWith('✅') ? 'success' : n.msg.startsWith('⚠️') ? 'warn' : 'fail'}`}>
                    <span>{n.msg}</span>
                    <button className="iconBtn" style={{ marginLeft: 'auto', color: '#94a3b8' }}
                      onClick={() => setNotifications(prev => prev.filter(x => x.id !== n.id))}>
                      <XCircle size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="healSection">
              <div className="healSectionTitle"><AlertTriangle size={13} /> Recent Errors ({(healStatus?.recent_errors || []).length})</div>
              {(healStatus?.recent_errors || []).length === 0
                ? <div className="healEmpty" style={{ padding: '12px 0' }}><CheckSquare size={20} style={{ color: '#22c55e' }} /><span>No errors in buffer</span></div>
                : [...(healStatus?.recent_errors || [])].reverse().map((e, i) => (
                  <div key={i} className="healErrorRow">
                    <span className="healErrLevel">{e.level}</span>
                    <span className="healErrTs">{new Date(e.ts).toLocaleTimeString()}</span>
                    <span className="healErrMsg">{e.msg}</span>
                  </div>
                ))
              }
            </div>

            <div className="healSection">
              <div className="healSectionTitle"><Activity size={13} /> Heal History ({(healStatus?.history || []).length})</div>
              {(healStatus?.history || []).length === 0
                ? <div className="healEmpty" style={{ padding: '12px 0' }}><p>No heal cycles run yet.</p></div>
                : [...(healStatus?.history || [])].reverse().map(h => {
                    const isActive = ['analyzing','fixing','reviewing'].includes(h.status)
                    const n_yes = Object.values(h.signoffs || {}).filter(s => s.approved).length
                    const n_tot = Object.values(h.signoffs || {}).length
                    return (
                      <div key={h.heal_id} className={`healCard ${h.status === 'approved' ? 'healApproved' : h.status === 'rejected' ? 'healRejected' : 'healPending'}`}>
                        <div className="healCardHeader">
                          <span className="healCardId">#{h.heal_id}</span>
                          {h.manual && <span className="healBadge">Manual</span>}
                          <span className={`healStatusBadge ${h.status}`}>
                            {isActive ? <><Loader2 size={11} className="spin" /> {h.status}</> : h.status}
                          </span>
                          <span className="healCardTs">{h.started_at ? new Date(h.started_at).toLocaleTimeString() : ''}</span>
                        </div>
                        {h.analysis?.root_cause && <div className="healRootCause">🔍 {h.analysis.root_cause}</div>}
                        {h.fix_task_id && <div className="healMeta">Fix task: <code>{h.fix_task_id}</code></div>}
                        {n_tot > 0 && (
                          <div className="healSignoffs">
                            <strong>Signoffs ({n_yes}/{n_tot}):</strong>
                            {Object.entries(h.signoffs).map(([team, s]) => (
                              <span key={team} className={`signoffChip ${s.approved ? 'ok' : 'no'}`} title={s.reason}>
                                {s.approved ? '✅' : '❌'} {team.replace(/_/g, '\u200b')}
                              </span>
                            ))}
                          </div>
                        )}
                        {h.merge_result && (
                          <div className="healMeta">
                            Merge:&nbsp;
                            <span className={`mergePill ${h.merge_result.status === 'merged' ? 'success' : h.merge_result.status === 'already_merged' ? 'info' : 'fail'}`}>
                              {h.merge_result.status}
                            </span>
                            {h.merge_result.target && <> → <code>{h.merge_result.target}</code></>}
                          </div>
                        )}
                      </div>
                    )
                  })
              }
            </div>
          </div>
        )}

        {/* Input */}
        {['chat','pipeline','group'].includes(activeTab) && (
          <div className="inputArea">
            {activeTab === 'pipeline' && taskStatus?.result?.code_files && Object.keys(taskStatus.result.code_files).length > 0 && (
              <div className="followupBanner">
                <RefreshCw size={12} />
                <span>Follow-up mode — your next request will extend the existing code</span>
              </div>
            )}
            {activeTab === 'group' && (() => {
              const mentioned = parseMentions(inputMessage)
              return mentioned.length > 0 ? (
                <div className="mentionRoutingBar">
                  <span className="mentionRoutingIcon">@</span>
                  <span>Asking only:</span>
                  {mentioned.map(t => <span key={t} className="mentionChip">{formatTeamName(t)}</span>)}
                  <span className="mentionRoutingNote">other participants ignored</span>
                </div>
              ) : (
                <div className="mentionHintBar">
                  <span>💡 Tag a team to ask them directly — e.g. <code>@solArch</code>, <code>@backend</code>, <code>@qa</code></span>
                </div>
              )
            })()}
            <form onSubmit={handleSubmit} className="inputForm">
              <input type="text" value={inputMessage} onChange={e => setInputMessage(e.target.value)}
                placeholder={
                  activeTab === 'chat' ? 'Ask about the project...' :
                  activeTab === 'pipeline'
                    ? (taskStatus?.result?.code_files && Object.keys(taskStatus.result.code_files).length > 0
                        ? 'Describe a change or fix to apply...'
                        : 'Describe a requirement to build...')
                    : 'Ask all or tag specific teams — e.g. @solArch what did you decide about the DB schema?'
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
