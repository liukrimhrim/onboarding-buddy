# Curriculum: Kubernetes & EKS, grounded in `infra/`

**Created:** 2026-05-18
**Status:** in_progress
**Current lesson:** 2

## Goal

After this curriculum, the user will be able to:

1. Read our Helm chart in `infra/charts/llamacloud/` and predict what Kubernetes objects (pods, services, ingresses, HPAs) it produces in a cluster.
2. Read `infra/terraform/modules/eks/` and explain at a whiteboard level what our EKS cluster is — control plane, node groups, addons (ALB controller, Karpenter, cert-manager, Linkerd, Prometheus), and how IAM connects to pods.
3. Debug a misbehaving pod in staging end-to-end: from `kubectl describe` events through logs, config, services, autoscaling, and node pressure.

Center of gravity is *reading* infra confidently, not authoring new Terraform from scratch.

## Prerequisites

- Comfort with containers, env vars, REST, basic AWS concepts (VPC, IAM at a high level).
- Has used `kubectl logs`, `kubectl describe`, `kubectl get pods` against a real cluster.
- Can read a Deployment YAML and recognize what a Pod, Service, ConfigMap, Secret is.
- Has *not* set up a cluster, never authored a Helm chart, treats Karpenter / IRSA / linkerd as black boxes.

## Lessons

- [x] 1. **The shape of `infra/` — what lives where, and why.** Guided tour: `terraform/` vs. `charts/` vs. `kubernetes/`. Generalize to the provisioning-vs-workload split.
- [ ] 2. **A pod's life — from a Deployment YAML to a running container.** Anchor: [infra/charts/llamacloud/templates/llamacloud/deployment.yaml](infra/charts/llamacloud/templates/llamacloud/deployment.yaml). Generalize to the k8s control loop and reconciliation.
- [ ] 3. **Services, ingress, and how traffic gets in.** Anchor: [service.yaml](infra/charts/llamacloud/templates/llamacloud/service.yaml), [ingress.yaml](infra/charts/llamacloud/templates/ingress.yaml), [alb.tf](infra/terraform/modules/eks/alb.tf). Generalize to L4 Service vs. L7 Ingress and cloud LB controllers.
- [ ] 4. **EKS = managed k8s + AWS glue.** Anchor: [infra/terraform/modules/eks/main.tf](infra/terraform/modules/eks/main.tf) and its sibling addon files. Generalize to control plane vs. data plane, IRSA.
- [ ] 5. **Autoscaling: HPA (pods) and Karpenter (nodes).** Anchor: [hpa.yaml](infra/charts/llamacloud/templates/llamacloud/hpa.yaml), [karpenter-llamadeploy-nodepool.yaml](infra/terraform/environments/staging/karpenter-llamadeploy-nodepool.yaml). Generalize to two-tier autoscaling; compare Karpenter vs. cluster-autoscaler.
- [ ] 6. **Debugging a sick pod in staging.** Synthesis lesson — walk a hypothetical CrashLoopBackOff through the diagnostic tree, using everything from lessons 1–5.

## Notes from sessions

### Lesson 1 (2026-05-18)

- User came in knowing kubectl-level basics; this lesson was mostly about orienting on file layout, not new concepts.
- Confirmed mental model: terraform = "what AWS provisions", charts = "what gets deployed into the cluster", kubernetes/ = "operational tooling for the running cluster".
- User asked a useful side-question: why is `karpenter-llamadeploy-nodepool.yaml` under `terraform/environments/staging/` and not under `charts/`? Answer (worth revisiting in lesson 5): Karpenter NodePool CRs are co-located with the Terraform that bootstraps Karpenter itself, because the NodePool's `nodeClassRef` points at an `EC2NodeClass` whose IAM/subnet/AMI wiring is created by Terraform — keeping them adjacent reduces drift between the IAM role and the NodePool that uses it.
- Follow-up to revisit later: relationship between per-env Terraform under `terraform/environments/<env>/` and per-env Helm values under `charts/environments/<env>/`. Different envs, same shape — user wants to understand the boundary.
