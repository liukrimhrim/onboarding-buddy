Good — no existing curriculum, and I now have a concrete picture of what's actually in `infra/`: a substantial EKS Terraform module with cluster, IAM, Karpenter, KEDA, Traefik, ALB, Linkerd, NVIDIA, Prometheus, cert-manager; per-environment Terraform stacks; a Helm umbrella chart with Temporal/Bifrost/Prometheus subcharts and per-env values overlays; and a Python `k8sctl` deployment CLI.

Before I lock in a 12-lesson plan, two quick intake questions so the curriculum fits you:

**Q1. Goal — which outcome do you most want?**
- (a) Be able to *debug* prod K8s issues confidently (read Karpenter/KEDA events, trace pod-not-scheduling, decode Helm rollout failures).
- (b) Be able to *modify* our infra (add a new service, write a HelmRelease/values overlay, add a new env, tune a NodePool).
- (c) Conceptual fluency — be the person who can explain how EKS/K8s actually work to a new hire and reason about tradeoffs.

**Q2. Starting point** — which of these would feel like wasted time?
- Pods / Deployments / Services / Ingress basics
- Helm templating mental model (values → manifests → release)
- Terraform module pattern (providers, modules, state)
- IAM / IRSA / Pod Identity

(Pick any that are already solid for you.)

While you answer, here's the curriculum I'd draft based on what's in the repo — feel free to push back:

---

**Proposed curriculum: `k8s-eks-llamacloud.md`** (7 lessons, ~45 min each)

1. **The map: how a request reaches a pod in our cluster.** Walk Route53 → ALB → Traefik → Service → Pod using `infra/terraform/modules/eks/{alb,traefik,dns}.tf` and `infra/charts/llamacloud/templates/ingress.yaml`. Concept: K8s networking layers (Service, Ingress, LB). Comparison: ALB Ingress vs Traefik vs service mesh (Linkerd).
2. **EKS control plane and node identity.** `terraform/modules/eks/main.tf` — cluster resource, KMS, OIDC, `authentication_mode = API_AND_CONFIG_MAP`. Concept: managed control plane vs self-managed, IRSA vs Pod Identity, kubeconfig auth flow.
3. **Where pods actually run: Karpenter.** `eks/karpenter.tf` + `environments/staging/karpenter-llamadeploy-{ec2nodeclass,nodepool}.yaml`. Concept: NodePool/EC2NodeClass, bin-packing, consolidation, taints/tolerations, spot. Comparison: Karpenter vs Cluster Autoscaler vs managed node groups.
4. **Autoscaling pods: KEDA + HPA.** `eks/keda.tf` and KEDA `ScaledObject`s in the chart for parse/extract workers. Concept: HPA's metric loop, KEDA scalers (RabbitMQ, SQS, Prometheus), scale-to-zero. Tie back to the parse queue.
5. **The Helm umbrella chart.** `charts/llamacloud/Chart.yaml` (Temporal/Bifrost/Prometheus subcharts) + `templates/` + `values.yaml` + `environments/<env>/values.yaml` overlay pattern. Concept: Helm templating, dependencies, release lifecycle, schema validation. Comparison: Helm vs Kustomize vs raw manifests; how ArgoCD consumes this.
6. **Per-environment topology.** Compare `terraform/environments/{staging,prod,prod-eu,8am,opg,new-york-life}/main.tf` and the matching `charts/environments/*`. Concept: multi-tenant SaaS vs single-tenant BYOC, account-per-tenant, the `tenant` module. Comparison: namespace isolation vs cluster isolation vs account isolation.
7. **Day-2: ArgoCD + `k8sctl` + observability.** `infra/kubernetes/k8sctl` CLI, `eks/prometheus.tf`, Loki module, ArgoCD flow from `kubernetes/README.md`. Concept: GitOps, pull vs push deploy, the observability triangle (metrics/logs/traces). Tie to the SRE skills you already use.

---

Tell me your Q1/Q2 answers (or just say "looks good, run lesson 1") and I'll write the file and start.

---
**[Note: Baseline stopped here without running lesson 1, waiting for user confirmation. No file was saved to disk.]**
