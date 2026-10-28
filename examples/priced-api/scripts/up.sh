#!/usr/bin/env bash
# Brings up the priced example on the cluster kubectl points at: the mock API
# with a volume and a load balancer, Prometheus, kube-state-metrics and
# OpenCost. It creates no cluster — README.md says which one the committed
# runs used, and why not kind.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NS=report-kit-priced
MONITORING=report-kit-priced-monitoring
POOL=${POOL:-apps}

echo "-> context: $(kubectl config current-context)"

# The label Karpenter puts on every node it launches, applied by hand: a local
# cluster has no Karpenter, and the register sums one pool's nodes by it.
kubectl label nodes --all "karpenter.sh/nodepool=$POOL" --overwrite

# The HPA needs metrics-server. k3s ships one; kind needs it installed, with
# --kubelet-insecure-tls since kubelet serving certs there are self-signed.
if ! kubectl get deploy metrics-server -n kube-system >/dev/null 2>&1; then
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
  kubectl patch deploy metrics-server -n kube-system --type=json \
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi

kubectl apply -f "$HERE/manifests/namespace.yaml"
kubectl apply -f "$HERE/manifests/"

# The same images from somewhere else, for a machine that cannot reach
# ghcr.io or registry.k8s.io — the committed runs needed both.
if [ -n "${OPENCOST_IMAGE:-}" ]; then
  kubectl -n "$MONITORING" set image deploy/opencost opencost="$OPENCOST_IMAGE"
fi
if [ -n "${KSM_IMAGE:-}" ]; then
  kubectl -n "$MONITORING" set image deploy/kube-state-metrics kube-state-metrics="$KSM_IMAGE"
fi

echo "-> waiting for everything to be ready"
kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
kubectl -n "$NS" rollout status deploy/mock-api --timeout=300s
for deploy in prometheus kube-state-metrics opencost; do
  kubectl -n "$MONITORING" rollout status "deploy/$deploy" --timeout=300s
done

echo
echo "ready. OpenCost publishes its first prices about two minutes after it"
echo "starts; ./api_point.py --preflight-only --run x --rate 8 says when."
