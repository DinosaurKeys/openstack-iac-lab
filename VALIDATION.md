# Validation and deployment status

This repository contains implementation code and learning guides. It has not deployed or changed the physical lab. Generated examples are not claimed as observed deployment results.

## Checked locally

- Parsed YAML, JSON, Python, and Terraform/HCL source and examples.
- Checked relative Markdown links and code-fence balance.
- Checked all Ansible playbooks with ansible-playbook --syntax-check.
- Exercised input guards for preserved node addresses, duplicate provider MACs, reserved floating addresses, and overlapping workload networks.
- Exercised storage guards for wrong serials, mounted OS descendants, existing Ceph signatures, and partitioned/nonblank disks.
- Ran 11 guard tests, including a guest-volume serial/UUID association check.
- Checked shell syntax and generated inventory membership.

GitHub Actions independently runs source checks and native Terraform provider validation without lab credentials. Read its actual run result; the presence of a workflow file is not a passing result.

## Requires the real lab

The following are intentionally not claimed as tested: Ubuntu reinstall, exact disk cleanup, SMART health, NIC driver/link behavior, Netplan application, Kolla container startup, MariaDB/RabbitMQ quorum, volume attachment, PostgreSQL data migration, application HTTP behavior, monitoring scrapes, alert firing, and controller failover.

The Cinder LVM multi-controller caveat in Kolla's documentation remains a validation gate. This implementation uses one backend host and aligned service-group membership; that design choice does not replace a live cross-compute read/write/reattach test.

## First live evidence required

1. Run bash scripts/discover.sh on Hermes before erasing nodes and review the private reports.
2. Confirm actual provider NIC MACs, DNS, data-disk by-id path/serial/health, and a floating-IP range excluded from router DHCP and every other LAN device.
3. Reinstall all three nodes as agreed, keeping their addresses and preserving Hermes.
4. Fill private/lab.yml and use the staged commands in README.md.

The storage helper provisions only an unowned blank disk. It refuses old Ceph/LVM/filesystem signatures. Exact erasure of existing storage must be prepared from the observed disk identities; the code does not guess a device or silently wipe every node.
