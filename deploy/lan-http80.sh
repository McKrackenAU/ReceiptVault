#!/usr/bin/env bash
# Root helper: listen on :80 and forward to ReceiptVault so http://<ip>/ works
# like every other helper-script CT. The app itself stays on 8082.
set -euo pipefail
PORT="${RECEIPTVAULT_LAN_PORT:-${RECEIPTVAULT_API_PORT:-8082}}"
export RV_HTTP80_TARGET="$PORT"
exec python3 - <<'PY'
import os
import socket
import threading

target = int(os.environ["RV_HTTP80_TARGET"])


def pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen.bind(("0.0.0.0", 80))
listen.listen(128)
while True:
    client, _ = listen.accept()
    try:
        upstream = socket.create_connection(("127.0.0.1", target), timeout=10)
    except OSError:
        client.close()
        continue
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
PY
