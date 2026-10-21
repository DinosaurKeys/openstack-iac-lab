# Validation and deployment status

This repository contains implementation code and learning guides. The user has completed the three Ubuntu reinstalls, basic discovery, and privileged storage collection. OpenStack deployment remains untested. Generated examples are not claimed as observed deployment results.

## Checked locally

- Parsed YAML, JSON, Python, and Terraform/HCL source and examples.
- Checked relative Markdown links and code-fence balance.
- Checked all Ansible playbooks with ansible-playbook --syntax-check.
- Exercised input guards for preserved node addresses, duplicate provider MACs, reserved floating addresses, and overlapping workload networks.
- Exercised storage guards for wrong serials, mounted OS descendants, existing Ceph signatures, and partitioned/nonblank disks.
- Ran 45 guard tests: the original 11 input/storage/guest-volume checks plus 34 exact-Ceph-removal guard and execution-flow tests. The added tests use fixtures and mocked subprocesses; they never operate on real disks.
- Added regression coverage for the actual Linux model strings from all three nodes, rejection of unrecorded prefixes, diagnostic values before a model stop, and exact byte-capacity mismatch messages. Model/capacity failures still reject apply before any mutation or confirmation.
- Compared LV aliases by their canonical device paths: a /dev/mapper name must resolve to the same device as the recorded /dev/VG/LV path. Regression fixtures accept that same-device alias and reject an unrelated LV; ownership checks remain exact.
- Checked shell syntax and generated inventory membership.
- Checked the consolidated storage collector with simulated SSH and diagnostic commands, including all-node collection, report privacy, optional tool installation, and continuation after connection/SMART flags. This is a local check, not real disk-health validation.
- Checked explicit node1/node2/node3/all selection, invalid target rejection, and the explanatory message for SMART command exit 4 with simulated commands.
- Checked the new reset-ceph SSH wrapper with eight isolated simulated runs: target selection, remote Python quoting/compilation, preserved terminal input, apply/plan arguments, private reports, invalid inputs and stop-on-first-failure behavior. No SSH connection or disk command executed in these checks.

The live evidence below comes from the user's earlier all-node run. The new node selector, wider table and explanatory message have local simulated checks; they have not yet been run on the real lab.

GitHub Actions independently runs source checks and native Terraform provider validation without lab credentials. Read its actual run result; the presence of a workflow file is not a passing result.

## Requires the real lab

The following are intentionally not claimed as tested: exact disk cleanup, resolution of health/diagnostic findings, new SMART self-tests, NIC driver/link behavior, Netplan application, Kolla container startup, MariaDB/RabbitMQ quorum, volume attachment, PostgreSQL data migration, application HTTP behavior, monitoring scrapes, alert firing, and controller failover.

The Cinder LVM multi-controller caveat in Kolla's documentation remains a validation gate. This implementation uses one backend host and aligned service-group membership; that design choice does not replace a live cross-compute read/write/reattach test.

## Live evidence and remaining checks

The user-supplied discovery reports from 2026-10-21 confirm Ubuntu 24.04.5 on all three nodes, original management addresses, `joe` SSH access, configured gateway/DNS, synchronized clocks, /dev/kvm, actual USB NIC MACs, and disk identities. Their separate SATA disks still contain Ceph LVM volumes. This confirms identity and retained metadata; it does not establish SSD health or provider-link operation.

The user's storage run from 2026-10-21 reached all three nodes and installed smartmontools 7.4. On each node, the Ubuntu VG reports 235.42 GiB total and 135.42 GiB unallocated, with a 100 GiB root LV on NVMe. Each separate SATA disk retains a Ceph VG/LV with no unallocated VG space.

| Node | Main NVMe health fields | Diagnostic finding |
|---|---|---|
| node1 | Critical warning 0x00; media/data-integrity errors 0; percentage used 4% | Self-test log request rejected with Invalid Field, command exit 4 |
| node2 | Critical warning 0x00; media/data-integrity errors 0; percentage used 0% | Self-test log request rejected with Invalid Namespace or Format, command exit 4 |
| node3 | Critical warning 0x00; media/data-integrity errors 0; percentage used 7% | Self-test log request rejected with Invalid Field, command exit 4 |

All six drives report overall PASSED in this snapshot. Node1's SATA Runtime_Bad_Block raw count is 11 and remains a separate review item. Node2's SATA error log is unsupported. Historical extended self-tests completed without error on all three SATA disks; this run did not launch new tests. The UMIS NVMe error-log table rows also need interpretation. These findings do not establish a clean bill of health or authorize reuse.

1. Use the visual Stage 0 lesson to understand the existing report; its collection is complete.
2. Resolve health/diagnostic questions and verify USB provider links, DNS operation, the unused API VIP, and the floating-IP range's DHCP/device exclusions.
3. Stage 0 Step 7 now documents the exact reset-ceph helper for all three recorded SATA SSDs. The user has confirmed old Ceph contents are disposable. The first user run stopped on node1 at the old model/capacity comparison before any removal; node2/node3 were not attempted. The corrected retry is pending; live guards and per-node command/serial confirmation still run before each removal. Keep later disk reuse conditional on its health review.
4. Fill private/lab.yml and use the staged commands in README.md. Hermes remains intact.

The storage-target helper provisions only an unowned blank disk and refuses old Ceph/LVM/filesystem signatures. The separate reset-ceph helper removes only the three recorded old Ceph allocations, defaults to plan-only, requires exact host/disk/ownership/current-use checks and per-node approval for apply, and refuses new Cinder ownership. This implementation has local guard/transport validation; the supplied live attempt stopped before cleanup, and successful cleanup/post-check results have not yet been supplied.

Two NICs per node are part of the documented design: built-in management interfaces retain the original node IPs; actual USB MACs are known for the proposed ext0 provider interfaces. Provider link/cabling/VLAN operation remains unverified. The README execution map separates observed results, the immediate cleanup run and later steps requiring additional inputs.

## First cleanup attempt: reviewed failure

On 2026-10-21 the user ran reset-ceph against all nodes. Git update, node1 SSH and sudo succeeded. The helper stopped at `Disk model/size changed` before displaying a plan or executing removal; later nodes were skipped. No disk was erased by that attempt.

The original helper compared SMART full model names with Linux lsblk model names. The existing discovery already recorded node1 as `KINGSTON SUV400S` and node3 as `KINGSTON SA400S3`; their SMART names are longer. The source now records these fields separately, validates against the observed Linux model, and prints actual/expected values before validation. Serial, byte capacity, disk ownership and use protections remain. The original error did not expose observed capacity; it remains a live check on retry.
