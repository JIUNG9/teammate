# teammate-chat-web — Standalone web UI

Next.js 14 (App Router, RSC, TypeScript, Tailwind). Talks to:

- `teammate-chat-api` for `/api/chat/*` (chat, search, feed, index-status, reindex)
- `teammate-war-api` for `/api/war/*` (incidents, SSE, slash commands)

## Local dev

```bash
cd examples/web-app
npm install
# Point at the cluster (or port-forward both services):
TEAMMATE_CHAT_API_URL=http://localhost:8000 \
TEAMMATE_WAR_API_URL=http://localhost:8001 \
  npm run dev
# Open http://localhost:3000
```

## Build + deploy

```bash
docker build -t your-registry/teammate-chat-web:latest .
docker push your-registry/teammate-chat-web:latest
```

Apply the k8s manifest in `examples/k8s/chat-web/deployment.yaml` (referenced by gitops).

## Pages

| Path | Purpose |
|---|---|
| `/` | Chat (streaming SSE, citation badges, per-source confidence) |
| `/watch` | MTTD watchlist + similarity search blurb (real UI ships in v2) |
| `/war` | List of incidents by state (triage / open / active / resolved) |
| `/war/[id]` | War-room detail with SSE timeline + 7 panels + chat |
| `/feed` | Recent triggered K8s Jobs |
| `/index-status` | Qdrant collection stats + Rebuild button |
| `/settings` | Per-source weights + score floor (localStorage) |

## Auth

The app expects an SSO proxy (oauth2-proxy) in front of the Ingress. It trusts the
`X-Forwarded-User` header for display name. No client-side auth.
