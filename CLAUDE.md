# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAG (Retrieval-Augmented Generation) chatbot for querying educational course materials. Full-stack app with a Python/FastAPI backend, vanilla HTML/CSS/JS frontend, ChromaDB vector database, and Anthropic Claude API for generation.

## Important Rules

- Always use `uv` to run the server and manage dependencies. Never use `pip`.
- Before running any shell command that uses `uv`, prepend: `export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`

## Commands

### Install dependencies
```bash
uv sync
```

### Run the application
```bash
# From project root:
./run.sh
# Or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

### Access
- Web UI: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

### Environment setup
Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

## Architecture

The system follows a pipeline: **Frontend → FastAPI → RAGSystem → (VectorStore + AIGenerator) → Claude API**.

### Backend (`backend/`)

- **app.py** — FastAPI entry point. Serves the frontend as static files, exposes `/api/query` (POST) and `/api/courses` (GET). Loads documents from `../docs` on startup.
- **rag_system.py** — Main orchestrator. Coordinates document ingestion, query handling, session management, and tool-based search. The `query()` method is the core pipeline entry point.
- **document_processor.py** — Parses course text files with a specific format (Course Title/Link/Instructor headers, then `Lesson N:` sections). Chunks text by sentences with configurable size/overlap.
- **vector_store.py** — ChromaDB wrapper with two collections: `course_catalog` (metadata) and `course_content` (text chunks). Uses SentenceTransformer `all-MiniLM-L6-v2` for embeddings. Includes fuzzy course name resolution via semantic matching.
- **ai_generator.py** — Claude API client using tool-calling. Sends the search tool definition to Claude, handles tool execution loops, and returns formatted responses. Uses claude-sonnet-4-20250514 with temperature=0.
- **search_tools.py** — Tool framework with abstract `Tool` base class. `CourseSearchTool` implements filtered semantic search. `ToolManager` handles tool registry and execution.
- **session_manager.py** — In-memory conversation history per session. Keeps last N messages (default 2 turns) for context window management.
- **config.py** — Central configuration loaded from environment. Key settings: chunk size (800), overlap (100), max results (5), max history (2).
- **models.py** — Pydantic models: `Course`, `Lesson`, `CourseChunk`.

### Frontend (`frontend/`)

Vanilla HTML/JS/CSS with a dark theme. Chat interface with sidebar showing course stats and suggested questions. Uses Marked.js for markdown rendering.

### Course Documents (`docs/`)

Plain text files with a specific format parsed by `document_processor.py`. Each file has course metadata headers followed by lesson sections.

## Key Patterns

- Claude tool-calling: The AI decides when to search the vector store via tool use, rather than always searching.
- Two-collection vector store: Metadata collection for course-level lookup, content collection for chunk-level search. Search resolves fuzzy course names against the metadata collection first.
- Session management is in-memory (no persistence across restarts).
- ChromaDB data is stored in `./chroma_db` (gitignored) and regenerated on startup from `docs/`.

## Dependencies

Python 3.13, managed with `uv`. Key packages: fastapi, uvicorn, chromadb, anthropic, sentence-transformers, python-dotenv.
