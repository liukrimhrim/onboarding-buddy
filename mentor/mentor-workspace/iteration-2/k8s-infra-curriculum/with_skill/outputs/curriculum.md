# Curriculum: Kubernetes & EKS — from `infra/` outward

**Status:** in_progress
**Current lesson:** 1

## Goal
You can read this repo's `infra/` directory and explain what each piece is doing, debug a misbehaving cluster (scaling stuck, pods pending, IAM denied), and make a focused PR — either a Terraform change to the cluster or a Helm change to a workload. You also leave with a transferable model of how EKS clusters are built and operated, not just this one.

## Prerequisites
Pods, Deployments, Services, namespaces. You can `kubectl get pods` and read a Deployment YAML. You do **not** need prior Terraform, Helm, Karpenter, KEDA, or IRSA experience — we'll build those up.

## Lessons
- [ ] 1. **The shape of `infra/` and the provisioning-vs-workload split** — why Terraform and Helm are two separate worlds, what each owns, and where the seam is. Lands the mental model that runs through every later lesson.
- [ ] 2. **What the EKS module actually builds** — walk `infra/terraform/modules/eks/` and see an EKS cluster as ~5 concrete AWS resources plus a handful of in-cluster controllers. Generalize to the EKS control plane vs. data plane.
- [ ] 3. **Node autoscaling with Karpenter** — read `karpenter.tf` + a NodePool, trace a Pending pod to new EC2 instance. Generalize to cluster autoscaling tradeoffs (Karpenter vs. Cluster Autoscaler vs. managed node groups).
- [ ] 4. **IRSA: how pods get AWS permissions without secrets** — read the OIDC provider + a role trust policy (e.g., `keda_operator`), trace the token exchange. Generalize to workload identity (GKE WI, Azure WI, SPIFFE).
- [ ] 5. **Workload autoscaling with KEDA** — read `keda.tf` and `llamaparse-ocr/keda-scaledobject.yaml`, follow a queue-depth metric to a replica change. Compare to HPA, contrast push vs. pull metrics.
- [ ] 6. **The Helm chart and the rollout path** — `infra/charts/llamacloud/` structure, how `values.yaml` + templates produce the running cluster state, and how a deploy actually flows (CI to ArgoCD/helm to rolling update). Generalize to GitOps and declarative config.

<!-- Mentor scratchpad — not user-facing. -->
## Mentor scratchpad
- user knows pods/Deployments/Services; assume that floor
- jargon tolerance: high — define Karpenter/IRSA/KEDA inline first use only
- user has shipped to but not operated the cluster — bias toward "what would I see when this breaks"
