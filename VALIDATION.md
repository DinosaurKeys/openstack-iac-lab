# Validation and deployment status

This repository contains implementation code and learning guides. The user has completed the three Ubuntu reinstalls, basic discovery, privileged storage collection, exact old-Ceph removal on all three nodes, and passive network inspection. OpenStack deployment remains untested. Generated examples are not claimed as observed deployment results.

## Checked locally

- Parsed YAML, JSON, Python, and Terraform/HCL source and examples.
- Checked relative Markdown links and code-fence balance.
- Checked all Ansible playbooks with ansible-playbook --syntax-check.
- Exercised input guards for preserved node addresses, duplicate provider MACs, reserved floating addresses, and overlapping workload networks.
- Exercised storage guards for wrong serials, mounted OS descendants, existing Ceph signatures, and partitioned/nonblank disks.
- Ran 55 tests: 49 input/storage/confirmation checks and six terminal-driven integration cases. Disk reads/actions are fixtures or recorded mocks; no real disk operation is performed.
- Added regression coverage for the actual Linux model strings from all three nodes, rejection of unrecorded prefixes, diagnostic values before a model stop, and exact byte-capacity mismatch messages. Model/capacity failures still reject apply before any mutation or confirmation.
- Tested the actual wrapper and real Python input through a pseudo-terminal with simulated SSH: full phrases reach all three nodes, a partial ERASE can be corrected, and cancellation/EOF/three mismatches stop without a disk command. Plan-only mode visits all three without asking for approval.
- Compared LV aliases by their canonical device paths: a /dev/mapper name must resolve to the same device as the recorded /dev/VG/LV path. Regression fixtures accept that same-device alias and reject an unrelated LV; ownership checks remain exact.
- Checked shell syntax and generated inventory membership.
- Checked the consolidated storage collector with simulated SSH and diagnostic commands, including all-node collection, report privacy, optional tool installation, and continuation after connection/SMART flags. This is a local check, not real disk-health validation.
- Checked explicit node1/node2/node3/all selection, invalid target rejection, and the explanatory message for SMART command exit 4 with simulated commands.
- Checked the new reset-ceph SSH wrapper with eight isolated simulated runs: target selection, remote Python quoting/compilation, preserved terminal input, apply/plan arguments, private reports, invalid inputs and stop-on-first-failure behavior. No SSH connection or disk command executed in these checks.

The health evidence below comes from the user's earlier check-storage.sh all-node run. That collector's newer node selector, wider table and explanatory message have local simulated checks. The separate reset-ceph.sh cleanup has since completed on the real lab, as recorded below.

GitHub Actions independently runs source checks and native Terraform provider validation without lab credentials. Read its actual run result; the presence of a workflow file is not a passing result.

## Requires the real lab

The following are intentionally not claimed as tested: Cinder VG provisioning, resolution of health/diagnostic findings, new SMART self-tests, NIC driver/link behavior, Netplan application, Kolla container startup, MariaDB/RabbitMQ quorum, volume attachment, PostgreSQL data migration, application HTTP behavior, monitoring scrapes, alert firing, and controller failover.

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
3. The latest combined cleanup report records CLEANED for all three SATA disks, no detected signatures/PV/children and unchanged Ubuntu backing. Cleanup is complete. Health/diagnostic review and later Cinder VG provisioning remain separate.
4. Fill private/lab.yml and use the staged commands in README.md. Hermes remains intact.

The storage-target helper provisions only an unowned blank disk and refuses old Ceph/LVM/filesystem signatures. The separate reset-ceph helper removes only the three recorded old Ceph allocations, defaults to plan-only, requires exact host/disk/ownership/current-use checks and per-node approval for apply, and refuses new Cinder ownership. This implementation has local guard/transport validation; the latest live run completed removal and passed post-checks on all three recorded SATA disks. This does not claim that the Cinder VG was provisioned or the hardware-health findings resolved.

Two NICs per node are part of the documented design: built-in management interfaces retain the original node IPs; actual USB MACs are known for the proposed ext0 provider interfaces. The new report confirms management links at 1 Gb/s full duplex, but provider interfaces remain administratively DOWN and their cable/carrier/VLAN operation is unverified. The README execution map records the completed cleanup, current network inspection and later steps requiring additional inputs.

## First cleanup attempt: reviewed failure

On 2026-10-21 the user ran reset-ceph against all nodes. Git update, node1 SSH and sudo succeeded. The helper stopped at `Disk model/size changed` before displaying a plan or executing removal; later nodes were skipped. No disk was erased by that attempt.

The original helper compared SMART full model names with Linux lsblk model names. The existing discovery already recorded node1 as `KINGSTON SUV400S` and node3 as `KINGSTON SA400S3`; their SMART names are longer. The source now records these fields separately, validates against the observed Linux model, and prints actual/expected values before validation. Serial, byte capacity, disk ownership and use protections remain. The original error did not expose observed capacity; the later node1 retry confirmed the expected 240,057,409,536 bytes.

## Corrected retry: checks passed, confirmation cancelled

The user's next 2026-10-21 report shows node1's Linux model KINGSTON SUV400S, serial 50026B7766070422 and byte capacity 240057409536 matching the recorded target. Ubuntu was traced to /dev/nvme0n1. The helper passed all target, ownership and current-use checks and displayed the removal commands. The entered confirmation was ERASE instead of the required full host/serial phrase; it cancelled before any removal command. Node2/node3 were not attempted. This verifies node1 pre-removal checks in that snapshot, not a completed cleanup or a health certification.

The Stage 0 lesson now explains sequential all-node selection, stop-on-cancellation behavior and the exact per-node confirmation phrases. That documentation update left the script unchanged. The later prompt revision is recorded below.

## Repeated partial response: prompt revised

The latest user report again passed node1 checks, then the old one-attempt prompt received only ERASE and cancelled. No removal occurred; node2/node3 were skipped. The report does not show a complete phrase being received.

The prompt now prints the required full line separately, allows three attempts, and supports explicit cancel or an empty response. EOF has an explanatory stop. Exact node/serial approval and the post-confirmation device recheck remain required. The wrapper announces the selected order and current node number. All 55 local tests passed, including six pseudo-terminal tests of the actual wrapper/helper with mocked SSH and disks. This does not claim real SSH-server behavior or successful real cleanup.

## Completed live cleanup

The user's 2026-10-21 combined report records node1/node2/node3 COMPLETED and RESULT CLEANED. Each exact target passed the identity/ownership/use checks, received its full host/serial approval, and completed signature/LV/VG/PV removal. Each post-check found no detected SATA signatures/PV/children and unchanged Ubuntu backing on NVMe. Lock messages ended OK and the affected commands succeeded; no identity for the other lock holder was established.

No Cinder VG or new filesystem was created by the cleanup. Node1/node2 SATA stay unallocated in the design; node3 is the proposed later Cinder host. Earlier failed/cancelled attempts above are historical and are superseded by this successful run.

## Next lesson: passive network inspection

The new check-network wrapper collects Hermes route selections and all three nodes' actual NIC MACs, administrative state, carrier/speed/duplex, driver, addresses, routes, configured DNS and a bounded Ubuntu hostname lookup. It uses joe SSH without sudo and has no interface-enabling, address-setting, Netplan or package-install action. It saves private reports and continues after observation/connection failures.

Seven isolated simulated checks passed for target selection, quoted remote Bash syntax, private report modes, continuation after review/SSH errors and invalid options. Shell/source/link checks passed. The network script has now run on the lab, as recorded below. USB active-link testing and switch/VLAN connectivity remain pending.

## Observed network results

The user's 2026-10-21 report reached all three nodes. Recorded management and USB MACs matched. Each built-in e1000e NIC is admin/operational UP with carrier 1, 1000 Mb/s full duplex and the preserved .200/.201/.202 address. Each r8152 USB NIC is administratively/operationally DOWN with no host address; sysfs carrier/speed is unavailable. Each node has gateway/DNS 192.168.0.1 and successfully resolved archive.ubuntu.com from network DNS data. No node interface/address/route/Netplan changes occurred.

The report also contains ethtool netlink permission denials. The collector ran unprivileged; some get requests require privileges, but this report does not identify the denied subrequest. USB ethtool output shows Speed 1000Mb/s alongside Link detected no and admin DOWN. A usable gigabit provider link has not been established. The existing collector explicitly marks the DOWN provider state REVIEW.

Hermes routes to the three nodes using ens33, local source 192.168.162.130 and next hop 192.168.162.2. NAT versus another routing arrangement has not been inferred from that route alone. Router DHCP exclusions, VIP reservation, USB cable/switch/VLAN placement and active provider-link verification remain open. The original uploaded report is unchanged and is not published to the repository.
