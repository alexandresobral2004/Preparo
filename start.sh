#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
UVICORN_BIN="$BACKEND_DIR/.venv/bin/uvicorn"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
MODE="dev"

usage() {
  cat <<EOF
Uso: ./start.sh [opção]

Sobe o Preparo de Vegetal v2 (Backend FastAPI + SQLite e Frontend React + Vite).

Opções:
  (padrão)   Modo desenvolvimento: sobe os 2 serviços com hot-reload
             - Backend (FastAPI + SQLite): http://localhost:${BACKEND_PORT}
             - Frontend (React + Vite):    http://localhost:${FRONTEND_PORT}
  --prod     Faz o build do frontend e sobe em porta única (${BACKEND_PORT})
  -h, --help Mostra esta ajuda
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prod)
      MODE="prod"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

check_prereqs() {
  if [[ ! -x "$UVICORN_BIN" ]]; then
    echo "Erro: ambiente Python não encontrado em $UVICORN_BIN." >&2
    echo "Crie o venv e instale as dependências do backend antes de iniciar." >&2
    exit 1
  fi
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "Erro: pnpm não encontrado no PATH." >&2
    exit 1
  fi
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "Erro: dependências do frontend não instaladas ($FRONTEND_DIR/node_modules ausente)." >&2
    echo "Execute: pnpm --dir frontend install" >&2
    exit 1
  fi
}

is_port_busy() {
  local port="$1"
  if [[ -x "$PYTHON_BIN" ]]; then
    if "$PYTHON_BIN" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
busy = False
for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(0.15)
            if s.connect_ex((host, port)) == 0:
                busy = True
                break
    except OSError:
        pass
sys.exit(0 if busy else 1)
PY
    then
      return 0
    fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      return 0
    fi
  fi
  return 1
}

pick_free_port() {
  local desired="$1"
  local label="$2"
  local port="$desired"
  local attempts=0

  while is_port_busy "$port"; do
    if [[ "$attempts" -eq 0 ]]; then
      echo "Aviso: porta ${port} (${label}) já está ocupada por outro serviço; buscando próxima porta livre..." >&2
    fi
    port=$((port + 1))
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge 50 ]]; then
      echo "Erro: nenhuma porta livre encontrada a partir de ${desired} para ${label}." >&2
      exit 1
    fi
  done

  if [[ "$port" -ne "$desired" ]]; then
    echo "-> ${label} ajustado automaticamente para a porta ${port}." >&2
  fi
  echo "$port"
}

detect_local_ip() {
  local ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  echo "$ip"
}

BACK_PID=""
FRONT_PID=""

kill_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  if command -v pgrep >/dev/null 2>&1; then
    local child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
      kill_tree "$child" "$sig"
    done
  fi
  kill "-$sig" "$pid" 2>/dev/null || true
}

cleanup() {
  local exit_code=$?
  trap - INT TERM EXIT
  kill_tree "$FRONT_PID" TERM
  kill_tree "$BACK_PID" TERM
  wait "$FRONT_PID" 2>/dev/null || true
  wait "$BACK_PID" 2>/dev/null || true
  exit "$exit_code"
}

check_prereqs
LOCAL_IP="$(detect_local_ip)"

if [[ "$MODE" == "prod" ]]; then
  BACKEND_PORT="$(pick_free_port "$BACKEND_PORT" "Backend + PWA")"
  echo "Gerando build de produção do frontend React..."
  pnpm --dir "$FRONTEND_DIR" build

  echo ""
  echo "=========================================="
  echo " Preparo de Vegetal v2 (Produção)"
  echo " Local:   http://localhost:${BACKEND_PORT}"
  if [[ -n "$LOCAL_IP" ]]; then
    echo " Celular: http://${LOCAL_IP}:${BACKEND_PORT}"
  fi
  echo " API Doc: http://localhost:${BACKEND_PORT}/docs"
  echo " Pressione Ctrl+C para encerrar."
  echo "=========================================="
  echo ""

  trap cleanup INT TERM EXIT
  "$UVICORN_BIN" app.main:app \
    --app-dir "$BACKEND_DIR" \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" &
  BACK_PID=$!
  wait "$BACK_PID"
  exit 0
fi

BACKEND_PORT="$(pick_free_port "$BACKEND_PORT" "Backend FastAPI")"
FRONTEND_PORT="$(pick_free_port "$FRONTEND_PORT" "Frontend Vite")"

echo "Iniciando backend FastAPI + SQLite na porta ${BACKEND_PORT}..."
trap cleanup INT TERM EXIT
"$UVICORN_BIN" app.main:app \
  --app-dir "$BACKEND_DIR" \
  --reload \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" &
BACK_PID=$!

echo "Iniciando frontend React (Vite) na porta ${FRONTEND_PORT}..."
BACKEND_PORT="$BACKEND_PORT" pnpm --dir "$FRONTEND_DIR" dev --host 0.0.0.0 --port "$FRONTEND_PORT" &
FRONT_PID=$!

echo ""
echo "=========================================="
echo " Preparo de Vegetal v2 (Desenvolvimento)"
echo " App:     http://localhost:${FRONTEND_PORT}"
if [[ -n "$LOCAL_IP" ]]; then
  echo " Celular: http://${LOCAL_IP}:${FRONTEND_PORT}"
fi
echo " Backend: http://localhost:${BACKEND_PORT}"
echo " API Doc: http://localhost:${BACKEND_PORT}/docs"
echo " Pressione Ctrl+C para encerrar ambos os serviços."
echo "=========================================="
echo ""

# Aguarda ambos os processos; se um cair, o trap encerra o outro
while kill -0 "$BACK_PID" 2>/dev/null && kill -0 "$FRONT_PID" 2>/dev/null; do
  sleep 1
done
wait "$BACK_PID" 2>/dev/null || wait "$FRONT_PID" 2>/dev/null || true
