# MV Optimization Web Dashboard

Next.js frontend for the FastAPI backend in `../api`. Replaces the Streamlit `dashboard/`.

```bash
# terminal 1 (repo root) – loopback only, the API accepts arbitrary SELECTs
docker start mv_postgres
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 2
cd web && npm install && npm run dev   # http://localhost:3000
```

`NEXT_PUBLIC_API_URL` overrides the API address (see `.env.example`).

Migration status: Query Plan viewer done; Experiments / Results / Settings are placeholders.
