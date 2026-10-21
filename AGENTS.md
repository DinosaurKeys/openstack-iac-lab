# Project instructions for Codex

## Objective

Build a documented three-controller OpenStack lab on Ubuntu 24.04. Teach Ansible roles, Terraform modules, app deployment, and monitoring. Use Cinder LVM, not Ceph. Preserve node1 192.168.0.200, node2 192.168.0.201, node3 192.168.0.202, and API VIP 192.168.0.100. Preserve Hermes and its existing installation. Use the confirmed two-NIC design: built-in enp0s31f6 retains management IPs; each actual USB NIC is intended for the MAC-matched ext0 provider interface without a host IP. Joe confirms both NICs connect to the same mini switch/LAN 192.168.0.0/24, with DHCP 192.168.0.2–149. USB carrier and switch/VLAN operation are not yet measured. The .100 reservation's exact DHCP binding/exclusion and current lease need clarification. Floating pool .150–.199 is proposed only, pending other static allocations; .150–.250 is not a verified free block and includes the nodes.

## Working method

1. Read README.md and the stage being changed. Inspect actual files/output before drawing conclusions.
2. Separate observed facts from proposed values and unknowns. Do not invent device identities, NIC MACs, credentials, available addresses, capacity, or successful results.
3. Explain cause and effect before recommending a change. Keep the lesson short and concrete.
4. Edit files in this repository, show a diff, and run relevant local validation.
5. The user runs infrastructure commands unless they explicitly authorize Codex to execute the particular change. Approval to write documentation is not approval to wipe disks, change Netplan, deploy OpenStack, or apply/destroy Terraform workloads.
6. Before any destructive disk command, identify the host, stable /dev/disk/by-id path, serial, size, parent devices, mounts, and ownership. Obtain approval for the exact command and target. There are no pre-approved disk wipe commands in this repository.
7. Keep Kolla prechecks enabled. Do not turn a failed LVM/HA precheck into a claimed success by bypassing it.
8. Keep credentials and Terraform state out of Git. Do not print secret-bearing files. Do not access browser sessions, email, or unrelated directories for this project.
9. Record actual execution results and unresolved problems. Never describe draft code as a completed deployment.
10. Use six core guides. Add detail within the relevant guide instead of creating a chapter for every command.
11. Start each teaching step by naming the current stage and explaining the cause shown by the actual evidence. Consolidate repeated node operations in scripts/ or Ansible roles, explain their inputs/effects/output, then give one stage command. Review its report together before moving on. Avoid repeated per-node command lists and large terminal paste blocks; learning the system is the objective.
12. Publish each step's lesson in the relevant guide before recommending its execution, and link directly to that section in chat. Explain the concepts, cause, script behavior, changes, outputs and result interpretation. After a run, document the reviewed findings and remaining unknowns without publishing secrets or raw private reports. A script and a chat summary alone do not satisfy this requirement.
13. Teach as a visual workbook for a Linux beginner: architecture first, one concept per step, short tables and annotated output excerpts. Keep advanced explanations and old command references in collapsible sections. Prefer one script with explicit node selection over separate copies or repeated SSH commands. Interpret supplied output before asking for another run; show observed fact → meaning → remaining uncertainty. Keep paragraphs short.

These instructions express the workflow; they are not a security sandbox. Codex permissions and OS/network access must also be configured appropriately.
