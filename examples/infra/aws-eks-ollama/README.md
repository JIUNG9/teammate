# Ollama on EKS — Phase B reference deployment

This directory ships the reference infrastructure for **Phase B**: a
team-shared Ollama instance running on EKS, fronted by a ClusterIP
service, with model weights persisted on a gp3 PVC. Phase A (every
engineer runs Ollama on their laptop) remains the OSS default; this
deployment is for teams who'd rather centralize the inference plane.

> **TL;DR for the impatient:** copy this directory into your platform
> repo, point your `kubernetes` provider at your EKS cluster, run
> `terraform apply` here, then `kubectl apply -f ../k8s/`. Engineers
> point teammate at `http://ollama.teammate.svc.cluster.local:11434`
> in their `.teammate/config.toml`.

## What this ships

```
examples/infra/aws-eks-ollama/
├── README.md                      ← you are here
├── terraform/                     ← Namespace, PVC, ServiceAccount
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── argocd/
│   └── application.yaml           ← optional: ArgoCD Application
└── k8s/                           ← raw manifests (kubectl apply path)
    ├── ollama-deployment.yaml     ← Deployment + HPA
    ├── ollama-service.yaml        ← ClusterIP :11434
    ├── ollama-pvc.yaml            ← gp3 50 GiB volume
    └── ollama-init-job.yaml       ← post-sync model pull
```

The split is deliberate: **Terraform owns the durable primitives**
(namespace, PVC, ServiceAccount — the things you don't want a
GitOps-loop accidentally pruning); **ArgoCD owns the workload**
(Deployment, Service, HPA, init Job — the things you want declarative
+ reconciled). If you don't run ArgoCD, the raw `k8s/*.yaml` works
with `kubectl apply` directly.

## Prerequisites

Before you apply anything in this directory:

1. **An EKS cluster.** Kubernetes 1.28 or newer. The manifests assume
   the `gp3` storage class is available — most modern EKS clusters
   ship with it.
2. **`kubectl` context** pointing at the cluster (`aws eks
   update-kubeconfig --name <your-cluster> --region <your-region>`).
3. **A gp3 StorageClass.** If your cluster predates the EBS CSI
   default, install it: `aws eks create-addon --cluster-name <c>
   --addon-name aws-ebs-csi-driver`. Verify:
   `kubectl get sc gp3` returns a non-error.
4. **Cluster autoscaler or Karpenter**, or a node group with at least
   one node large enough to fit the Ollama Pod (see *Sizing* below).
5. **Terraform 1.5+** if you go the Terraform route; **kubectl** plus
   either ArgoCD or vanilla `kubectl apply` for the workload.

## Sizing

Ollama is CPU-bound on small models. The defaults target llama3.2:3b
plus nomic-embed-text — together they need ~6 GiB resident plus
enough CPU headroom to stream a 100-token answer in a few seconds.

| Resource | Default request | Default limit |
| --- | --- | --- |
| CPU | 2 vCPU | 4 vCPU |
| Memory | 6 GiB | 8 GiB |
| Storage (PVC) | 50 GiB gp3 | — |

If you plan to host larger models (7B, 13B) or more concurrent
queries:

- Bump `cpu_request` / `cpu_limit` to 4 / 8 (or move to a GPU node
  group — out of scope for this OSS example, but the same module
  works once you set the right node selector and runtime class).
- Bump `memory_limit` to `16Gi` for 7B models.
- Bump `pvc_size` to `100Gi` if you'll keep more than three
  mid-size models around.

## Deploy via Terraform + kubectl (simple path)

This is the **recommended starting point** if you don't already run
ArgoCD: Terraform creates the namespace + PVC + ServiceAccount, then
you `kubectl apply` the workload manifests.

```bash
cd terraform
terraform init
terraform plan -var "cluster_name=acme-corp-platform" \
               -var "namespace=teammate"
terraform apply -var "cluster_name=acme-corp-platform" \
                -var "namespace=teammate"
```

You should see three Kubernetes resources created:

```
kubernetes_namespace.ollama: Creation complete
kubernetes_persistent_volume_claim.ollama_models: Creation complete
kubernetes_service_account.ollama: Creation complete
```

Now apply the workload:

```bash
kubectl apply -n teammate -f ../k8s/ollama-deployment.yaml
kubectl apply -n teammate -f ../k8s/ollama-service.yaml
kubectl apply -n teammate -f ../k8s/ollama-init-job.yaml
```

Wait for the Pod to come up:

```bash
kubectl rollout status -n teammate deployment/ollama --timeout=10m
```

The init Job runs `ollama pull llama3.2:3b` and `ollama pull
nomic-embed-text` in the background. You can watch:

```bash
kubectl logs -n teammate -l job-name=ollama-pull-models -f
```

First pull is slow (~5 minutes for the 3B model on a typical EKS
egress link). Subsequent pulls are no-ops because the PVC keeps the
weights.

## Deploy via ArgoCD (recommended for production)

If your platform already uses ArgoCD, skip the `kubectl apply` step
and let the controller own reconciliation:

```bash
# 1. Run Terraform for the durable primitives only.
cd terraform
terraform apply -var "cluster_name=acme-corp-platform"

# 2. Commit the contents of `../k8s/` into your platform repo at
#    `infra/ollama/k8s/`. (Adjust the path in
#    argocd/application.yaml accordingly.)

# 3. Apply the ArgoCD Application:
kubectl apply -n argocd -f ../argocd/application.yaml
```

The shipped Application manifest **does not enable automated sync**.
That is intentional. Workload-level changes to a shared inference
endpoint are exactly the case where you want a human to click sync
after reading the diff. Once you've shipped the same module to two
or three teams and trust the rollout, flip `automated: null` to:

```yaml
automated:
  prune: false      # never auto-prune Ollama; pruning a model PVC is unrecoverable
  selfHeal: true
```

## Validate the deployment

Once the Pod is `Ready`:

```bash
# 1. From inside the cluster (e.g. a debug Pod):
kubectl run -n teammate --rm -it --image=curlimages/curl:8.10.1 \
  ollama-probe -- curl -fsS http://ollama:11434/ \
  && echo "OK"

# 2. Run a smoke generation:
kubectl exec -n teammate deploy/ollama -- \
  ollama list

# 3. From your laptop (with port-forward):
kubectl port-forward -n teammate svc/ollama 11434:11434 &
curl -fsS http://localhost:11434/api/tags | python -m json.tool
```

You should see `llama3.2:3b` and `nomic-embed-text` in the model list.

## Point teammate at the EKS endpoint

Engineers who want to use the shared instance instead of running
Ollama locally:

```toml
# .teammate/config.toml — per-repo or in ~/.teammate/config.toml

[llm]
provider = "ollama"
model    = "llama3.2:3b"
host     = "http://ollama.teammate.svc.cluster.local:11434"

[embedding]
provider = "ollama"
model    = "nomic-embed-text"
host     = "http://ollama.teammate.svc.cluster.local:11434"
```

That host is the in-cluster DNS name. For laptop-to-cluster access,
two clean options:

1. **Port-forward (developer laptops):**
   `kubectl port-forward -n teammate svc/ollama 11434:11434` — set
   `host = "http://localhost:11434"` in your local config.
2. **VPN / private LB:** if your cluster lives on a VPC the laptops
   can reach, swap the Service to a private NLB and use that DNS
   name. ClusterIP-only is the safer OSS default; promote to private
   LB only after a security review.

`teammate doctor` will pick up the new endpoint and probe it for
reachability + model availability.

## Cost notes

Sized for a 5–15 engineer team:

| Component | Approx monthly | Notes |
| --- | --- | --- |
| t3.xlarge node (4 vCPU / 16 GiB) | ~$120 | Or fold into existing node group |
| 50 GiB gp3 EBS volume | ~$4 | Cheap; never fills under normal use |
| EKS control plane | $0 incremental | Already running for the rest of your stack |
| **Total incremental** | **~$50–125/mo** | Depends on whether the node is shared |

A GPU node group (g5.xlarge ≈ $720/mo on-demand) is roughly an
order of magnitude more expensive and only justified if you've
benchmarked CPU latency and confirmed it's the bottleneck. For
nomic-embed-text + llama3.2:3b answering 50 queries/day across the
team, CPU is fine.

## Operational playbook

| Task | Command |
| --- | --- |
| Tail Ollama logs | `kubectl logs -n teammate deploy/ollama -f` |
| List installed models | `kubectl exec -n teammate deploy/ollama -- ollama list` |
| Pull a new model | `kubectl exec -n teammate deploy/ollama -- ollama pull <name>` |
| Restart (preserves PVC) | `kubectl rollout restart -n teammate deploy/ollama` |
| Resize the PVC | edit `pvc_size` in tfvars, `terraform apply`, `kubectl get pvc -n teammate` |
| Delete and reinstall | `kubectl delete -n teammate -f ../k8s/`; the PVC remains |

## Failure modes worth knowing

- **OOMKilled.** Most often during the first generation after a
  cold start with a model larger than the memory limit. Fix: bump
  `memory_limit` to a value above your peak inference RSS.
- **PVC stuck in Pending.** Usually means the storage class doesn't
  exist or the cluster has no node in the AZ where the PVC is
  binding. Fix: `kubectl describe pvc -n teammate ollama-models` and
  follow the events.
- **`ollama pull` 503s.** registry.ollama.ai had an outage. Re-run
  the init Job — it's idempotent.
- **High latency.** Check if another Pod on the same node is
  CPU-throttling Ollama. Add a node anti-affinity rule, or move
  Ollama to a dedicated node pool.

## Why this isn't an Ollama operator

We could have shipped a CRD + controller. We didn't because:

- The shape of "one Deployment + one Service + one PVC" is small
  enough that vanilla manifests beat any abstraction.
- Most teams already run ArgoCD or Argo Rollouts; the surface area
  for a new operator to integrate cleanly is non-trivial.
- The OSS contract here is "boring infra you can read in five
  minutes". A custom operator would invert that.

If you're operating dozens of Ollama instances at multi-tenant
scale, consider a higher-level abstraction. For one shared instance
per team, the manifests above are all you need.

## OSS hygiene

Every example in this directory uses generic placeholders:
`acme-corp`, `your-team.local`, `acme-corp.internal`. Replace them
with your own org's values when you copy this into your platform
repo. If you find a hardcoded employer-specific value here, it's a
bug — file an issue.
