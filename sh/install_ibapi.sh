#!/usr/bin/env bash
set -euo pipefail

# Optional: eigenes pip/python angeben (z.B. aus deinem venv)
PIP="${PIP:-pip3}"
PYTHON="${PYTHON:-python3}"

INSTALL_DIR="${HOME}/ibapi_latest"
ZIP="${INSTALL_DIR}/twsapi_macunix_latest.zip"

# Aktueller direkter Link: "TWS API Latest for Mac / Unix"
# (enthält die Python-API im Ordner source/pythonclient)
DEFAULT_URL="https://interactivebrokers.github.io/downloads/twsapi_macunix.1039.01.zip"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "⬇️ Lade IBKR TWS API (Mac/Unix)…"
if ! wget -O "$ZIP" "$DEFAULT_URL"; then
  echo "Standard-URL fehlgeschlagen. Versuche, die aktuelle URL zu ermitteln…"
  PAGE="$(mktemp)"
  curl -s https://interactivebrokers.github.io/ > "$PAGE"
  ALT_URL=$(grep -oE 'https://interactivebrokers.github.io/downloads/twsapi_macunix[^"]+\.zip' "$PAGE" | head -n1 || true)
  if [ -z "$ALT_URL" ]; then
    echo "Konnte keinen Link finden. Öffne https://interactivebrokers.github.io/ im Browser,"
    echo "klicke auf 'I AGREE' und lade 'TWS API Latest for Mac / Unix' herunter."
    echo "Dann rerun mit: ZIP_PATH=/pfad/zur/datei.zip $0"
    exit 1
  fi
  wget -O "$ZIP" "$ALT_URL"
fi

echo "📦 Entpacke…"
unzip -oq "$ZIP" -d "$INSTALL_DIR"

echo "🔎 Suche pythonclient…"
PYDIR=$(find "$INSTALL_DIR" -type d -name pythonclient | head -n1)
echo "Gefunden: $PYDIR"
if [ -z "$PYDIR" ]; then
  echo "❌ 'pythonclient' nicht gefunden."; exit 1
fi

echo "🧹 Entferne alte ibapi-Version (falls vorhanden)…"
$PIP uninstall -y ibapi || true

echo "🐍 Installiere ibapi aus: $PYDIR"
$PIP install "$PYDIR"

echo "✅ Fertig. Installierte ibapi-Version:"
$PIP show ibapi || true

echo "📍 Paketpfad:"
$PYTHON - <<'PY'
import ibapi, inspect
print(inspect.getfile(ibapi))
PY
