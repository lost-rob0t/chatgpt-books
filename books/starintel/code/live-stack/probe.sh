#!/usr/bin/env bash
# Sourced by the pinned upstream stack-test while its disposable stack is live.

: "${BOOK_REPO_ROOT:?BOOK_REPO_ROOT must point to chatgpt-books}"
: "${STARINTEL_SERVER_PIN:?STARINTEL_SERVER_PIN is required}"
: "${server_url:?upstream stack-test must define server_url}"
: "${api_key:?upstream stack-test must define api_key}"
: "${artifact_dir:?upstream stack-test must define artifact_dir}"
: "${port_base:?upstream stack-test must define port_base}"

golden_fixture="${BOOK_REPO_ROOT}/books/starintel/code/records/fixtures/person.json"
adapter="${BOOK_REPO_ROOT}/books/starintel/code/ingest-adapter/adapter.py"
summarizer="${BOOK_REPO_ROOT}/books/starintel/code/live-stack/summarize_trace.py"
trace_tmp="${artifact_dir}/book-service-trace-raw"
trace_out="${artifact_dir}/book-service-trace.json"

rm -rf "$trace_tmp"
mkdir -p "$trace_tmp"

make_fixture() {
  local suffix="$1"
  local destination="$2"
  python3 - "$golden_fixture" "$destination" "$suffix" "$port_base" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
suffix = sys.argv[3]
port_base = sys.argv[4]
document = json.loads(source.read_text(encoding="utf-8"))
document["_id"] = f"starintel:person:book-live-{suffix}-{port_base}"
document["data"]["bio"] = f"Synthetic service-trace fixture ({suffix}); no investigation data."
destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

run_adapter() {
  local document="$1"
  local output="$2"
  STARINTEL_URL="$server_url" STARINTEL_TOKEN="$api_key" \
    python3 "$adapter" --wait-persisted 20 --poll-interval 0.25 "$document" > "$output"
}

happy_fixture="$trace_tmp/happy.json"
fault_fixture="$trace_tmp/fault.json"
recovery_fixture="$trace_tmp/recovery.json"
make_fixture happy "$happy_fixture"
make_fixture fault "$fault_fixture"
make_fixture recovery "$recovery_fixture"

# Baseline: this is the book-controlled proof that a current valid document can
# cross HTTP -> RabbitMQ -> the ingest consumer -> CouchDB and be read back.
run_adapter "$happy_fixture" "$trace_tmp/happy-result.json"

# Fault precondition: stop only RabbitMQ and verify the container is not running.
docker compose stop rabbitmq >/dev/null
rabbitmq_container="$(docker compose ps --all --quiet rabbitmq)"
rabbitmq_running="true"
if [[ -n "$rabbitmq_container" ]] && \
   [[ "$(docker inspect --format '{{.State.Running}}' "$rabbitmq_container")" == "false" ]]; then
  rabbitmq_running="false"
fi
if [[ "$rabbitmq_running" != "false" ]]; then
  printf 'service trace: RabbitMQ fault precondition was not observed\n' >&2
  return 1
fi

http_service_alive="false"
if curl --fail --silent --show-error --header "$auth_header" \
     "${server_url}/auth/context" >/dev/null 2>&1; then
  http_service_alive="true"
fi

# Do not assume the current server's exact HTTP status while its broker is down.
# Capture the existing adapter's observation and classify it afterwards.
fault_rc=0
if STARINTEL_URL="$server_url" STARINTEL_TOKEN="$api_key" \
     python3 "$adapter" --wait-persisted 2 --poll-interval 0.25 "$fault_fixture" \
     > "$trace_tmp/fault-stdout.txt" 2> "$trace_tmp/fault-stderr.txt"; then
  fault_rc=0
else
  fault_rc=$?
fi

# Recovery is deliberately operator-driven. This experiment does not claim the
# deployment transparently reconnects without a service restart.
docker compose start rabbitmq >/dev/null
docker compose restart star-server >/dev/null
wait_for_healthy_stack
run_adapter "$recovery_fixture" "$trace_tmp/recovery-result.json"

python3 "$summarizer" \
  --server-pin "$STARINTEL_SERVER_PIN" \
  --happy "$trace_tmp/happy-result.json" \
  --fault-stdout "$trace_tmp/fault-stdout.txt" \
  --fault-stderr "$trace_tmp/fault-stderr.txt" \
  --fault-returncode "$fault_rc" \
  --recovery "$trace_tmp/recovery-result.json" \
  --rabbitmq-stopped true \
  --http-service-alive "$http_service_alive" \
  --output "$trace_out"

rm -rf "$trace_tmp"
