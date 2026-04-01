# Hetzner Setup

This directory holds optional Hetzner bootstrap templates for a single VPS setup.

Files:

- `cloud-init.example.yaml`
- `firewall-rules.json`

Recommended server options:

- Ubuntu 24.04
- CPX22
- NBG1
- IPv4 and IPv6 enabled
- SSH key added up front

If using cloud-init, replace the placeholder SSH key before creating the server.

Optional firewall setup:

```bash
hcloud firewall create --name "muckrake-web" --rules-file "ops/hetzner/firewall-rules.json"
hcloud firewall apply-to-resource --type server --server "muckrake-prod-01" "muckrake-web"
```

The app deploy and server runtime notes live in `../README.md`.
