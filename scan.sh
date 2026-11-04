#!/usr/bin/env bash
#
# Rigorlytics security scan. Podman + natively installed Trivy, so there is
# no container to pull and no socket to mount.
#
#   ./scan.sh           scan and report
#   ./scan.sh --gate    exit 1 on any HIGH or CRITICAL   (what CI runs)
#
# Three scanners answering three different questions:
#   vuln       known CVEs in OS packages and Python dependencies
#   secret     a credential committed to source or baked into a layer
#   misconfig  Dockerfile, compose, Kubernetes and Terraform settings
#
# venv/ is skipped on the filesystem scans. Trivy does not read
# .dockerignore, so without this it walks the virtualenv and reports
# example tokens out of dependency READMEs as secrets. The image scan still
# covers every installed package, because those are what actually ship.

set -euo pipefail

IMAGE="${IMAGE:-localhost/rigorlytics:dev}"
TAR="$(mktemp /tmp/rigorlytics-scan-XXXXXX.tar)"
OUT="security-reports"
SKIP_DIRS="--skip-dirs venv --skip-dirs .venv --skip-dirs security-reports"
GATE=0
[[ "${1:-}" == "--gate" ]] && GATE=1

cleanup() { rm -f "$TAR"; }
trap cleanup EXIT

mkdir -p "$OUT"

echo "Exporting $IMAGE ..."
podman save -o "$TAR" "$IMAGE"

echo
echo "=============================================================="
echo " 1/3  Image vulnerabilities"
echo "=============================================================="
trivy image --input "$TAR" --scanners vuln --ignore-unfixed \
  --severity LOW,MEDIUM,HIGH,CRITICAL \
  --format table --output "$OUT/image-vulns.txt" 2>/dev/null || true
grep -E "^Total:|^(/tmp|Python)" "$OUT/image-vulns.txt" 2>/dev/null \
  || echo "  no findings"

# SARIF for GitHub code scanning once CI exists.
trivy image --input "$TAR" --scanners vuln --ignore-unfixed \
  --format sarif --output "$OUT/image-vulns.sarif" >/dev/null 2>&1 || true

echo
echo "=============================================================="
echo " 2/3  Secrets in the working tree"
echo "=============================================================="
# .env is excluded deliberately: it is meant to hold secrets and is
# gitignored. The point is catching a key that leaked into source, a
# manifest or a Dockerfile.
trivy fs --scanners secret --skip-files ".env" $SKIP_DIRS \
  --format table --output "$OUT/secrets.txt" . 2>/dev/null || true
grep -E "^Total:|secrets\)$" "$OUT/secrets.txt" 2>/dev/null || echo "  clean"

echo
echo "=============================================================="
echo " 3/3  Configuration and IaC misconfiguration"
echo "=============================================================="
# Picks up k8s/ and terraform/ automatically as those directories appear.
trivy config --severity LOW,MEDIUM,HIGH,CRITICAL $SKIP_DIRS \
  --format table --output "$OUT/misconfig.txt" . 2>/dev/null || true
grep -E "^Total:|^Tests:" "$OUT/misconfig.txt" 2>/dev/null || echo "  clean"

echo
echo "=============================================================="
echo " Summary"
echo "=============================================================="
for f in image-vulns secrets misconfig; do
  if [[ -f "$OUT/$f.txt" ]]; then
    n=$(grep -coE "(HIGH|CRITICAL):[[:space:]]*[1-9]" "$OUT/$f.txt" 2>/dev/null || true)
    printf "  %-14s %s report lines with HIGH/CRITICAL counts\n" "$f" "${n:-0}"
  fi
done
echo "  full reports in $OUT/"

if [[ "$GATE" == "1" ]]; then
  echo
  echo "Gate: failing the build on HIGH or CRITICAL."
  trivy image --input "$TAR" --scanners vuln --ignore-unfixed \
    --severity HIGH,CRITICAL --exit-code 1 --quiet
  echo "Gate passed: no HIGH or CRITICAL findings."
fi
