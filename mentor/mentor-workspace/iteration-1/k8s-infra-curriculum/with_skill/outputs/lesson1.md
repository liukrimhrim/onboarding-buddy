# Lesson 1 transcript — The shape of `infra/`, and why it's split this way

## Intake (recap)

**User goal:** Read the Helm chart and Terraform confidently; debug a misbehaving pod in staging. Mostly (a) + (c) from the offered framings.

**Starting point:** Has shipped services that run on the cluster. Comfortable with `kubectl logs / describe / get pods`, can read a Deployment YAML. Has never set up a cluster, never authored a Helm chart, treats Karpenter and IRSA as black boxes. Can read Terraform but not author it.

**Scope:** 6 lessons.

## Curriculum agreed on

1. The shape of `infra/` — what lives where, and why. (**this lesson**)
2. A pod's life — from a Deployment YAML to a running container.
3. Services, ingress, and how traffic gets in.
4. EKS = managed k8s + AWS glue.
5. Autoscaling: HPA (pods) and Karpenter (nodes).
6. Debugging a sick pod in staging — synthesis.

User said "ship it" — committed to disk.

---

## Lesson 1

### Goal

By the end of this lesson, you'll be able to look at any path under `infra/` and (a) say whether it provisions AWS, configures the cluster, deploys our app, or operates the running cluster; (b) explain *why* those things are separated.

### (a) Ground in this repo

Top of `infra/`:

```
infra/
├── charts/              # Helm charts (what gets deployed *into* the cluster)
├── kubernetes/          # k8sctl — operational tooling, Python CLI for kubectl-y ops
├── scripts/             # ad-hoc shell helpers
├── terraform/           # AWS infrastructure (the cluster itself, networking, RDS)
├── terraform-posthog/   # PostHog-specific terraform, isolated
└── tools/               # misc tooling
```

Three do the heavy lifting:

**`infra/terraform/` — "what AWS gives us"**

```
terraform/
├── environments/    # one dir per env: 8am, dev, new-york-life, opg, prod, prod-eu, staging, ...
└── modules/         # reusable building blocks: eks, aurora-postgresql, documentdb,
                     # elasticache, amazon-mq, loki, networking, storage, ...
```

Each environment is a `main.tf` wiring modules together for that account.
`infra/terraform/environments/staging/main.tf:47` shows the staging entry point — mostly a `locals` block (account_id, region, vpc_name) plus provider config and module calls. The actual EKS cluster resource lives in the reusable module at `infra/terraform/modules/eks/main.tf:26` (`resource "aws_eks_cluster" "this"`).

Mental model: terraform/ says "AWS, please give me a cluster, with these IAM roles, these subnets, these addons." Rare changes. Produces an empty-ish cluster ready to receive workloads.

**`infra/charts/` — "what we deploy onto the cluster"**

```
charts/
├── llamacloud/                    # main chart — backend, frontend, jobs, workers
├── llamacloud-external-services/  # things like temporal, RabbitMQ if not managed
├── llamacloud-models/             # model-serving deployments
├── llamacloud-saas/               # SaaS-specific overlay
├── environments/                  # per-env values.yaml — staging/, prod/, 8am/, ...
└── arc-cluster, test-cluster, _internal, usage-export
```

The *shape* of the deployment lives in `infra/charts/llamacloud/templates/` (deployment.yaml, service.yaml, ingress.yaml, hpa.yaml, pdb.yaml, serviceaccount.yaml). The per-env *parameters* live in `charts/environments/<env>/values.yaml`. Same chart, different values per env.

Mental model: charts/ says "k8s, please run these pods, expose these services, scale them with these rules." Frequent changes. Runs every deploy.

**`infra/kubernetes/` — "tools for operating the running cluster"**

Python project (`k8sctl/`) wrapping kubectl-style ops. Not IaC in the Terraform sense — a CLI used during day-to-day cluster ops (rollouts, connecting to envs, debugging).

### (b) Generalize — provisioning vs. workload

The line through `infra/` is the **provisioning vs. workload boundary**. Why split them:

- **Different change frequency.** AWS resources change rarely (months); app deploys happen many times per day. Mixing them couples slow + fast and breaks blast-radius reasoning. A bad chart change should never be able to delete your RDS.
- **Different blast radius.** A botched `terraform apply` can vaporize a database. A botched `helm upgrade` rolls back to the previous ReplicaSet. The tools *should* feel different because they *are* different.
- **Different audiences/permissions.** Terraform runs from CI with privileged IAM that can touch IAM and networking. Helm runs with weaker cluster-scoped permission to update Deployments. The boundary mirrors a permissions boundary.
- **Different state.** Terraform stores state in S3 (`infra/terraform/environments/staging/main.tf:20`) and reconciles to it. Helm stores release state as Secrets in the cluster. Two reconciliation loops, two recovery stories.

`kubernetes/` tooling is separate from both — it doesn't change desired state, it inspects/operates the running system. Third category: **provisioning, deployment, operations.**

### (c) Compare — alternatives

- **Pure Terraform-for-everything** (using the `kubernetes` and `helm` providers to manage app deployments). Tempting for unified state, but Terraform's reconciliation fights with k8s controllers, drift detection becomes painful, and every Deployment edit needs `terraform apply`. Most teams back off.
- **GitOps with ArgoCD/Flux** — chart applied by a controller watching git, not by humans running `helm upgrade`. Our `infra/kubernetes/README.md:26` mentions ArgoCD, so there's a partial story. ArgoCD doesn't change the chart/terraform split; it changes *who runs helm* (in-cluster controller vs. human/CI).
- **Single mega-chart vs. multiple charts.** We chose split: `llamacloud`, `llamacloud-external-services`, `llamacloud-models`. Benefit: independent release cadence. Cost: values duplication.

### (d) Comprehension check

1. **Easy.** Which directory would you touch to (a) bump the backend image tag in staging, (b) add a new RDS instance, (c) curl-debug a Service from inside the cluster?
2. **Medium.** `infra/charts/environments/staging/` and `infra/terraform/environments/staging/` both have `staging` in the path. Why two dirs? Could we collapse?
3. **The good one.** `infra/terraform/environments/staging/karpenter-llamadeploy-nodepool.yaml` is a `kind: NodePool` — a Kubernetes custom resource, not a Terraform resource. Why does it live under `terraform/`? What does its placement say about Karpenter the controller vs. Karpenter the NodePool CR?

### Wrap-up

- Updated curriculum: lesson 1 checked, current_lesson advanced to 2.
- Notes appended under "Notes from sessions" — includes the user's #3 side-question and a follow-up about per-env Terraform vs. per-env Helm values to revisit in lesson 5.
- Next lesson: "A pod's life — from a Deployment YAML to a running container." Anchor `infra/charts/llamacloud/templates/llamacloud/deployment.yaml`, climb to the k8s control loop.

---

## File-write note (real, not roleplay)

`~/.claude/mentor-curricula/` does not exist on this host and the sandbox denied directory creation for me (both `mkdir` via Bash and Write-with-implicit-parent-create were refused). The canonical curriculum file is therefore present *only* at the workspace location:

- `/Users/jinxinliu/.claude/skills/mentor-workspace/iteration-1/k8s-infra-curriculum/with_skill/outputs/curriculum.md`

To make the skill's "resume across sessions" promise real, the user (or the harness) needs to either pre-create `~/.claude/mentor-curricula/` once or grant directory-create permission under `~/.claude/`. After that, the same content should be copied to `~/.claude/mentor-curricula/k8s-infra.md`.
