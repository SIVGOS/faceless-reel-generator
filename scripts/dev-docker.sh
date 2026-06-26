#!/usr/bin/env bash
#
# dev-docker.sh — pin local Docker to a NATIVE arm64 Colima engine.
#
# Why: on this Apple Silicon machine the default Colima profile runs EMULATED
# x86_64, which makes the MoviePy caption render unusably slow (a 53s reel took
# 30+ min and never finished). A native arm64 profile renders the same reel in
# ~150s. This script stops any running emulated-x86 Colima profile and brings up
# (or reuses) the native arm64 one, then points the docker CLI at it.
#
# It is idempotent — safe to run every time before `docker build` / `docker
# compose` / the render benchmark. It does NOT delete the x86 `default` profile
# (that holds other projects' containers); it only stops it while running.
#
# Usage:  ./scripts/dev-docker.sh
# Override:  ARM_PROFILE=arm ARM_CPU=4 ARM_MEM=8 ./scripts/dev-docker.sh
set -euo pipefail

ARM_PROFILE="${ARM_PROFILE:-arm}"
ARM_CPU="${ARM_CPU:-4}"      # match the deploy target's vCPU count
ARM_MEM="${ARM_MEM:-8}"      # GiB

if ! command -v colima >/dev/null 2>&1; then
  echo "error: colima not found. This script targets the local Apple-Silicon dev box." >&2
  echo "       On a native Linux host (incl. the deploy server) just use docker directly." >&2
  exit 1
fi

# 1. Stop any RUNNING emulated x86_64 Colima profile (cols: PROFILE STATUS ARCH ...).
colima list 2>/dev/null | awk 'NR>1 && $2=="Running" && $3=="x86_64" {print $1}' \
  | while read -r p; do
      echo "→ stopping emulated x86_64 Colima profile: $p"
      colima stop --profile "$p"
    done

# 2. Ensure the native arm64 profile is up.
if colima list 2>/dev/null | awk -v p="$ARM_PROFILE" 'NR>1 && $1==p && $2=="Running"{f=1} END{exit !f}'; then
  echo "→ native arm64 Colima ('$ARM_PROFILE') already running"
else
  echo "→ starting native arm64 Colima ('$ARM_PROFILE', ${ARM_CPU} cpu / ${ARM_MEM} GiB)…"
  colima start --profile "$ARM_PROFILE" --arch aarch64 --cpu "$ARM_CPU" --memory "$ARM_MEM"
fi

# 3. Point the docker CLI at it.
docker context use "colima-${ARM_PROFILE}" >/dev/null

echo -n "✓ docker engine: "
docker info --format '{{.OSType}}/{{.Architecture}} · {{.NCPU}} cpu' 2>/dev/null
echo "  (context: $(docker context show))"
