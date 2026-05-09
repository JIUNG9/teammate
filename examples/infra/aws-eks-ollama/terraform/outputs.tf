output "namespace" {
  description = "Kubernetes namespace the workload runs in."
  value       = kubernetes_namespace.ollama.metadata[0].name
}

output "service_dns_name" {
  description = "In-cluster DNS name engineers should point teammate at. Append `:11434`."
  value       = "ollama.${kubernetes_namespace.ollama.metadata[0].name}.svc.cluster.local"
}

output "service_account_name" {
  description = "ServiceAccount the workload runs as. Bind IRSA via service_account_role_arn."
  value       = kubernetes_service_account.ollama.metadata[0].name
}

output "pvc_name" {
  description = "PVC name for the model-weights volume."
  value       = kubernetes_persistent_volume_claim.ollama_models.metadata[0].name
}
