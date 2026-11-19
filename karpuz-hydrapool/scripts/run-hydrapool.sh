#!/bin/sh
# Start Hydrapool after the dashboard writes config.toml, and restart it
# when that file changes. The published image's default config is never used:
# it donates the whole block and pins an address the operator did not choose.
set -u

CONFIG=/data/config/config.toml
mkdir -p /data/hydrapool/stats /data/config /data/logs

pid=""

stop_pool() {
  if [ -n "${pid}" ]; then
    kill "${pid}" 2>/dev/null || true
    i=0
    while kill -0 "${pid}" 2>/dev/null && [ "${i}" -lt 25 ]; do
      i=$((i + 1))
      sleep 1
    done
    kill -9 "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  fi
  pid=""
}

trap 'stop_pool; exit 0' TERM INT

echo "Hydrapool supervisor waiting for setup"

while true; do
  if [ ! -s "${CONFIG}" ]; then
    sleep 2
    continue
  fi

  mtime=$(stat -c %Y "${CONFIG}" 2>/dev/null || echo 0)
  alive=0
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    alive=1
  fi

  if [ "${alive}" -eq 1 ] && [ "${mtime}" = "${seen:-}" ]; then
    sleep 2
    continue
  fi

  if [ "${alive}" -eq 1 ]; then
    echo "Hydrapool config changed; restarting"
    stop_pool
  elif [ -n "${pid}" ]; then
    echo "Hydrapool exited; restarting in 5s"
    pid=""
    sleep 5
    continue
  else
    echo "Starting Hydrapool"
  fi

  /usr/local/bin/hydrapool --config "${CONFIG}" &
  pid=$!
  seen=${mtime}
  sleep 2
done

# restart: on-failure does not revive an exit 0. Stay up if this loop ends.
echo "Hydrapool supervisor left its wait loop; idling"
while true; do
  sleep 3600
done
