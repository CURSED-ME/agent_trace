import { useEffect, useState, useRef, useCallback } from 'react'
import { CheckCircle, XCircle, Wrench, MessageSquare, Box, Server, AlertCircle, Loader2, Menu, X, Clock, Play, Pause, SkipForward } from 'lucide-react'

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
    const interval = setInterval(() => {
      fetchTraces()
      fetchTrace()
    }, 2000)
    return () => clearInterval(interval)
  }, [selectedTraceId])

  if (error && !trace) {
    return <div className="p-8 text-red-500 font-mono">Error: {error}</div>
  }

  return (
    <div className="flex h-screen bg-[#0f1115] text-gray-200 font-sans overflow-hidden">

      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-80' : 'w-0'} shrink-0 transition-all duration-300 bg-[#161b22] border-r border-gray-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-gray-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Box className="text-blue-500" size={20} />
            <h2 className="font-bold text-gray-200">History</h2>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="text-gray-500 hover:text-gray-300">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {traces.map((t) => (
            <button
              key={t.trace_id}
              onClick={() => setSelectedTraceId(t.trace_id)}
              className={`w-full text-left p-3 rounded-lg border ${selectedTraceId === t.trace_id ? 'bg-blue-900/20 border-blue-500/30' : 'border-transparent hover:bg-gray-800/50'} transition-colors`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs text-gray-300">{t.trace_id.split('_')[1] || t.trace_id}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-bold ${t.status === 'error' ? 'bg-red-900/50 text-red-400' : 'bg-green-900/50 text-green-400'}`}>{t.status}</span>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-gray-500">
                <Clock size={12} />
                {new Date(t.timestamp).toLocaleTimeString()}
              </div>
            </button>
          ))}
          {traces.length === 0 && (
            <div className="text-center p-4 text-xs text-gray-500 font-mono">No traces found.</div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Sticky Header */}
        <div className="bg-[#161b22]/90 backdrop-blur-md border-b border-gray-800 p-4 shrink-0 shadow-lg flex items-center justify-between">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button onClick={() => setSidebarOpen(true)} className="text-gray-400 hover:text-gray-200 mr-2">
                <Menu size={20} />
              </button>
            )}
            <div className="flex items-center gap-2">
              <Box className="text-blue-500" />
              <div>
                <h1 className="text-xl font-bold tracking-tight text-white">AgentTrace</h1>
                <p className="text-xs text-gray-400 font-mono">{trace?.trace_id || 'Waiting for agent...'}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Replay Controls */}
            {trace && trace.steps.length > 0 && (
              <div className="flex items-center gap-2 mr-4">
                {replayMode === 'idle' ? (
                  <button onClick={startReplay} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-semibold transition-colors" title="Replay trace step by step">
                    <Play size={14} /> Replay
                  </button>
                ) : replayMode === 'playing' ? (
                  <button onClick={pauseReplay} className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 rounded-lg text-xs font-semibold transition-colors">
                    <Pause size={14} /> Pause
                  </button>
                ) : (
                  <>
                    <button onClick={() => { setReplayMode('playing') }} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-semibold transition-colors">
                      <Play size={14} /> Resume
                    </button>
                    <button onClick={stopReplay} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-xs font-semibold transition-colors">
                      <X size={14} /> Stop
                    </button>
                  </>
                )}
                {replayMode !== 'idle' && (
                  <>
                    <button onClick={() => setReplaySpeed(s => s === 2 ? 0.5 : s + 0.5)} className="flex items-center gap-1 px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-[10px] font-mono text-gray-300 border border-gray-700 transition-colors">
                      <SkipForward size={12} /> {replaySpeed}x
                    </button>
                    <span className="text-[11px] font-mono text-gray-500">{visibleStepCount}/{totalSteps}</span>
                  </>
                )}
              </div>
            )}

            <div className="flex flex-col items-end">
              <div className="text-xs uppercase tracking-wider font-semibold text-gray-500 mb-1">
                Total Tokens Context
              </div>
              <div className="text-blue-400 font-mono text-xl">
                {(() => {
                  if (!trace) return '0';
                  const tokenContextMap = trace.steps.map(s => s.metrics.tokens_total).filter(t => t > 0);
                  const maxTokens = tokenContextMap.length ? Math.max(...tokenContextMap) : 0;
                  const currentTokens = tokenContextMap.length ? tokenContextMap[tokenContextMap.length - 1] : 0;
                  return <>{currentTokens.toLocaleString()} <span className="text-gray-600 text-sm">/ {maxTokens.toLocaleString()} peak</span></>
                })()}
              </div>
            </div>
          </div>
        </div>

        {/* Timeline */}
        <div className="flex-1 overflow-y-auto pb-20">
          {!trace ? (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 font-mono animate-pulse gap-3">
              <Loader2 className="animate-spin" size={24} />
              Waiting for agent trace data...
            </div>
          ) : (
            <div className="max-w-3xl mx-auto mt-8 px-4">
              <div className="relative border-l-2 border-gray-800 ml-4 pl-8 space-y-10">
                {(replayMode !== 'idle' ? trace.steps.slice(0, visibleStepCount) : trace.steps).map((step, stepIndex) => {

                  let icon = <MessageSquare size={18} />
                  let color = "bg-blue-600 border-blue-500"
                  let title = "User/System Prompt"

                  if (step.type === "tool_execution") {
                    icon = <Wrench size={18} className="text-gray-300" />
                    color = "bg-gray-700 border-gray-600"
                    title = "Tool Execution"
                  } else if (step.type === "server_crash") {
                    icon = <AlertCircle size={18} className="text-red-100" />
                    color = "bg-red-700 border-red-600"
                    title = "Crash / Unhandled Exception"
                  } else if (step.type === "llm_call") {
                    icon = <Server size={18} className="text-green-100" />
                    color = "bg-green-600 border-green-500"
                    title = "LLM Thought"

                    if (step.evaluation.status === 'fail') {
                      color = "bg-red-600 border-red-500"
                      icon = <AlertCircle size={18} className="text-red-100" />
                    } else if (step.evaluation.status === 'pending') {
                      color = "bg-yellow-600 border-yellow-500"
                      icon = <Loader2 size={18} className="animate-spin text-yellow-100" />
                    }
                  }

                  const isNewStep = replayMode !== 'idle' && stepIndex === visibleStepCount - 1
                  const hasFlagsDuringReplay = replayMode !== 'idle' && (step.evaluation.flags?.length ?? 0) > 0

                  return (
                    <div key={step.step_id} className={`relative ${isNewStep ? 'animate-fadeSlideIn' : ''}`} style={isNewStep ? { animationDuration: '400ms' } : undefined}>
                      <div className={`absolute -left-[45px] top-1 w-10 h-10 rounded-full border-4 border-[#0f1115] shadow-lg flex items-center justify-center ${color} z-10 ${hasFlagsDuringReplay ? 'animate-pulseRed' : ''}`}>
                        {icon}
                      </div>

                      <div className={`p-5 rounded-2xl border bg-[#161b22] shadow-xl ${step.evaluation.status === 'fail' || step.type === 'server_crash' ? 'border-red-900/50 shadow-red-900/10' : 'border-gray-800'} ${step.type === 'server_crash' && isNewStep ? 'animate-shakeX' : ''}`}>

                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-gray-200">{title}</span>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 font-mono border border-gray-700">{step.name}</span>
                          </div>
                          <span className="text-gray-500 text-xs font-mono">{step.metrics.latency_ms}ms</span>
                        </div>

                        <div className="mb-4">
                          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">Input</div>
                          <div className="bg-[#0d1117] p-3 rounded-lg border border-gray-800/60 overflow-x-auto">
                            <pre className="text-xs text-blue-200 font-mono whitespace-pre-wrap break-all">
                              {JSON.stringify(step.inputs, null, 2)}
                            </pre>
                          </div>
                        </div>

                        <div className="mb-4">
                          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">Output</div>
                          <div className="bg-[#000000] p-3 rounded-lg border border-gray-800/60 overflow-x-auto text-gray-300 text-sm whitespace-pre-wrap break-all">
                            {typeof step.outputs?.content === 'string' ? step.outputs.content : JSON.stringify(step.outputs, null, 2)}

                            {step.outputs?.tool_calls && step.outputs.tool_calls.length > 0 && (
                              <div className="mt-4 pt-4 border-t border-gray-800">
                                <div className="text-xs text-gray-500 mb-2 font-mono">Tool Calls Triggered:</div>
                                {step.outputs.tool_calls.map((tc: any, i: number) => (
                                  <div key={i} className="text-xs font-mono bg-blue-900/20 text-blue-300 p-2 rounded mb-1">
                                    {tc.function?.name}({tc.function?.arguments})
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>

                        {(step.type === 'llm_call' || step.type === 'tool_execution') && step.evaluation.status !== 'pending' && (
                          <div className={`mt-4 p-4 rounded-xl border ${step.evaluation.status === 'fail' ? 'bg-red-950/30 border-red-900/50 text-red-300' : 'bg-green-950/20 border-green-900/30 text-green-400'}`}>
                            <div className="flex items-start gap-3 flex-col sm:flex-row">
                              {step.evaluation.status === 'fail' ? <XCircle className="shrink-0 mt-0.5 text-red-500" size={18} /> : <CheckCircle className="shrink-0 mt-0.5 text-green-500" size={18} />}
                              <div className="flex-1 w-full">
                                <div className="font-semibold text-sm mb-2 uppercase tracking-wider flex items-center justify-between">
                                  <span>{step.evaluation.status === 'fail' ? 'Judge Flagged Issues' : 'Judge Passed'}</span>
                                  {step.evaluation.flags && step.evaluation.flags.length > 0 && (
                                    <div className="flex gap-1 flex-wrap justify-end">
                                      {step.evaluation.flags.map(f => (
                                        <span key={f} className="text-[10px] bg-red-900/40 text-red-200 px-2 py-0.5 rounded border border-red-800/50">
                                          {f.replace('_', ' ')}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                                {step.evaluation.reasoning && (
                                  <div className="text-sm opacity-90 leading-relaxed">
                                    {step.evaluation.reasoning}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {(step.type === 'llm_call' || step.type === 'tool_execution') && step.evaluation.status === 'pending' && (
                          <div className="mt-4 p-3 rounded-xl border bg-yellow-950/20 border-yellow-900/30 text-yellow-500/80 flex items-center gap-2 text-sm">
                            <Loader2 className="animate-spin" size={16} />
                            Judge is analyzing this step...
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
          <div className="absolute bottom-0 left-0 right-0 bg-[#161b22]/95 backdrop-blur-md border-t border-gray-800 p-3 px-6 flex items-center gap-4 z-20">
            <span className="text-[11px] font-mono text-gray-500 shrink-0">Step {visibleStepCount}</span>
            <input
              type="range"
              min={0}
              max={totalSteps}
              value={visibleStepCount}
              onChange={(e) => {
                setVisibleStepCount(parseInt(e.target.value))
                setReplayMode('paused')
              }}
              className="flex-1 h-1.5 bg-gray-800 rounded-full appearance-none cursor-pointer accent-blue-500"
            />
            <span className="text-[11px] font-mono text-gray-500 shrink-0">{totalSteps} total</span>
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
