# api/

Charles Core API — FastAPI backend running in Docker.

## What goes here

- `main.py` — FastAPI app entry point
- `openrouter.py` — OpenRouter API client (`qwen/qwen3-next-80b-a3b-instruct:free`)
- `database.py` — PostgreSQL connection + query helpers
- `mcp_client.py` — MCP protocol client (connects to MCP servers, calls tools)
- `Dockerfile` — Image definition (`python:3.11-slim`)
- `requirements.txt` — API service Python dependencies

## Endpoints (planned)

| Method | Path                         | Description                                       |
| ------ | ---------------------------- | ------------------------------------------------- |
| GET    | `/health`                    | Health check                                      |
| POST   | `/chat`                      | Send message, get response (stores in PostgreSQL) |
| GET    | `/history/{conversation_id}` | Fetch conversation history                        |
| DELETE | `/history/{conversation_id}` | Clear conversation history                        |

## Environment variables

| Variable             | Description                  |
| -------------------- | ---------------------------- |
| `OPENROUTER_API_KEY` | OpenRouter API key           |
| `DATABASE_URL`       | PostgreSQL connection string |

## Run locally (via Docker Compose)

```bash
docker-compose up charles-api
```
