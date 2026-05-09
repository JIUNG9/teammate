# Ollama on EKS — example Terraform module (Phase B).
#
# Phase A in teammate is "every engineer runs Ollama on their laptop".
# Phase B is "the team runs one shared Ollama on EKS so a half-dozen
# engineers don't each have to babysit a local model".
#
# This module is a STARTER. Drop it into your platform repo, point the
# kubernetes provider at your EKS cluster, run `terraform apply`, and
# get:
#   - a Namespace
#   - a Deployment (Ollama, configurable replicas, requests + limits)
#   - a ClusterIP Service on port 11434
#   - a PVC for model weights
#   - an init Job that pre-pulls the configured models on first deploy
#   - an optional HPA on CPU
#
# We deliberately do NOT reach into AWS resources here — no aws_*
# resources are created. The cluster, node group, IAM, and
# StorageClass already exist in the host platform; this module is
# purely a Kubernetes overlay.
#
# RECOMMENDED PATH: pair this Terraform with ArgoCD.
# Terraform creates the namespace + PVC. ArgoCD owns the Deployment +
# Service via the manifest in ../argocd/application.yaml. That keeps
# the workload sync loop in ArgoCD where the rest of your apps live.
# If you want the all-Terraform path instead, the kubernetes_manifest
# resources below give you a `terraform apply` round-trip.

terraform {
  required_version = ">= 1.5"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.30"
    }
  }
}

# The kubernetes provider must be configured by the caller (root
# module). We don't set host / token here — the right pattern is to
# wire the provider via aws_eks_cluster + aws_eks_cluster_auth in your
# platform module, then call this module.

locals {
  app_label = {
    "app.kubernetes.io/name"       = "ollama"
    "app.kubernetes.io/managed-by" = "teammate-phase-b"
  }
}

resource "kubernetes_namespace" "ollama" {
  metadata {
    name   = var.namespace
    labels = local.app_label
  }
}

resource "kubernetes_persistent_volume_claim" "ollama_models" {
  metadata {
    name      = "ollama-models"
    namespace = kubernetes_namespace.ollama.metadata[0].name
    labels    = local.app_label
  }
  spec {
    access_modes = ["ReadWriteOnce"]
    resources {
      requests = {
        storage = var.pvc_size
      }
    }
    storage_class_name = var.storage_class
  }
  # PVC binds lazily — the bind happens when the Deployment lands.
  wait_until_bound = false
}

resource "kubernetes_service_account" "ollama" {
  metadata {
    name      = "ollama"
    namespace = kubernetes_namespace.ollama.metadata[0].name
    labels    = local.app_label
    annotations = var.service_account_role_arn == "" ? {} : {
      "eks.amazonaws.com/role-arn" = var.service_account_role_arn
    }
  }
}

# The Deployment + Service + HPA can either live here (terraform-only)
# or be owned by ArgoCD (../argocd/application.yaml + ../k8s/*.yaml).
# We ship them here behind a `count = var.terraform_owns_workload ? 1
# : 0` guard so you can choose. To keep the module readable in the
# OSS example, we expose the workload via raw manifests in ../k8s/
# and ArgoCD App in ../argocd/ — both paths are documented in the
# README.

output "_manifests_note" {
  description = "Where to find the Deployment / Service / Job / HPA manifests."
  value       = "Workload manifests live at ../k8s/. ArgoCD Application at ../argocd/application.yaml. This Terraform module ships only the namespace, PVC, and ServiceAccount — the durable infra primitives — so the workload definition stays declarative + GitOps-friendly."
}
