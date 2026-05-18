# Lesson 1 — The shape of `infra/` and the provisioning-vs-workload split

## Goal
By the end of this lesson you can look at any file under `infra/` and immediately answer two questions: **who applies this, and what does it manage?** And you can explain, without hand-waving, why a chart change can ship in 5 minutes but a Karpenter change ships through Terraform — i.e., where the seam between provisioning and workloads sits, and why the cluster is designed around that seam.

This is the load-bearing concept for the whole curriculum. Lessons 2–6 are all on one side of this seam or the other.

---

## Concept map (read this *before* opening any file)

There are two completely different control loops running against this platform, and `infra/` is split along that line:

```
                   +--------------------------------------------+
                   |          AWS account (per env)             |
                   |                                            |
   Terraform  -->  |  VPC, subnets, IAM, EKS control plane,     |
   (slow loop)     |  RDS, DocumentDB, S3, KMS, OIDC provider,  |
                   |  Karpenter controller, KEDA operator,      |
                   |  Traefik ingress, cert-manager, Loki...    |
                   |                                            |
                   |   == the cluster itself + its plumbing ==  |
                   |                                            |
                   |  +--------------------------------------+  |
                   |  |        EKS cluster (k8s API)         |  |
                   |  |                                      |  |
                   |  |   Helm  -->  llamacloud-api Deploys, |  |
                   |  |   (fast loop)  llamaparse, OCR,      |  |
                   |  |                jobs, temporal,       |  |
                   |  |                ConfigMaps, Secrets,  |  |
                   |  |                ScaledObjects, HPAs   |  |
                   |  |                                      |  |
                   |  |   == the workloads that run on it == |  |
                   |  +--------------------------------------+  |
                   +--------------------------------------------+
```

Two control loops, two tools, two cadences:

| Axis            | Terraform side (`infra/terraform/`)                 | Helm side (`infra/charts/`)                              |
|-----------------|------------------------------------------------------|-----------------------------------------------------------|
| What it owns    | AWS resources + the cluster's *system* add-ons       | Application Deployments + their config                    |
| API it talks to | AWS API (via `aws.member_account` provider)          | Kubernetes API (kubectl/helm/argo)                        |
| State store     | `s3://llamacloud-terraform-state/...`                | etcd inside the EKS cluster                               |
| Cadence         | Minutes-to-hours; gated; rare                        | Seconds-to-minutes; every PR merge                        |
| Failure blast   | Can break the *cluster*                              | Breaks *a service*; cluster still up                      |
| Who runs it     | Platform engineers, manually or via TF Cloud         | CI + ArgoCD on merge                                      |

**The key insight:** these are not just two folders. They are two layers of a stack, and the line between them is the EKS cluster's API. Terraform's job ends roughly when the cluster API is up and the *controllers that watch the cluster* (Karpenter, KEDA, cert-manager, Traefik) are installed. Helm's job starts there — it talks to the cluster API and creates the Kubernetes objects that those controllers then act on.

Why this matters for you:

- **When something is broken, the seam tells you where to look.** A pod stuck Pending with no node? That's Karpenter — Terraform side. A pod CrashLooping with a bad env var? That's a Deployment — Helm side. A 503 at the ingress? Could be either (Traefik is Terraform-installed, but the upstream Service is Helm-installed) — and now you know to check both.
- **When you change something, the seam tells you the cost.** Adding a CPU limit to a container: Helm PR, deploys in minutes. Adding a new node pool for GPU workloads: Terraform PR, requires apply, can affect other tenants of the cluster.
- **It explains why some "Kubernetes config" lives in `.tf` files.** When you see `keda.tf` and wonder "wait, KEDA is a Kubernetes thing, why is it in Terraform?" — it's because KEDA the *operator* is part of the cluster's plumbing (installed once, watches the cluster), while KEDA `ScaledObject` resources (one per workload) are application config and live in Helm. Same pattern for cert-manager, Traefik, Karpenter.

Hold that picture in your head, then we'll drop into the files.

---

## Ground: walk the directories with the map in hand

`infra/` has six top-level directories. Three are load-bearing for this lesson; three are sidecars you should be able to dismiss.

**Load-bearing:**

1. [`infra/terraform/`](infra/terraform/) — the slow loop. Two subdirectories matter:
   - `modules/` — reusable building blocks (`eks/`, `aurora-postgresql/`, `documentdb/`, `elasticache/`, `networking/`, `loki/`, `tenant/`, ...). Each module is a logical "thing you can build one or more of."
   - `environments/` — per-env compositions: `prod/`, `staging/`, `prod-eu/`, `dev/`, and single-tenant envs (`8am/`, `new-york-life/`, `opg/`). Each is a tiny Terraform root that wires modules together with environment-specific values.

2. [`infra/charts/`](infra/charts/) — the fast loop. Each subdirectory is a Helm chart:
   - `llamacloud/` — the big one. Defines the API, parse workers, OCR, jobs, temporal workers, etc.
   - `llamacloud-models/` — model-serving workloads (OCR, layout detection) that are scaled differently and often on different node pools.
   - `llamacloud-external-services/` — third-party services run in-cluster (e.g., dependencies the platform needs).
   - `llamacloud-saas/` — SaaS-specific overlay on top of `llamacloud`.
   - `environments/` — per-env *values files* (the inputs to `helm install`).

3. [`infra/kubernetes/`](infra/kubernetes/) — operator tooling and manual one-off manifests. Has `k8sctl` (a CLI to connect to clusters across envs), `manual/` (rarely-applied manifests), and helper scripts. **It does not own a control loop** — it's where humans go when they need to talk to the cluster by hand.

**Sidecars (don't get distracted):**

- `infra/scripts/` — shell scripts for operators.
- `infra/tools/` — engineer tooling.
- `infra/terraform-posthog/` — separate stack for PostHog only; orthogonal.

### One file from each side, to make the seam concrete

Let's look at the cleanest example of each side.

**Terraform side — installing the KEDA operator** ([infra/terraform/modules/eks/keda.tf](infra/terraform/modules/eks/keda.tf)). The first 50 lines do these things, in order:

1. Create a Kubernetes namespace called `keda` (yes, Terraform can create k8s objects — it's using the `kubernetes` provider against the cluster it just built).
2. Create an IAM role `<cluster>-keda-operator-role` whose trust policy says "this role can be assumed via web identity by the `keda-operator` service account in the `keda` namespace." (That's IRSA — lesson 4.)
3. Attach a policy that lets that role query AWS Managed Prometheus.

This file runs **once per cluster**. It doesn't know anything about which workloads will autoscale. It only sets up the *capability* for workloads to autoscale.

**Helm side — using the KEDA operator** ([infra/charts/llamacloud-models/templates/llamaparse-ocr/keda-scaledobject.yaml](infra/charts/llamacloud-models/templates/llamaparse-ocr/keda-scaledobject.yaml)). The whole template is ~40 lines and does one thing: create a `ScaledObject` custom resource that points at the OCR Deployment and supplies `triggers` (queue depth, latency, etc.) from `values.yaml`.

This file (well, this *rendering* of the template) runs **once per workload that wants to autoscale**. It assumes KEDA the operator already exists in the cluster. If it didn't, this manifest would apply but nothing would happen — `ScaledObject` is a CRD installed by the operator. No operator, no CRD, `helm install` fails with "no matches for kind ScaledObject."

That's the seam. Notice it's not "Terraform owns AWS, Helm owns k8s" — Terraform also creates *some* k8s objects (the operator install). The honest line is **"Terraform owns things that are installed once per cluster; Helm owns things that exist per workload."**

### How the environments wire it together

Open [infra/terraform/environments/prod/main.tf](infra/terraform/environments/prod/main.tf:261) and look at the `module "eks"` block (line 261). It's a couple hundred lines of *configuration*, not resources. It says "for prod, use these subnets, these hostnames, enable Loki, enable the LlamaDeploy nodepool, sample traces at 1%." The actual resources are inside `modules/eks/`.

That same pattern repeats for every environment. The module is the recipe; the environment is the order ticket.

---

## Generalize: what's the broader pattern?

You're looking at a textbook **two-tier infrastructure split**, and it shows up in nearly every serious EKS shop:

- **Tier 1 (slow, foundational)**: cloud provider resources + cluster bootstrap. Tooling: Terraform, Pulumi, CDK, or eksctl. Outputs a working cluster with the operators you need (ingress, cert manager, autoscalers, observability).
- **Tier 2 (fast, app-level)**: Kubernetes objects for application workloads. Tooling: Helm, Kustomize, plain YAML + ArgoCD/Flux.

The seam isn't accidental. There are three forces pushing toward it:

1. **Different blast radii.** A bad Terraform apply can delete a VPC. A bad Helm upgrade can roll back in 30 seconds. You want different review gates, different deploy cadences, different on-call playbooks. Putting them in one tool collapses that separation.
2. **Different state machines.** Terraform reconciles toward a static plan. Kubernetes is continuously reconciling — controllers watch the API and act on drift forever. Trying to make Terraform manage 500 Deployments is fighting the tool: Terraform sees drift and "fixes" it, racing with the k8s controller that's also trying to fix it.
3. **Different audiences.** Platform team writes Terraform; product teams write Helm values. The seam is also an org boundary.

A common anti-pattern is putting *application* Deployments in Terraform (using the `kubernetes` provider for everything). It works on day one, but you eventually feel the friction: every app deploy needs a Terraform apply, drift detection screams, and the platform team becomes a bottleneck for product teams. This repo avoids that — Terraform's `kubernetes` provider is used *only* for cluster-wide system stuff (namespaces, operator installs), never for application Deployments.

The opposite anti-pattern is putting *infrastructure* in Helm (e.g., trying to provision RDS via a Helm chart wrapping a CRD). It can be done with the AWS Controllers for Kubernetes (ACK) — and you can see hints of that in the `ack-iam.tf` file — but it's a minority pattern and usually scoped to specific resources, not the whole stack.

---

## Compare: alternatives you'll hear named

- **Pulumi instead of Terraform.** Same tier-1 role, code-not-DSL. Real choice; this team picked Terraform.
- **Crossplane.** Manages cloud resources *from inside Kubernetes* via CRDs — collapses tier-1 and tier-2 into one control plane. Powerful, but you trade Terraform's mature plan/apply story for a much newer ecosystem. Worth knowing exists.
- **Pure GitOps with Flux/ArgoCD applying *everything* (including Terraform-rendered manifests).** This repo does use ArgoCD for the Helm side; it does not use it for the Terraform side. Some teams unify them via tf-controller or Atlantis.
- **eksctl + raw manifests, no Helm.** Fine at tiny scale. Falls apart when you have N environments × M services and need templating.

The takeaway isn't "Terraform + Helm is the right answer." It's: *whatever you pick, you almost always end up with two tiers and a seam. The question is just which tools sit on which side.*

---

## Comprehension check

Without scrolling back up, answer these. (Predict, then verify by opening the file.)

1. **Sorting test.** For each of the following, say which side of the seam it lives on (Terraform or Helm) and why:
   - The IAM role that lets the OCR pod read from S3.
   - The number of OCR replicas at minimum and maximum.
   - The KEDA polling interval for the OCR `ScaledObject`.
   - The decision that prod should sample 1% of traces.
   - The Karpenter NodePool that says "schedule GPU jobs only on g5 instances."
   - A new env var `FEATURE_X_ENABLED=true` on the `llamacloud-api` Deployment.

2. **Failure-mode test.** A teammate says: "I deleted `keda.tf` from prod's terraform and ran apply. Now `helm upgrade` on `llamacloud-models` is failing with `no matches for kind ScaledObject in version keda.sh/v1alpha1`. Why? What's the fix?"

3. **Seam-finding test.** Open [infra/terraform/modules/eks/](infra/terraform/modules/eks/) and list the files that install *in-cluster* things (operators/controllers) rather than pure AWS resources. (Hint: look at file names — they're named after what they install.) For one of them, predict what corresponding *workload-side* config probably exists in `infra/charts/`.

When you've taken a swing at these, tell me your answers and we'll grade them together. Then we move to **Lesson 2 — what the EKS module actually builds**, where we open `modules/eks/main.tf` and watch an EKS cluster come into existence as a handful of concrete AWS resources.
