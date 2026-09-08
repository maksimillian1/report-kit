#!/usr/bin/env bash
# Brings up a local cluster with the mock API, an HPA and Prometheus.
set -euo pipefail
CLUSTER=${CLUSTER:-report-kit-example}
HERE=$(cd "$(dirname "$0")" && pwd)

kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
kubectl config use-context "kind-$CLUSTER"

# The HPA needs metrics-server, which needs --kubelet-insecure-tls on kind
# (kubelet serving certs there are self-signed).
if ! kubectl get deploy metrics-server -n kube-system >/dev/null 2>&1; then
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
  kubectl patch deploy metrics-server -n kube-system --type=json \
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi

kubectl apply -f "$HERE/manifests/"

echo "-> waiting for everything to be ready"
kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
kubectl -n report-kit-example rollout status deploy/mock-api --timeout=180s
kubectl -n report-kit-example rollout status deploy/prometheus --timeout=180s

echo
echo "ready. run:  ./point.py --run demo-r20 --rate 20 --duration 30s"
