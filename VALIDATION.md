# Validation and deployment status

This repository contains implementation code and learning guides. The user has completed the three Ubuntu reinstalls and run basic discovery; OpenStack deployment remains untested. Generated examples are not claimed as observed deployment results.

## Checked locally

- Parsed YAML, JSON, Python, and Terraform/HCL source and examples.
- Checked relative Markdown links and code-fence balance.
- Checked all Ansible playbooks with ansible-playbook --syntax-check.
- Exercised input guards for preserved node addresses, duplicate provider MACs, reserved floating addresses, and overlapping workload networks.
- Exercised storage guards for wrong serials, mounted OS descendants, existing Ceph signatures, and partitioned/nonblank disks.
- Ran 11 guard tests, including a guest-volume serial/UUID association check.
- Checked shell syntax and generated inventory membership.
- Checked the consolidated storage collector with simulated SSH and diagnostic commands, including all-node collection, report privacy, optional tool installation, and continuation after connection/SMART flags. This is a local check, not real disk-health validation.

GitHub Actions independently runs source checks and native Terraform provider validation without lab credentials. Read its actual run result; the presence of a workflow file is not a passing result.

## Requires the real lab

The following are intentionally not claimed as tested: exact disk cleanup, SMART health, NIC driver/link behavior, Netplan application, Kolla container startup, MariaDB/RabbitMQ quorum, volume attachment, PostgreSQL data migration, application HTTP behavior, monitoring scrapes, alert firing, and controller failover.

The Cinder LVM multi-controller caveat in Kolla's documentation remains a validation gate. This implementation uses one backend host and aligned service-group membership; that design choice does not replace a live cross-compute read/write/reattach test.

## Live evidence and remaining checks

The user-supplied discovery reports from 2026-10-21 confirm Ubuntu 24.04.5 on all three nodes, original management addresses, `joe` SSH access, configured gateway/DNS, synchronized clocks, /dev/kvm, actual USB NIC MACs, and disk identities. Their separate SATA disks still contain Ceph LVM volumes. This confirms identity and retained metadata; it does not establish SSD health or provider-link operation.

1. Run `bash scripts/check-storage.sh joe --install-tools` once on Hermes and review its single `build/storage-health-report.txt` for privileged mount/ownership and SMART evidence.
2. Verify USB provider links, DNS operation, the unused API VIP, and a floating-IP range excluded from router DHCP and every other LAN device.
3. Prepare any exact disk cleanup from the reviewed report; keep storage reuse conditional on health and ownership checks.
4. Fill private/lab.yml and use the staged commands in README.md. Hermes remains intact.

The storage helper provisions only an unowned blank disk. It refuses old Ceph/LVM/filesystem signatures. Exact erasure of existing storage must be prepared from the observed disk identities; the code does not guess a device or silently wipe every node.
