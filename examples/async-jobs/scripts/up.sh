#!/usr/bin/env bash
# Brings up a local cluster with a queue, a worker pool that scales to zero,
# a shared tier that does not, and Prometheus watching all three.
set -euo pipefail
CLUSTER=${CLUSTER:-report-kit-jobs}
NS=report-kit-jobs
HERE=$(cd "$(dirname "$0")" && pwd)

kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER"
kubectl config use-context "kind-$CLUSTER"

# The results HPA needs metrics-server, which needs --kubelet-insecure-tls on
# kind (kubelet serving certs there are self-signed).
if ! kubectl get deploy metrics-server -n kube-system >/dev/null 2>&1; then
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
  kubectl patch deploy metrics-server -n kube-system --type=json \
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi

# KEDA is what lets the worker pool reach zero. An HPA cannot: its floor is 1,
# and "one worker still running" is not the close condition this profile is
# about.
if ! kubectl get deploy keda-operator -n keda >/dev/null 2>&1; then
  helm repo add kedacore https://kedacore.github.io/charts >/dev/null
  helm repo update kedacore >/dev/null
  helm install keda kedacore/keda --namespace keda --create-namespace --version 2.16.1 --wait
fi

kubectl apply -f "$HERE/manifests/00-namespace.yaml"

# The pods run the files in cluster/, plus resp.py from this directory — the
# same file the host-side scripts import, rather than a second copy that can
# drift. Rebuilt on every up.sh so an edit reaches the cluster.
kubectl create configmap jobs-src -n "$NS" \
  --from-file="$HERE/resp.py" \
  --from-file="$HERE/cluster/worker.py" \
  --from-file="$HERE/cluster/exporter.py" \
  --from-file="$HERE/cluster/results.py" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "$HERE/manifests/"
kubectl apply -f "$HERE/keda/"

echo "-> waiting for everything to be ready"
kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
kubectl -n "$NS" rollout status deploy/redis --timeout=180s
kubectl -n "$NS" rollout status deploy/queue-exporter --timeout=180s
kubectl -n "$NS" rollout status deploy/results --timeout=180s
kubectl -n "$NS" rollout status deploy/prometheus --timeout=180s

echo
echo "ready. run:  ./point.py --run demo --n 2 --count 200"
