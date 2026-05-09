# Variables for the Ollama-on-EKS example module.
#
# These are the knobs every adopter needs to tune. The defaults match
# the smallest reasonable production deployment: 1 replica, 4 vCPU /
# 8 GiB, 50 GiB gp3 PVC for model weights, llama3.2:3b + nomic-embed-text
# baked in via an init job.
#
# Replace `acme-corp` placeholders with your own cluster / org names.

variable "cluster_name" {
  description = "Name of the EKS cluster the module deploys into. Used only for outputs and tagging — the kubernetes provider must already be wired to the cluster."
  type        = string
  default     = "acme-corp-platform"
}

variable "namespace" {
  description = "Kubernetes namespace for the Ollama workload. Created by the manifest, not by Terraform."
  type        = string
  default     = "teammate"
}

variable "ollama_image_tag" {
  description = "ollama/ollama image tag. `latest` is convenient for evaluation; pin to an immutable digest in production (e.g. `0.4.7`) so kube-rolls become deterministic."
  type        = string
  default     = "latest"
}

variable "model_pulls" {
  description = "Models the init Job pulls into /root/.ollama on first deploy. Add embedding + LLM models here. Pulls are idempotent — re-running the Job is safe."
  type        = list(string)
  default     = ["llama3.2:3b", "nomic-embed-text"]
}

variable "replicas" {
  description = "Number of Ollama replicas. ClusterIP service in front. Start at 1; scale once you've measured request volume."
  type        = number
  default     = 1
}

variable "cpu_request" {
  description = "Per-replica CPU request. Ollama is CPU-bound on small models; 4 vCPU is the comfortable lower bound for llama3.2:3b."
  type        = string
  default     = "2"
}

variable "cpu_limit" {
  description = "Per-replica CPU limit."
  type        = string
  default     = "4"
}

variable "memory_request" {
  description = "Per-replica memory request. nomic-embed-text + llama3.2:3b together need ~6 GiB of RSS during inference."
  type        = string
  default     = "6Gi"
}

variable "memory_limit" {
  description = "Per-replica memory limit. Set above your peak inference footprint — OOM kills will look like flaky failures."
  type        = string
  default     = "8Gi"
}

variable "pvc_size" {
  description = "PVC size for model weights. 50 GiB fits a handful of 7B models comfortably; bump to 100 GiB if you plan to host > 3 mid-size models."
  type        = string
  default     = "50Gi"
}

variable "storage_class" {
  description = "StorageClass for the PVC. EKS default is gp3 in modern provisioners; override only if your cluster has a different name or class for general-purpose SSD."
  type        = string
  default     = "gp3"
}

variable "enable_hpa" {
  description = "Whether to create the HorizontalPodAutoscaler. Disable when you want fixed replicas (deterministic capacity / cost)."
  type        = bool
  default     = true
}

variable "hpa_min_replicas" {
  description = "Minimum replicas the HPA may scale to."
  type        = number
  default     = 1
}

variable "hpa_max_replicas" {
  description = "Maximum replicas the HPA may scale to."
  type        = number
  default     = 4
}

variable "hpa_cpu_target" {
  description = "Target average CPU utilization the HPA tries to hold."
  type        = number
  default     = 70
}

variable "service_account_role_arn" {
  description = "Optional IRSA role ARN bound to the Ollama service account. Vanilla Ollama pulls models from registry.ollama.ai over public HTTPS and needs no AWS auth, so this is empty by default. Set this if you mirror models from a private S3 bucket or pull images from a private ECR (in which case the node role usually still suffices for ECR — set this only when the *pod* needs IAM)."
  type        = string
  default     = ""
}
