import React, { useEffect, useState, useRef, useCallback } from 'react'
import { AlertCircle, Loader2, Menu, X, Clock, Play, Pause, SkipForward } from 'lucide-react'

// types
interface StepMetrics {
  latency_ms: number
  tokens_total: number
}

interface StepEvaluation {
  status: 'pending' | 'pass' | 'fail' | 'error'
  reasoning?: string
  flags?: string[]
}

interface TraceStep {
  step_id: string
  type: string
  name: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inputs: Record<string, any>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  outputs: Record<string, any>
  metrics: StepMetrics
  evaluation: StepEvaluation
  timestamp: string
}

interface AgentTrace {
  trace_id: string
  session_id?: string
  tags?: Record<string, string>
  timestamp: string
  status: string
  steps: TraceStep[]
}

interface StepDiff {
  left_step?: TraceStep
  right_step?: TraceStep
  changes: string[]
  status: 'added' | 'removed' | 'changed' | 'unchanged'
}

interface MetricsDelta {
  total_tokens: number
  total_latency_ms: number
  steps_count: number
}

interface TraceDiff {
  left: AgentTrace
  right: AgentTrace
  steps: StepDiff[]
  metrics_delta: MetricsDelta
}

interface Session {
  session_id: string
  trace_count: number
  latest_timestamp: string
}

interface DatasetItem {
  item_id: string
  dataset_id: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  inputs: Record<string, any>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  expected_outputs?: Record<string, any>
  created_at: string
}

interface Dataset {
  dataset_id: string
  name: string
  description?: string
  created_at: string
}

const App = () => {
  const [trace, setTrace] = useState<AgentTrace | null>(null)
  const [traces, setTraces] = useState<AgentTrace[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [sidebarView, setSidebarView] = useState<'traces' | 'sessions' | 'datasets'>('traces')
  const [tagFilter, setTagFilter] = useState('')
  const [expandedSessions, setExpandedSessions] = useState<Set<string>>(new Set())
  const [sessionTraces, setSessionTraces] = useState<Record<string, AgentTrace[]>>({})
  const [datasets, setDatasets] = useState<Dataset[]>([])
  
  const [mainView, setMainView] = useState<'trace' | 'compare' | 'dataset'>('trace')
  const [compareTraceIds, setCompareTraceIds] = useState<string[]>([])
  const [compareData, setCompareData] = useState<TraceDiff | null>(null)
  
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const [datasetItems, setDatasetItems] = useState<DatasetItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Replay state
  const [replayMode, setReplayMode] = useState<'idle' | 'playing' | 'paused'>('idle')
  const [visibleStepCount, setVisibleStepCount] = useState<number>(0)
  const [replaySpeed, setReplaySpeed] = useState<number>(1)
  const replayTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const totalSteps = trace?.steps.length || 0

  const startReplay = useCallback(() => {
    if (!trace || trace.steps.length === 0) return
    setReplayMode('playing')
    setVisibleStepCount(0)
  }, [trace])

  const pauseReplay = useCallback(() => {
    setReplayMode('paused')
  }, [])

  const stopReplay = useCallback(() => {
    setReplayMode('idle')
    setVisibleStepCount(0)
    if (replayTimer.current) clearInterval(replayTimer.current)
  }, [])

  // Replay timer tick
  useEffect(() => {
    if (replayTimer.current) clearInterval(replayTimer.current)
    if (replayMode === 'playing' && totalSteps > 0) {
      const interval = 800 / replaySpeed
      replayTimer.current = setInterval(() => {
        setVisibleStepCount(prev => {
          if (prev >= totalSteps) {
            setReplayMode('paused')
            return totalSteps
          }
          return prev + 1
        })
      }, interval)
    }
    return () => { if (replayTimer.current) clearInterval(replayTimer.current) }
  }, [replayMode, replaySpeed, totalSteps])

  const fetchTraces = async () => {
    try {
      const res = await fetch('/api/traces')
      if (res.ok) {
        const data = await res.json()
        setTraces(data.traces)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/sessions')
      if (res.ok) {
        const data = await res.json()
        setSessions(data.sessions)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const toggleSession = async (sessionId: string) => {
    const newExpanded = new Set(expandedSessions)
    if (newExpanded.has(sessionId)) {
      newExpanded.delete(sessionId)
      setExpandedSessions(newExpanded)
    } else {
      newExpanded.add(sessionId)
      setExpandedSessions(newExpanded)
      // fetch traces for this session
      try {
        const res = await fetch(`/api/session/${sessionId}`)
        if (res.ok) {
          const data = await res.json()
          setSessionTraces(prev => ({...prev, [sessionId]: data.traces}))
        }
      } catch (err) {
        console.error(err)
      }
    }
  }

  const fetchDatasets = async () => {
    try {
      const res = await fetch('/api/datasets')
      if (res.ok) {
        const data = await res.json()
        setDatasets(data.datasets)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const fetchDatasetItems = async (datasetId: string) => {
    try {
      const res = await fetch(`/api/datasets/${datasetId}/items`)
      if (res.ok) {
        const data = await res.json()
        setDatasetItems(data.items)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleAddToDataset = async (step: TraceStep) => {
    if (datasets.length === 0) {
      alert("No datasets available. Please create one first in the Datasets tab.")
      return
    }
    const nameStr = datasets.map(d => `${d.name} (${d.dataset_id})`).join('\\n')
    const dsId = window.prompt(`Enter dataset ID to add this step to:\\n\\n${nameStr}`, datasets[0].dataset_id)
    if (!dsId) return
    
    try {
      const res = await fetch(`/api/datasets/${dsId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          inputs: step.inputs,
          expected_outputs: step.outputs
        })
      })
      if (res.ok) {
        alert("Added to dataset!")
      } else {
        alert("Failed to add.")
      }
    } catch {
      alert("Error adding to dataset.")
    }
  }

  const fetchTrace = async () => {
    try {
      const endpoint = selectedTraceId ? `/api/trace/${selectedTraceId}` : '/api/trace/latest'
      const res = await fetch(endpoint)
      if (res.ok) {
        const data = await res.json()
        setTrace(data.trace)
        if (!selectedTraceId && data.trace) {
          setSelectedTraceId(data.trace.trace_id)
        }
        setError(null)
      } else {
        setError("Failed to load trace.")
      }
    } catch {
      setError("Server disconnected.")
    }
  }

  useEffect(() => {
    if (compareTraceIds.length === 2) {
      fetch(`/api/traces/compare?left=${compareTraceIds[0]}&right=${compareTraceIds[1]}`)
        .then(res => res.json())
        .then(data => setCompareData(data))
        .catch(console.error)
    } else {
      setCompareData(null)
    }
  }, [compareTraceIds])

  useEffect(() => {
    fetchTraces()
    fetchSessions()
    fetchTrace()
    fetchDatasets()

    let interval: ReturnType<typeof setInterval>
    if (autoRefresh && replayMode === 'idle') {
      interval = setInterval(() => {
        fetchTraces()
        fetchSessions()
        fetchTrace()
        // Refresh expanded session traces as well
        expandedSessions.forEach(sessionId => {
          fetch(`/api/session/${sessionId}`).then(res => res.json()).then(data => {
            setSessionTraces(prev => ({...prev, [sessionId]: data.traces}))
          }).catch(() => {})
        })
      }, 2000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [selectedTraceId, autoRefresh, replayMode, expandedSessions, fetchTrace])

  if (error && !trace) {
    return <div className="p-8 text-red-500 font-mono">Error: {error}</div>
  }

  const renderTraceStep = (step: TraceStep, animate: boolean = false, highlightChanges: string[] = [], diffStatus: 'added'|'removed'|'changed'|'unchanged'|null = null) => {
    let badge = "bg-gray-800 text-gray-300"
    let title = "PROMPT"

    if (step.type === "tool_execution") {
      badge = "bg-[#1f1f1f] text-gray-400"
      title = "TOOL"
    } else if (step.type === "server_crash") {
      badge = "bg-red-950 text-red-400"
      title = "CRASH"
    } else if (step.type === "llm_call") {
      badge = "bg-gray-200 text-[#0a0a0a]"
      title = "LLM"

      if (step.evaluation.status === 'fail') {
        badge = "bg-red-900 text-red-200"
      } else if (step.evaluation.status === 'pending') {
        badge = "bg-yellow-900 border border-yellow-700 text-yellow-500"
      }
    }

    const hasFlagsDuringReplay = animate && (step.evaluation.flags?.length ?? 0) > 0
    
    let borderClass = step.evaluation.status === 'fail' || step.type === 'server_crash' ? 'border-red-900/50' : 'border-gray-800'
    let bgClass = "bg-[#0f0f0f]"
    
    if (diffStatus === 'added') {
      borderClass = 'border-green-800/60'
      bgClass = 'bg-green-950/20'
    } else if (diffStatus === 'removed') {
      borderClass = 'border-red-900/50 text-gray-500 opacity-60'
      bgClass = 'bg-[#0f0a0a]'
    } else if (diffStatus === 'changed') {
      borderClass = 'border-amber-700/50'
    }

    return (
      <div key={step.step_id} className={`relative ${animate ? 'animate-fadeSlideIn' : ''}`} style={animate ? { animationDuration: '400ms' } : undefined}>
        {/* Timeline Node (Only for non-diff view) */}
        {!diffStatus && (
          <div className={`absolute -left-[41px] top-4 w-5 h-5 bg-[#0f0f0f] border border-gray-700 flex items-center justify-center z-10 ${hasFlagsDuringReplay ? 'border-red-500 animate-pulse' : ''}`}>
             <div className={`w-1.5 h-1.5 ${title === 'CRASH' ? 'bg-red-500' : 'bg-gray-500'}`}></div>
          </div>
        )}

        <div className={`p-4 ${bgClass} border ${borderClass} ${step.type === 'server_crash' && animate ? 'animate-shakeX' : ''}`}>
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-800/50">
            <div className="flex items-center gap-3">
              <span className={`text-[10px] px-1.5 py-0.5 font-bold tracking-widest ${badge}`}>{title}</span>
              <span className={`text-sm ${highlightChanges.includes('name') ? 'text-amber-400' : 'text-gray-200'}`}>{step.name}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-[10px] ${highlightChanges.includes('metrics.latency_ms') ? 'text-amber-500 font-bold' : 'text-gray-600'}`}>{step.metrics.latency_ms}ms</span>
              {(step.type === 'llm_call' || step.type === 'tool_execution') && !diffStatus && (
                <button
                  onClick={() => handleAddToDataset(step)}
                  className="px-1.5 py-0.5 text-[9px] uppercase tracking-widest bg-[#1a1a1a] border border-gray-700 hover:bg-[#2a2a2a] text-gray-400 transition-colors rounded-sm"
                  title="Save to dataset"
                >
                  SAVE
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-px bg-gray-800 border border-gray-800 mb-4">
            <div className={`p-3 ${highlightChanges.includes('inputs') ? 'bg-amber-950/20' : 'bg-[#0f0f0f]'}`}>
              <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Input</div>
              <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all leading-relaxed">
                {JSON.stringify(step.inputs, null, 2)}
              </pre>
            </div>

            <div className={`p-3 ${highlightChanges.includes('outputs') ? 'bg-amber-950/20' : 'bg-[#0f0f0f]'}`}>
              <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Output</div>
              <div className="text-xs text-gray-300 whitespace-pre-wrap break-all leading-relaxed">
                {typeof step.outputs?.content === 'string' ? step.outputs.content : JSON.stringify(step.outputs, null, 2)}

                {step.outputs?.tool_calls && step.outputs.tool_calls.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-800/50">
                    <div className="text-[10px] text-gray-500 mb-1">CALLS</div>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {step.outputs.tool_calls.map((tc: any, i: number) => (
                      <div key={i} className="text-xs text-gray-400">
                        {tc.function?.name}({tc.function?.arguments})
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {(step.type === 'llm_call' || step.type === 'tool_execution') && step.evaluation.status !== 'pending' && step.evaluation.flags && step.evaluation.flags.length > 0 && (
            <div className={`mt-2 p-3 bg-red-950/20 border text-xs ${highlightChanges.includes('evaluation.flags') ? 'border-amber-700/50 text-amber-200' : 'border-red-900/30 text-red-400'}`}>
              <div className="flex gap-2 items-start">
                <AlertCircle size={14} className="shrink-0 mt-0.5 opacity-80" />
                <div>
                  <div className="uppercase tracking-widest text-[9px] mb-1 opacity-70">Judge Flags</div>
                  <div className="flex gap-1.5 flex-wrap mb-1.5">
                    {step.evaluation.flags.map((f: string) => (
                      <span key={f} className="text-[10px] border border-red-800/50 bg-[#1a0f0f] px-1.5 py-0.5">
                        {f}
                      </span>
                    ))}
                  </div>
                  {step.evaluation.reasoning && (
                    <div className="opacity-80">
                      {step.evaluation.reasoning}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {(step.type === 'llm_call' || step.type === 'tool_execution') && step.evaluation.status === 'pending' && (
            <div className="mt-2 text-[10px] text-gray-600 flex items-center gap-1.5 uppercase tracking-widest">
              <Loader2 className="animate-spin" size={10} />
              Analyzing
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-gray-300 font-mono overflow-hidden selection:bg-gray-700 selection:text-white">

      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-80' : 'w-0'} shrink-0 transition-all duration-300 bg-[#0f0f0f] border-r border-gray-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-800 flex items-center justify-between shrink-0">
          <div className="flex bg-[#1a1a1a] p-1 rounded-md w-full mr-2">
            <button
              onClick={() => setSidebarView('traces')}
              className={`flex-1 text-[11px] uppercase tracking-wider py-1 font-bold rounded-sm transition-colors ${sidebarView === 'traces' ? 'bg-[#2a2a2a] text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Traces
            </button>
            <button
              onClick={() => setSidebarView('sessions')}
              className={`flex-1 text-[11px] uppercase tracking-wider py-1 font-bold rounded-sm transition-colors ${sidebarView === 'sessions' ? 'bg-[#2a2a2a] text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Sessions
            </button>
            <button
              onClick={() => setSidebarView('datasets')}
              className={`flex-1 text-[11px] uppercase tracking-wider py-1 font-bold rounded-sm transition-colors ${sidebarView === 'datasets' ? 'bg-[#2a2a2a] text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Datasets
            </button>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="text-gray-500 hover:text-gray-200 transition-colors ml-1">
            <X size={16} />
          </button>
        </div>

        {traces.length >= 2 && (
          <div className="px-3 py-2 border-b border-gray-800 shrink-0 bg-[#0f0f0f]">
            <button
              onClick={() => {
                const newMode = mainView === 'compare' ? 'trace' : 'compare';
                setMainView(newMode);
                if (newMode === 'trace') {
                  setCompareTraceIds([]);
                }
              }}
              className={`w-full py-1.5 text-xs font-bold uppercase tracking-wider border transition-colors ${mainView === 'compare' ? 'bg-indigo-900 border-indigo-700 text-indigo-200' : 'bg-transparent border-gray-700 text-gray-400 hover:bg-[#1f1f1f]'}`}
            >
              {mainView === 'compare' ? 'Exit Compare Mode' : 'Compare Traces'}
            </button>
            {mainView === 'compare' && (
              <div className="text-[10px] text-gray-500 mt-1 text-center">Select 2 traces to diff</div>
            )}
          </div>
        )}

        
        <div className="px-3 py-2 border-b border-gray-800 shrink-0">
          <input 
            type="text" 
            placeholder="Filter by tag (e.g. env=prod) or ID" 
            className="w-full bg-[#141414] border border-gray-700 text-gray-300 text-xs px-2 py-1.5 focus:outline-none focus:border-gray-500"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
          />
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-px">
          {sidebarView === 'traces' && (() => {
            const filteredTraces = traces.filter(t => {
              if (!tagFilter) return true;
              const filterLower = tagFilter.toLowerCase();
              if (t.trace_id.toLowerCase().includes(filterLower)) return true;
              if (t.session_id && t.session_id.toLowerCase().includes(filterLower)) return true;
              if (t.tags) {
                return Object.entries(t.tags).some(([k, v]) => 
                  k.toLowerCase().includes(filterLower) || v.toLowerCase().includes(filterLower) || `${k}=${v}`.toLowerCase().includes(filterLower)
                );
              }
              return false;
            });
            
            return (
              <>
                {filteredTraces.map((t) => {
                  const isSelected = mainView === 'compare' ? compareTraceIds.includes(t.trace_id) : selectedTraceId === t.trace_id;
                  const selectionClass = mainView === 'compare'
                    ? isSelected ? 'bg-indigo-950/40 border-indigo-500 text-gray-100' : 'border-transparent text-gray-400 hover:bg-[#141414] hover:text-gray-200'
                    : isSelected ? 'bg-[#1a1a1a] border-gray-300 text-gray-100' : 'border-transparent text-gray-400 hover:bg-[#141414] hover:text-gray-200';
                  
                  return (
                    <button
                      key={t.trace_id}
                      onClick={() => {
                        if (mainView === 'compare') {
                          setCompareTraceIds(prev => prev.includes(t.trace_id) ? prev.filter(id => id !== t.trace_id) : prev.length >= 2 ? [prev[1], t.trace_id] : [...prev, t.trace_id]);
                        } else {
                          setSelectedTraceId(t.trace_id);
                        }
                      }}
                      className={`w-full text-left p-3 border-l-2 ${selectionClass} transition-all relative group`}
                    >
                      {mainView === 'compare' && (
                        <div className="absolute top-3 right-3 flex items-center justify-center w-4 h-4 border border-gray-600 rounded-sm">
                          {isSelected && <div className="w-2 h-2 bg-indigo-500 rounded-sm" />}
                        </div>
                      )}
                      
                      <div className="flex items-center justify-between mb-1 pr-5">
                        <span className="text-xs truncate mr-2 font-semibold">
                          {t.trace_id.split('_')[1] || t.trace_id}
                        </span>
                        <span className={`text-[9px] px-1 py-0.5 border uppercase font-bold tracking-wider shrink-0 ${t.status === 'error' ? 'border-red-900 text-red-500' : 'border-gray-800 text-gray-500'}`}>{t.status}</span>
                      </div>
                    {t.session_id && (
                      <div className="text-[10px] text-gray-500 mb-1 truncate">
                        Sess: {t.session_id}
                      </div>
                    )}
                    {t.tags && Object.keys(t.tags).length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1.5">
                        {Object.entries(t.tags).map(([k, v]) => (
                          <span key={k} className="text-[9px] bg-[#1f1f1f] text-gray-400 px-1 py-0.5 border border-gray-700">
                            {k}:{v}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-1 text-[10px] opacity-70">
                      <Clock size={10} />
                      {new Date(t.timestamp).toLocaleTimeString()}
                    </div>
                  </button>
                  )
                })}
                {filteredTraces.length === 0 && (
                  <div className="text-center p-6 text-xs text-gray-600">No traces found.</div>
                )}
              </>
            )
          })()}

          {sidebarView === 'sessions' && (() => {
            const filteredSessions = sessions.filter(s => {
              if (!tagFilter) return true;
              return s.session_id.toLowerCase().includes(tagFilter.toLowerCase());
            });

            return (
              <>
                {filteredSessions.map((s) => (
                  <div key={s.session_id} className="mb-2">
                    <button
                      onClick={() => toggleSession(s.session_id)}
                      className="w-full text-left p-2 bg-[#141414] border border-gray-800 hover:bg-[#1a1a1a] text-gray-300 flex items-center justify-between"
                    >
                      <div className="truncate text-xs font-bold mr-2">{s.session_id}</div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[10px] bg-gray-800 px-1.5 py-0.5">{s.trace_count} traces</span>
                      </div>
                    </button>
                    {expandedSessions.has(s.session_id) && (
                      <div className="pl-2 border-l border-gray-800 ml-2 mt-1 space-y-px">
                        {(sessionTraces[s.session_id] || []).map(t => (
                           <button
                           key={t.trace_id}
                           onClick={() => setSelectedTraceId(t.trace_id)}
                           className={`w-full text-left p-2 border-l-2 ${selectedTraceId === t.trace_id ? 'bg-[#1a1a1a] border-gray-300 text-gray-100' : 'border-transparent text-gray-400 hover:bg-[#111] hover:text-gray-200'} transition-all`}
                         >
                           <div className="flex items-center justify-between mb-1">
                             <span className="text-xs truncate mr-2">
                               {t.trace_id.split('_')[1] || t.trace_id}
                             </span>
                             <span className={`text-[9px] px-1 py-0.5 border uppercase font-bold tracking-wider shrink-0 ${t.status === 'error' ? 'border-red-900 text-red-500' : 'border-gray-800 text-gray-500'}`}>{t.status}</span>
                           </div>
                           {t.tags && Object.keys(t.tags).length > 0 && (
                             <div className="flex flex-wrap gap-1 mb-1.5">
                               {Object.entries(t.tags).map(([k, v]) => (
                                 <span key={k} className="text-[9px] bg-[#1a1a1a] text-gray-500 px-1 py-px border border-gray-700">
                                   {k}:{v}
                                 </span>
                               ))}
                             </div>
                           )}
                           <div className="flex items-center gap-1 text-[9px] opacity-70">
                             <Clock size={9} />
                             {new Date(t.timestamp).toLocaleTimeString()}
                           </div>
                         </button>
                        ))}
                        {(!sessionTraces[s.session_id] || sessionTraces[s.session_id].length === 0) && (
                          <div className="p-2 text-[10px] text-gray-600">Loading traces...</div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                {filteredSessions.length === 0 && (
                   <div className="text-center p-6 text-xs text-gray-600">No sessions found.</div>
                )}
              </>
            )
          })()}

          {sidebarView === 'datasets' && (
            <>
              <div className="p-3 border-b border-gray-800">
                <button 
                  onClick={async () => {
                    const name = window.prompt("Enter new dataset name:");
                    if (name) {
                      await fetch('/api/datasets', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) });
                      fetchDatasets();
                    }
                  }}
                  className="w-full py-1.5 text-xs font-bold uppercase tracking-wider bg-[#1a1a1a] border border-gray-700 text-gray-200 hover:bg-[#222] transition-colors"
                >
                  Create Dataset
                </button>
              </div>
              {datasets.map(d => (
                <button
                  key={d.dataset_id}
                  onClick={() => {
                    setSelectedDatasetId(d.dataset_id);
                    setMainView('dataset');
                    fetchDatasetItems(d.dataset_id);
                  }}
                  className={`w-full text-left p-3 border-l-2 ${selectedDatasetId === d.dataset_id && mainView === 'dataset' ? 'bg-[#1a1a1a] border-gray-300 text-gray-100' : 'border-transparent text-gray-400 hover:bg-[#141414] hover:text-gray-200'} transition-all`}
                >
                  <div className="text-xs font-bold truncate mb-1">{d.name}</div>
                  <div className="text-[10px] text-gray-500">{d.dataset_id.split('_')[1] || d.dataset_id}</div>
                </button>
              ))}
              {datasets.length === 0 && <div className="text-center p-6 text-xs text-gray-600">No datasets found.</div>}
            </>
          )}

        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden relative bg-[#0a0a0a]">
        {/* Sticky Header */}
        <div className="bg-[#0f0f0f] border-b border-gray-800 p-4 shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-4">
            {!sidebarOpen && (
              <button onClick={() => setSidebarOpen(true)} className="text-gray-500 hover:text-gray-200">
                <Menu size={18} />
              </button>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-gray-100 tracking-wider uppercase">AgentTrace</h1>
                <span className="text-[10px] bg-gray-800 text-gray-400 px-1.5 py-0.5 ml-2 border border-gray-700">v0.1.1</span>
                <button
                  onClick={() => setAutoRefresh(!autoRefresh)}
                  className={`ml-3 flex items-center gap-1.5 border px-2 py-0.5 text-[9px] uppercase tracking-widest transition-colors ${autoRefresh ? 'border-green-900 bg-[#0a1a0a] text-green-500' : 'border-gray-800 bg-[#141414] text-gray-500'}`}
                >
                  <div className={`w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`}></div>
                  {autoRefresh ? 'Live' : 'Paused'}
                </button>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5">{trace?.trace_id || 'Waiting for connection...'}</p>
            </div>
          </div>

          <div className="flex items-center gap-5">
            {/* Context Window / Main Controls */}
            {mainView === 'trace' ? (
              <>
                {/* Replay Controls */}
                {trace && trace.steps.length > 0 && (
                  <div className="flex items-center gap-2">
                    {replayMode === 'idle' ? (
                      <button onClick={startReplay} className="flex items-center gap-1.5 px-3 py-1 bg-[#1a1a1a] border border-gray-700 hover:bg-[#222] hover:border-gray-500 text-xs text-gray-300 transition-colors">
                        <Play size={12} /> REPLAY
                      </button>
                    ) : replayMode === 'playing' ? (
                      <button onClick={pauseReplay} className="flex items-center gap-1.5 px-3 py-1 bg-gray-800 border border-gray-600 hover:bg-gray-700 text-xs text-gray-200 transition-colors">
                        <Pause size={12} /> PAUSE
                      </button>
                    ) : (
                      <>
                        <button onClick={() => { setReplayMode('playing') }} className="flex items-center gap-1.5 px-3 py-1 bg-gray-800 border border-gray-600 hover:bg-gray-700 text-xs text-gray-200 transition-colors">
                          <Play size={12} /> RESUME
                        </button>
                        <button onClick={stopReplay} className="flex items-center gap-1.5 px-3 py-1 bg-[#111] border border-gray-800 hover:bg-gray-800 text-xs text-gray-400 transition-colors">
                          <X size={12} /> STOP
                        </button>
                      </>
                    )}
                    {replayMode !== 'idle' && (
                      <>
                        <button onClick={() => setReplaySpeed(s => s === 2 ? 0.5 : s + 0.5)} className="flex items-center gap-1 px-2 py-1 bg-transparent hover:bg-gray-800 text-[10px] text-gray-400 border border-gray-800 transition-colors">
                          <SkipForward size={10} /> {replaySpeed}x
                        </button>
                        <span className="text-[10px] text-gray-600 ml-1">{visibleStepCount}/{totalSteps}</span>
                      </>
                    )}
                  </div>
                )}

                <div className="flex flex-col items-end border-l border-gray-800 pl-5">
                  <div className="text-[9px] uppercase tracking-widest text-gray-600 mb-0.5">
                    Context Window
                  </div>
                  <div className="text-gray-300 text-sm">
                    {(() => {
                      if (!trace) return '0';
                      const tokenContextMap = trace.steps.map(s => s.metrics.tokens_total).filter(t => t > 0);
                      const maxTokens = tokenContextMap.length ? Math.max(...tokenContextMap) : 0;
                      const currentTokens = tokenContextMap.length ? tokenContextMap[tokenContextMap.length - 1] : 0;
                      return <>{currentTokens.toLocaleString()} <span className="text-gray-600 text-[10px]">/ {maxTokens.toLocaleString()} ctx</span></>
                    })()}
                  </div>
                </div>
              </>
            ) : (
              // Compare View Header Stats
              compareData && (
                <div className="flex gap-6 items-center border-l-2 border-indigo-900/50 pl-5">
                  <div className="flex flex-col">
                     <span className="text-[9px] uppercase tracking-widest text-gray-500 mb-0.5">Tokens</span>
                     <span className={`text-sm font-bold ${compareData.metrics_delta.total_tokens > 0 ? 'text-amber-500' : compareData.metrics_delta.total_tokens < 0 ? 'text-green-500' : 'text-gray-300'}`}>
                        {compareData.metrics_delta.total_tokens > 0 ? '+' : ''}{compareData.metrics_delta.total_tokens}
                     </span>
                  </div>
                  <div className="flex flex-col">
                     <span className="text-[9px] uppercase tracking-widest text-gray-500 mb-0.5">Latency</span>
                     <span className={`text-sm font-bold ${compareData.metrics_delta.total_latency_ms > 0 ? 'text-amber-500' : compareData.metrics_delta.total_latency_ms < 0 ? 'text-green-500' : 'text-gray-300'}`}>
                        {compareData.metrics_delta.total_latency_ms > 0 ? '+' : ''}{compareData.metrics_delta.total_latency_ms}ms
                     </span>
                  </div>
                  <div className="flex flex-col">
                     <span className="text-[9px] uppercase tracking-widest text-gray-500 mb-0.5">Steps</span>
                     <span className={`text-sm font-bold ${compareData.metrics_delta.steps_count > 0 ? 'text-amber-500' : compareData.metrics_delta.steps_count < 0 ? 'text-green-500' : 'text-gray-300'}`}>
                        {compareData.metrics_delta.steps_count > 0 ? '+' : ''}{compareData.metrics_delta.steps_count}
                     </span>
                  </div>
                </div>
              )
            )}
          </div>
        </div>

        {/* Timeline / Compare View / Dataset View */}
        {mainView === 'dataset' ? (
          <div className="flex-1 overflow-y-auto pb-20 p-6">
            {!selectedDatasetId ? (
              <div className="h-full flex items-center justify-center text-gray-600 text-sm">Select a dataset from the sidebar</div>
            ) : (
              <div className="max-w-4xl mx-auto space-y-6">
                 <div className="flex justify-between items-center mb-6">
                   <h2 className="text-xl font-bold uppercase tracking-wider">{datasets.find(d => d.dataset_id === selectedDatasetId)?.name}</h2>
                   <div className="flex items-center gap-4">
                     <span className="text-xs text-gray-500">{datasetItems.length} items</span>
                     <button
                       onClick={async () => {
                         const sourceValue = window.prompt("Enter Session ID to import traces from:");
                         if (!sourceValue) return;
                         try {
                           const res = await fetch(`/api/datasets/${selectedDatasetId}/batch`, {
                             method: 'POST',
                             headers: {'Content-Type': 'application/json'},
                             body: JSON.stringify({ source_type: 'session', source_value: sourceValue })
                           });
                           if (res.ok) {
                             const data = await res.json();
                             alert(`Successfully imported ${data.added_count} items!`);
                             fetchDatasetItems(selectedDatasetId);
                           } else {
                             alert("Failed to batch import.");
                           }
                         } catch {
                           alert("Error batch importing.");
                         }
                       }}
                       className="px-3 py-1 bg-indigo-900 border border-indigo-700 text-indigo-200 text-xs font-bold uppercase tracking-widest hover:bg-indigo-800 transition-colors rounded-sm"
                     >
                       Batch Add (Session)
                     </button>
                     <button
                       onClick={async () => {
                         try {
                           const res = await fetch(`/api/datasets/${selectedDatasetId}/export`);
                           if (res.ok) {
                             const data = await res.json();
                             const blob = new Blob([data.jsonl], { type: 'application/jsonl' });
                             const url = window.URL.createObjectURL(blob);
                             const a = document.createElement('a');
                             a.href = url;
                             a.download = `dataset_${selectedDatasetId}.jsonl`;
                             document.body.appendChild(a);
                             a.click();
                             window.URL.revokeObjectURL(url);
                             document.body.removeChild(a);
                           }
                         } catch {
                           alert("Error exporting dataset.");
                         }
                       }}
                       className="px-3 py-1 bg-[#1a1a1a] border border-gray-700 text-gray-300 text-xs font-bold uppercase tracking-widest hover:bg-[#222] transition-colors rounded-sm"
                     >
                       Export JSONL
                     </button>
                   </div>
                 </div>
                 {datasetItems.length === 0 ? (
                    <div className="text-center p-8 border border-dashed border-gray-800 text-gray-600">No items yet. Save traces to this dataset.</div>
                 ) : (
                    datasetItems.map(item => (
                       <div key={item.item_id} className="p-4 bg-[#0f0f0f] border border-gray-800">
                         <div className="grid grid-cols-2 gap-4">
                            <div>
                               <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Inputs</div>
                               <pre className="text-[10px] text-gray-400 whitespace-pre-wrap break-all bg-[#0a0a0a] p-2 border border-gray-900 rounded">
                                 {JSON.stringify(item.inputs, null, 2)}
                               </pre>
                            </div>
                            <div>
                               <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Expected Outputs</div>
                               <pre className="text-[10px] text-gray-400 whitespace-pre-wrap break-all bg-[#0a0a0a] p-2 border border-gray-900 rounded">
                                 {JSON.stringify(item.expected_outputs, null, 2) || 'None'}
                               </pre>
                            </div>
                         </div>
                       </div>
                    ))
                 )}
              </div>
            )}
          </div>
        ) : mainView === 'compare' ? (
          <div className="flex-1 overflow-y-auto pb-20">
            {!compareData ? (
               <div className="h-full flex flex-col items-center justify-center text-gray-600 text-sm gap-3">
                 {compareTraceIds.length < 2 ? 'Select 2 traces to diff' : <><Loader2 className="animate-spin" size={20} /> DIFFING TRACES</>}
               </div>
            ) : (
               <div className="max-w-[1400px] mx-auto mt-6 px-4 pb-20">
                  <div className="flex items-center gap-4 mb-6 border-b border-gray-800 pb-2">
                     <div className="flex-1 text-right text-xs font-bold uppercase tracking-widest text-gray-400">
                        Left: {compareData.left.trace_id.split('_')[1] || compareData.left.trace_id}
                     </div>
                     <button 
                       onClick={() => setCompareTraceIds([compareTraceIds[1], compareTraceIds[0]])}
                       className="px-2 py-0.5 text-[9px] uppercase tracking-widest bg-[#1a1a1a] border border-gray-700 hover:bg-[#222] text-gray-400 transition-colors rounded-sm"
                     >
                        Swap
                     </button>
                     <div className="flex-1 text-left text-xs font-bold uppercase tracking-widest text-indigo-400">
                        Right: {compareData.right.trace_id.split('_')[1] || compareData.right.trace_id}
                     </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-6 relative">
                     {/* Center connector line */}
                     <div className="absolute top-0 bottom-0 left-1/2 w-px bg-gray-800 -translate-x-1/2 z-0" />
                     
                     {compareData.steps.map((diff, i) => (
                       <React.Fragment key={i}>
                         <div className="z-10 relative">
                            {diff.left_step ? (
                              <>
                                {diff.status === 'removed' && (
                                  <div className="absolute top-1/2 -right-3 w-3 h-px bg-red-800/50" />
                                )}
                                {diff.status === 'changed' && (
                                  <div className="absolute top-1/2 -right-3 w-3 h-px bg-amber-700/50" />
                                )}
                                {diff.status === 'unchanged' && (
                                  <div className="absolute top-1/2 -right-3 w-3 h-px bg-gray-700" />
                                )}
                                {renderTraceStep(diff.left_step, false, diff.changes, diff.status === 'removed' ? 'removed' : diff.status === 'changed' ? 'changed' : null)}
                              </>
                            ) : (
                              <div className="p-4 border border-dashed border-gray-800/40 bg-gray-900/10 h-full min-h-[100px] flex items-center justify-center text-[10px] text-gray-600 uppercase tracking-widest rounded">
                                Missing Step
                              </div>
                            )}
                         </div>
                         <div className="z-10 relative">
                            {diff.right_step ? (
                              <>
                                {diff.status === 'added' && (
                                  <div className="absolute top-1/2 -left-3 w-3 h-px bg-green-800/50" />
                                )}
                                {diff.status === 'changed' && (
                                  <div className="absolute top-1/2 -left-3 w-3 h-px bg-amber-700/50" />
                                )}
                                {diff.status === 'unchanged' && (
                                  <div className="absolute top-1/2 -left-3 w-3 h-px bg-gray-700" />
                                )}
                                {renderTraceStep(diff.right_step, false, diff.changes, diff.status === 'added' ? 'added' : diff.status === 'changed' ? 'changed' : null)}
                              </>
                            ) : (
                              <div className="p-4 border border-dashed border-gray-800/40 bg-gray-900/10 h-full min-h-[100px] flex items-center justify-center text-[10px] text-gray-600 uppercase tracking-widest rounded">
                                Missing Step
                              </div>
                            )}
                         </div>
                       </React.Fragment>
                     ))}
                  </div>
               </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto pb-20">
            {!trace ? (
              <div className="h-full flex flex-col items-center justify-center text-gray-600 text-sm animate-pulse gap-3">
                <Loader2 className="animate-spin" size={20} />
                AWAITING_TELEMETRY
              </div>
            ) : (
              <div className="max-w-4xl mx-auto mt-8 px-4 pb-20">
                <div className="relative ml-4 pl-8 space-y-6">
                  {/* Continuous Timeline Line */}
                  <div className="absolute top-4 bottom-0 left-0 w-px bg-gray-800" />

                  {(replayMode !== 'idle' ? trace.steps.slice(0, visibleStepCount) : trace.steps).map((step, stepIndex) => {
                    const isNewStep = replayMode !== 'idle' && stepIndex === visibleStepCount - 1;
                    return renderTraceStep(step, isNewStep);
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Replay Scrubber */}
        {mainView === 'trace' && replayMode !== 'idle' && totalSteps > 0 && (
          <div className="absolute bottom-0 left-0 right-0 bg-[#0a0a0a] border-t border-gray-800 p-3 px-6 flex items-center gap-4 z-20">
            <span className="text-[10px] text-gray-600 shrink-0 uppercase">Step {visibleStepCount}</span>
            <input
              type="range"
              min={0}
              max={totalSteps}
              value={visibleStepCount}
              onChange={(e) => {
                setVisibleStepCount(parseInt(e.target.value))
                setReplayMode('paused')
              }}
              className="flex-1 h-0.5 bg-gray-800 appearance-none cursor-pointer accent-gray-500 hover:accent-gray-300 transition-all"
            />
            <span className="text-[10px] text-gray-600 shrink-0 uppercase">{totalSteps} Total</span>
          </div>
        )}

      </div>

      {/* Global Replay CSS */}
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeSlideIn { animation: fadeSlideIn 400ms ease-out forwards; }

        @keyframes pulseRed {
          0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
          50% { box-shadow: 0 0 12px 4px rgba(239, 68, 68, 0.4); }
        }
        .animate-pulseRed { animation: pulseRed 1.5s ease-in-out infinite; }

        @keyframes shakeX {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-6px); }
          40% { transform: translateX(6px); }
          60% { transform: translateX(-4px); }
          80% { transform: translateX(4px); }
        }
        .animate-shakeX { animation: shakeX 0.5s ease-in-out; }

        input[type="range"]::-webkit-slider-thumb {
          appearance: none;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #3b82f6;
          cursor: pointer;
          border: 2px solid #1e3a5f;
        }
      `}</style>
    </div>
  )
}

export default App
