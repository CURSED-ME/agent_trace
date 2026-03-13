<div align="center">

# 🔍 AgentTrace

**Zero-config visual debugging and auto-evaluation for LLM agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-native-blueviolet)](https://opentelemetry.io/)

*One import. Zero config. Instant visual timeline of every LLM call, tool execution, and crash your agent makes.*

</div>

---

## The Problem

You build an AI agent. It calls an LLM, uses tools, chains prompts together. Then it hallucinates, loops infinitely, or silently drops context — and you have **no idea where it went wrong.**

Every other observability tool requires accounts, API keys, cloud dashboards, and framework-specific setup. You just want to **see what happened.**

## The Solution

```python
import agenttrace.auto  # ← That's it. One line.

# ... your existing agent code runs normally ...
# When it finishes, a local dashboard opens automatically at localhost:8000
```

AgentTrace intercepts every LLM call, tool execution, and unhandled crash — then serves a beautiful local timeline you can replay step-by-step.

---

## ✨ Features

### 🪄 True Zero-Config
Add `import agenttrace.auto` to the top of your script. No API keys, no accounts, no cloud. Works with **OpenAI**, **Groq**, **Anthropic**, **Mistral**, **Google Gemini**, **LangChain**, **CrewAI**, and **15+ more** out of the box.

### 🧠 Smart Auto-Judge
AgentTrace doesn't just *show* you what happened — it *tells you what went wrong:*

| Evaluation | How It Works | Cost |
|---|---|---|
| 🔁 **Loop Detection** | Flags 3+ identical consecutive tool calls | Free (pure Python) |
| 💰 **Cost Anomaly** | Flags steps using >2x average tokens | Free (pure Python) |
| ⏱️ **Latency Regression** | Flags steps >3x slower than average | Free (pure Python) |
| 🔧 **Tool Misuse** | Detects wrong arguments or failed tool calls | LLM-powered (optional) |
| 📝 **Instruction Drift** | Detects when LLM ignores the system prompt | LLM-powered (optional) |

> LLM-powered checks require a free [Groq API key](https://console.groq.com). Install with `pip install "agenttrace-ai[judge]"`.

### ▶️ Trace Replay
Press **Play** and watch your agent's execution animate step-by-step — like a video recording of its thought process. Drag the scrubber to jump to any moment. Flagged steps pulse red.

### 💥 Crash Detection
If your agent throws an unhandled exception, AgentTrace catches it and logs the full traceback as a trace step — so you never lose debugging data.

### 🔌 Framework Support

#### LLM Providers
| Provider | Status | Install |
|---|---|---|
| OpenAI | ✅ Native | `pip install "agenttrace-ai[openai]"` |
| Groq | ✅ Native | `pip install "agenttrace-ai[openai]"` |
| Anthropic (Claude) | ✅ Native | `pip install "agenttrace-ai[anthropic]"` |
| Mistral AI | ✅ Native | `pip install "agenttrace-ai[mistral]"` |
| Google Gemini | ✅ Native | `pip install "agenttrace-ai[google]"` |
| Cohere | ✅ Native | `pip install "agenttrace-ai[cohere]"` |
| AWS Bedrock | ✅ Native | `pip install "agenttrace-ai[bedrock]"` |
| Ollama | ✅ Native | `pip install "agenttrace-ai[ollama]"` |
| Replicate | ✅ Native | `pip install "agenttrace-ai[all]"` |
| Together AI | ✅ Native | `pip install "agenttrace-ai[all]"` |

#### Agent Frameworks
| Framework | Status | Install |
|---|---|---|
| LangChain | ✅ Adapter | None (auto-detected) |
| CrewAI | ✅ Adapter | None (auto-detected) |
| LlamaIndex | ✅ Native | `pip install "agenttrace-ai[all]"` |
| Haystack | ✅ Native | `pip install "agenttrace-ai[all]"` |

#### Vector Databases
| Database | Status | Install |
|---|---|---|
| ChromaDB | ✅ Native | `pip install "agenttrace-ai[vectordb]"` |
| Pinecone | ✅ Native | `pip install "agenttrace-ai[vectordb]"` |

---

## 🚀 Quickstart

### Install

```bash
# Core (works with LangChain out of the box)
pip install agenttrace-ai

# With OpenAI/Groq support
pip install "agenttrace-ai[openai]"

# With everything (OpenAI + Auto-Judge + LangChain)
pip install "agenttrace-ai[all]"
```

### Basic Usage (OpenAI / Groq)

```python
import agenttrace.auto  # ← Add this one line
import openai

client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "What is the capital of France?"}]
)
print(response.choices[0].message.content)
# Dashboard opens automatically at http://localhost:8000 when your script finishes
```

### LangChain (Zero-Config)

```python
import agenttrace.auto  # ← Same one line
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(model="gpt-4")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("human", "{input}")
])

chain = prompt | llm
result = chain.invoke({"input": "Explain quantum computing"})
# All LLM calls automatically appear in the AgentTrace dashboard
```

### Node.js & TypeScript SDK

AgentTrace now natively supports Javascript/Typescript AI agents via the `@opentelemetry` standard!

**1. Install the SDK:**
```bash
npm install agenttrace-node
```

**2. Initialize tracking at the top of your index file:**
```typescript
import { init, shutdown } from "agenttrace-node";
import { OpenAI } from "openai";

// 1. Initialize OTLP tracer
init({
  serviceName: "my-ai-agent"
});

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

async function main() {
  const response = await client.chat.completions.create({
    model: "gpt-4o",
    messages: [{ role: "user", content: "Hello!" }]
  });
  
  // 2. Gracefully flush traces before the Node event loop exits
  await shutdown(); 
}
main();
```

### Custom Tool Tracking

```python
from agenttrace import track_tool, track_agent

@track_tool
def search_database(query: str) -> str:
    return db.search(query)

@track_agent
def my_agent(task: str) -> str:
    data = search_database(task)
    return llm.complete(f"Answer based on: {data}")
```

---

## 🏗️ Architecture

```
Your Agent Script
       │
       ▼
  import agenttrace.auto
       │
       ├─── OpenTelemetry TracerProvider
       │         │
       │         ├── OpenAI / Groq Instrumentor
       │         ├── Anthropic / Mistral / Cohere Instrumentors
       │         ├── Google Gemini / Bedrock / Ollama Instrumentors
       │         ├── LangChain / CrewAI Callback Adapters
       │         └── ChromaDB / Pinecone Vector DB Instrumentors
       │         │
       │         ▼
       │    AgentTraceExporter → SQLite (.agenttrace.db)
       │
       ├─── sys.excepthook → Crash capture
       │
       └─── atexit → FastAPI Server (localhost:8000)
                         │
                         ├── /api/traces
                         ├── /api/trace/{id}
                         └── React Dashboard (Vite + Tailwind)
```

### Key Design Decisions
- **OpenTelemetry** for instrumentation (industry standard, not fragile monkey-patching)
- **SQLite with WAL mode** for zero-config persistence that survives crashes
- **`contextvars`** for thread-safe multi-agent isolation
- **Pre-compiled React UI** bundled inside the Python package

---

## 📁 Project Structure

```
agenttrace/
├── auto.py              # Zero-config entry point (import this)
├── exporter.py          # OTel SpanExporter → SQLite
├── judge.py             # Smart Auto-Judge engine (5 eval types)
├── models.py            # Pydantic data models
├── storage.py           # SQLite with WAL mode
├── server.py            # FastAPI dashboard server
├── decorators.py        # @track_tool, @track_agent
├── utils.py             # Payload truncation
├── integrations/
│   ├── langchain.py     # LangChain callback adapter
│   └── crewai.py        # CrewAI callback adapter
└── static/              # Pre-compiled React dashboard
```

---

## ⚙️ Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Required for LLM-powered judge evaluations |
| `AGENTTRACE_DB_PATH` | `.agenttrace.db` | Custom database file path |
| `AGENTTRACE_FULL_PAYLOAD` | `0` | Set to `1` to disable payload truncation |
| `AGENTTRACE_MAX_CONTENT` | `500` | Max characters before truncation |

---

## 🤝 Contributing

We welcome contributions! Here's how to set up the dev environment:

```bash
git clone https://github.com/CURSED-ME/AgentTrace.git
cd AgentTrace
pip install -e ".[all]"

# Frontend development
cd ui
npm install
npm run dev    # Dev server with hot reload
npm run build  # Compile to agenttrace/static/
```

See [.env.example](.env.example) for required environment variables.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ for the agent builder community.**

*If AgentTrace helped you debug an agent, give us a ⭐ on GitHub!*

</div>
