import { useEffect, useState, useRef, useCallback } from 'react'
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
  inputs: any
  outputs: any
  metrics: StepMetrics
  evaluation: StepEvaluation
  timestamp: string
}

interface AgentTrace {
  trace_id: string
  timestamp: string
  status: string
  steps: TraceStep[]
}

const App = () => {
  const [trace, setTrace] = useState<AgentTrace | null>(null)
  const [traces, setTraces] = useState<AgentTrace[]>([])
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
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
    } catch (e: any) {
      console.error(e)
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
    } catch (e: any) {
      setError("Server disconnected.")
    }
  }

  useEffect(() => {
    fetchTraces()
    fetchTrace()

    let interval: ReturnType<typeof setInterval>
    if (autoRefresh && replayMode === 'idle') {
      interval = setInterval(() => {
        fetchTraces()
        fetchTrace()
      }, 2000)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [selectedTraceId, autoRefresh, replayMode])

  if (error && !trace) {
    return <div className="p-8 text-red-500 font-mono">Error: {error}</div>
  }

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-gray-300 font-mono overflow-hidden selection:bg-gray-700 selection:text-white">

      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-80' : 'w-0'} shrink-0 transition-all duration-300 bg-[#0f0f0f] border-r border-gray-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-2 h-4 bg-gray-400"></div>
            <h2 className="font-bold text-gray-100 uppercase tracking-widest text-sm">Traces</h2>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="text-gray-500 hover:text-gray-200 transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-px">
          {traces.map((t) => (
            <button
              key={t.trace_id}
              onClick={() => setSelectedTraceId(t.trace_id)}
              className={`w-full text-left p-3 border-l-2 ${selectedTraceId === t.trace_id ? 'bg-[#1a1a1a] border-gray-300 text-gray-100' : 'border-transparent text-gray-400 hover:bg-[#141414] hover:text-gray-200'} transition-all`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs truncate mr-2">{t.trace_id.split('_')[1] || t.trace_id}</span>
                <span className={`text-[9px] px-1 py-0.5 border uppercase font-bold tracking-wider ${t.status === 'error' ? 'border-red-900 text-red-500' : 'border-gray-800 text-gray-500'}`}>{t.status}</span>
              </div>
              <div className="flex items-center gap-1 text-[10px] opacity-70">
                <Clock size={10} />
                {new Date(t.timestamp).toLocaleTimeString()}
              </div>
            </button>
          ))}
          {traces.length === 0 && (
            <div className="text-center p-6 text-xs text-gray-600">No traces available.</div>
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
          </div>
        </div>

        {/* Timeline */}
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

                  const isNewStep = replayMode !== 'idle' && stepIndex === visibleStepCount - 1
                  const hasFlagsDuringReplay = replayMode !== 'idle' && (step.evaluation.flags?.length ?? 0) > 0

                  return (
                    <div key={step.step_id} className={`relative ${isNewStep ? 'animate-fadeSlideIn' : ''}`} style={isNewStep ? { animationDuration: '400ms' } : undefined}>
                      {/* Timeline Node */}
                      <div className={`absolute -left-[41px] top-4 w-5 h-5 bg-[#0f0f0f] border border-gray-700 flex items-center justify-center z-10 ${hasFlagsDuringReplay ? 'border-red-500 animate-pulse' : ''}`}>
                        <div className={`w-1.5 h-1.5 ${title === 'CRASH' ? 'bg-red-500' : 'bg-gray-500'}`}></div>
                      </div>

                      <div className={`p-4 bg-[#0f0f0f] border ${step.evaluation.status === 'fail' || step.type === 'server_crash' ? 'border-red-900/50' : 'border-gray-800'} ${step.type === 'server_crash' && isNewStep ? 'animate-shakeX' : ''}`}>

                        <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-800/50">
                          <div className="flex items-center gap-3">
                            <span className={`text-[10px] px-1.5 py-0.5 font-bold tracking-widest ${badge}`}>{title}</span>
                            <span className="text-sm text-gray-200">{step.name}</span>
                          </div>
                          <span className="text-gray-600 text-[10px]">{step.metrics.latency_ms}ms</span>
                        </div>

                        <div className="grid grid-cols-1 gap-px bg-gray-800 border border-gray-800 mb-4">
                          <div className="bg-[#0f0f0f] p-3">
                            <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Input</div>
                            <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all leading-relaxed">
                              {JSON.stringify(step.inputs, null, 2)}
                            </pre>
                          </div>

                          <div className="bg-[#0f0f0f] p-3">
                            <div className="text-[10px] text-gray-500 mb-2 uppercase tracking-widest">Output</div>
                            <div className="text-xs text-gray-300 whitespace-pre-wrap break-all leading-relaxed">
                              {typeof step.outputs?.content === 'string' ? step.outputs.content : JSON.stringify(step.outputs, null, 2)}

                              {step.outputs?.tool_calls && step.outputs.tool_calls.length > 0 && (
                                <div className="mt-3 pt-3 border-t border-gray-800/50">
                                  <div className="text-[10px] text-gray-500 mb-1">CALLS</div>
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
                          <div className="mt-2 p-3 bg-red-950/20 border border-red-900/30 text-red-400 text-xs">
                            <div className="flex gap-2 items-start">
                              <AlertCircle size={14} className="shrink-0 mt-0.5 opacity-80" />
                              <div>
                                <div className="uppercase tracking-widest text-[9px] mb-1 opacity-70">Judge Flags</div>
                                <div className="flex gap-1.5 flex-wrap mb-1.5">
                                  {step.evaluation.flags.map(f => (
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
                })}
              </div>
            </div>
          )}
        </div>

        {/* Replay Scrubber */}
        {replayMode !== 'idle' && totalSteps > 0 && (
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
