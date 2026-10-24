#!/usr/bin/env bash
# Removes what up.sh applied, and the nodepool label it put on every node.
set -euo pipefail
kubectl delete namespace report-kit-priced report-kit-priced-monitoring --ignore-not-found
kubectl delete clusterrole,clusterrolebinding --ignore-not-found \
  report-kit-priced-prometheus report-kit-priced-kube-state-metrics report-kit-priced-opencost
kubectl label nodes --all karpenter.sh/nodepool-
