#!/usr/bin/env bash
set -euo pipefail

backend_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="${HOME}/.kube"
config_file="${config_dir}/investigation-reader.kubeconfig"
temp_file=""
trap 'if [[ -n "${temp_file}" ]]; then rm -f -- "${temp_file}"; fi' EXIT

sudo k3s kubectl apply -f "${backend_dir}/k8s/readonly-rbac.yaml"

token="$(sudo k3s kubectl -n ecommerce create token investigation-reader --duration=1h)"
api_server="$(sudo k3s kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
ca_data="$(sudo k3s kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"

if [[ -z "${token}" || -z "${api_server}" || -z "${ca_data}" ]]; then
  echo "Could not create a complete read-only Kubernetes client configuration." >&2
  exit 1
fi

install -d -m 700 "${config_dir}"
temp_file="$(mktemp "${config_dir}/.investigation-reader.XXXXXX")"
chmod 600 "${temp_file}"
cat >"${temp_file}" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: local-k3s
    cluster:
      server: ${api_server}
      certificate-authority-data: ${ca_data}
users:
  - name: investigation-reader
    user:
      token: ${token}
contexts:
  - name: investigation-reader@local-k3s
    context:
      cluster: local-k3s
      user: investigation-reader
      namespace: ecommerce
current-context: investigation-reader@local-k3s
EOF
mv -f -- "${temp_file}" "${config_file}"
temp_file=""
chmod 600 "${config_file}"

printf 'Read-only kubeconfig created at %s (token expires in 1 hour).\n' "${config_file}"
printf 'Use it with: export KUBECONFIG=%s\n' "${config_file}"
