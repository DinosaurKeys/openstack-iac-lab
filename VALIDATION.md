# Validation and deployment status

This repository contains implementation code and learning guides. The user has completed the three Ubuntu reinstalls, basic discovery, privileged storage collection, exact old-Ceph removal, passive network inspection, temporary USB link measurement/restoration, Hermes tools, SSH/Python tests, Ansible sudo identity checks and the common-role preview on all three nodes. A real common-role run reached node1 and verified its package/service/IP baseline, then stopped at duplicate hostname resolution. Overall common-role verification and OpenStack deployment remain incomplete. Generated examples are not claimed as observed deployment results.

## Checked locally

- Parsed YAML, JSON, Python, and Terraform/HCL source and examples.
- Checked relative Markdown links and code-fence balance.
- Checked all Ansible playbooks with ansible-playbook --syntax-check.
- Exercised input guards for preserved node addresses, duplicate provider MACs, reserved floating addresses, and overlapping workload networks.
- Exercised storage guards for wrong serials, mounted OS descendants, existing Ceph signatures, and partitioned/nonblank disks.
- Ran 147 tests: 55 input/storage/confirmation/terminal checks, 31 USB link checks, nine Hermes recovery checks, 17 SSH access checks, eight administrator-access checks, nine common-role preview checks, nine common-role apply checks and nine hosts-rendering checks. Hardware reads/actions, installers and SSH connections in these tests are fixtures or recorded mocks; no actual package, disk or NIC operation is performed. Native hosts tests write temporary fixture files only.
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

The following are intentionally not claimed as tested: Cinder VG provisioning, resolution of health/diagnostic findings, new SMART self-tests, sustained USB NIC stability/throughput, switch/VLAN forwarding, Netplan application, Kolla container startup, MariaDB/RabbitMQ quorum, volume attachment, PostgreSQL data migration, application HTTP behavior, monitoring scrapes, alert firing, and controller failover. Basic physical USB negotiation and restoration have passed on the lab, as recorded below.

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

Two NICs per node are part of the documented design: built-in management interfaces retain the original node IPs; actual USB MACs are known for the proposed ext0 provider interfaces. Passive inspection confirmed management links at 1 Gb/s full duplex. The subsequent temporary USB test also confirmed carrier 1 and 1000 Mb/s full duplex on all three adapters, then verified restoration to DOWN and unchanged management. VLAN forwarding and workload traffic remain untested. The README execution map records these completed steps and the remaining inputs.

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

Seven isolated simulated checks passed for target selection, quoted remote Bash syntax, private report modes, continuation after review/SSH errors and invalid options. Shell/source/link checks passed. The passive network script and subsequent temporary USB link test have now run on the lab, as recorded below. Switch/VLAN forwarding and workload traffic remain pending.

## Observed network results

The user's 2026-10-21 report reached all three nodes. Recorded management and USB MACs matched. Each built-in e1000e NIC is admin/operational UP with carrier 1, 1000 Mb/s full duplex and the preserved .200/.201/.202 address. Each r8152 USB NIC is administratively/operationally DOWN with no host address; sysfs carrier/speed is unavailable. Each node has gateway/DNS 192.168.0.1 and successfully resolved archive.ubuntu.com from network DNS data. No node interface/address/route/Netplan changes occurred.

The passive report also contains ethtool netlink permission denials. The collector ran unprivileged; some get requests require privileges, but this report does not identify the denied subrequest. USB ethtool output showed Speed 1000Mb/s alongside Link detected no and admin DOWN; that snapshot did not establish active physical negotiation. The collector explicitly marked the DOWN provider state REVIEW. The later privileged activation measured actual carrier and speed successfully, as recorded below.

Hermes routes to the three nodes using ens33, local source 192.168.162.130 and next hop 192.168.162.2. NAT versus another routing arrangement has not been inferred from that route alone. The original uploaded report is unchanged and is not published to the repository.

## Confirmed LAN plan and temporary link test

Joe subsequently confirmed that both NICs connect to the same mini switch/LAN 192.168.0.0/24 and router DHCP serves 192.168.0.2–149. He reports a reservation at .100. Its exclusion versus MAC-binding semantics, bound device and current lease remain unknown. The proposed external allocation block .150–.199 avoids DHCP and the nodes .200–.202, but other static users are unverified. No private configuration flag or floating-pool value was automatically marked verified.

The new test-provider-link wrapper/helper defaults to plan only. Apply requires exact recorded host/management/USB identity, an unused DOWN USB interface, no addresses/routes/master/uppers, networkd unmanaged status and inactive NetworkManager. It temporarily suppresses IPv6 on that USB NIC, brings it UP, reads physical negotiation, restores DOWN and the original IPv6 setting, and compares management address identity and routes. No persistent network file or management-interface setting is written. Handled interrupts enter restoration; power loss/uncatchable kills cannot guarantee cleanup. A restoration failure is a stop, never a passing result.

The 31 new local tests cover identity/use/ownership refusals, plan without writes, gigabit/slower/missing-carrier outcomes, restoration after errors/interruption, changed-route rejection, failed-restoration rejection, remote helper quoting, all/single-node selection, private reports, continuation after a restored REVIEW and stop on a hard failure. These tests perform no real network mutation. The subsequent physical result is recorded below; VLAN forwarding and workload connectivity remain pending.

## Completed live USB link test

The user's combined report started at 2026-10-21T19:17:04Z and records node1/node2/node3 COMPLETED and LINK_OK. The recorded USB MACs matched interfaces enx00e04c557e58, enx00e04c2c1678 and enx00e04c304688 respectively. Each interface passed the networkd-unmanaged ownership guard, was temporarily enabled, and measured carrier 1, speed 1000 Mb/s and full duplex.

Each USB NIC was then set DOWN, its disable_ipv6 setting restored from temporary 1 to original 0, and the helper's final checks verified unchanged management addresses/routes. This confirms basic physical negotiation at the time of the test and successful restoration on all three nodes. It does not establish sustained throughput/stability, VLAN forwarding, persistent Netplan behavior or VM connectivity. There is no reason to repeat the successful test by default.

The Stage 0 lesson and README checkpoint now record completed physical testing and pending address-allocation facts: exact .100 DHCP exclusion/reservation binding and current lease, and other static users in proposed .150–.199. Scripts and configuration flags were unchanged by this documentation update. The private raw report is not published.

## Address-owner confirmation and next Hermes preparation

Joe reiterates that .100 is reserved and confirms no manually configured devices in .150–.199, explicitly offering .150/.151/.152. The DHCP product/device, reservation client binding and current lease are still unspecified. Final three-address versus wider-pool allocation scope remains to be chosen. No public/private config verification flag was changed.

The supplied Windows ping output for .150/.151/.152 contains only Destination host unreachable messages from .59, despite Received 4/Lost 0 summaries. There are no successful target echo replies. The report does not identify .59's role or the DHCP server, and ping cannot certify absence of offline/static ownership. The owner's allocation statement is recorded separately from that observation.

Inspection of the existing Terraform roots/modules gives a five-address external budget with all current workloads present: one first-workload router plus one VM floating IP; one app router plus one app floating IP; one monitoring floating IP reusing the app network/router. PostgreSQL has no floating IP. This is source-derived planning, not a live allocation. No Terraform/network topology changes were made for this update.

The new prepare-hermes.sh wrapper installs through the existing bootstrap-hermes.sh, records private logs/Python versions and runs doctor in the selected environment. It requires an interactive terminal on hostname hermes, stops after installer failure and never invokes SSH/node configuration or cloud deployment. Local shell/source checks and isolated simulations cover success, installation failure, doctor review and report permissions. The actual package install/dependency resolution on Hermes remains pending.

## Observed Hermes installation and PATH correction

The uploaded report started at 2026-10-21T19:47:23Z. On Hermes, APT reports 1 upgraded, 0 newly installed, 0 removed, 69 not upgraded: ca-certificates became 20260816ubuntu0.24.04.1. Git/curl/Python development and venv packages/GCC/listed libraries were already current. No full system upgrade was performed.

The project environment /home/joe/venvs/kolla-iac installed pip 26.2.2 (from 24.0), ansible-core 2.20.10, kolla-ansible 22.2.1.dev24 from the selected commit, python-openstackclient 10.4.0, PyYAML 6.0.3 and supporting dependencies, including openstacksdk 4.21.0. The dependency/collection phase then stopped with No such file or directory: ansible-galaxy. Project collections, pip-freeze reporting and doctor were not reached. This is a partial installation, not TOOLS_FOUND.

The bootstrap script called Kolla with an absolute path but had not exported the new environment's bin directory on PATH. The pinned Kolla source calls ansible-galaxy by name in a child process. The wrapper's later PATH export could not fix the earlier bootstrap call. The correction exports PATH before Kolla's install-deps. A local isolated child-command lookup simulation verifies this ordering; no real apt/pip/SSH or cloud operation is used for that check. Corrected collection installation and doctor on Hermes remain pending.

The lesson now leads with a plain-language package/purpose/location table and the observed partial result. Original installation commands are reference material, not a new retry instruction. The original uploaded report is unchanged and is not published. This run performed no node network/storage configuration or OpenStack deployment, and installed neither Codex nor Terraform.

## Next recovery: resume collections only

Joe requested the next step after reviewing the installed tools and the PATH failure. prepare-hermes.sh now accepts --resume-collections: it requires the existing Python/Kolla/Galaxy executables, exports the project environment and collections path before dependency calls, installs Kolla/project collections, checks Python dependencies, records versions, lists collections and runs doctor. Resume performs no APT operation, venv creation, pip install, sudo, SSH or cloud deployment. Full setup remains available without that flag.

The script writes a private short hermes-tools-summary.txt plus the full report/history, including stop/review outcomes. Nine new fixture tests exercise resume command selection and the real child PATH lookup, installation/check failures, a missing existing executable, doctor review, wrong host/arguments, preserved full mode and report permissions. No actual installer/package operation is executed in those tests. The current guide is a short recovery lesson; previous architecture/installation details are folded into reference material. Corrected collection installation and doctor on real Hermes remain pending.

## Completed live Hermes tool setup

The user supplied the resume-collections summary beginning 2026-10-21T20:35:49Z. Kolla collections, project collections, Python dependency check and installed-collection listing all report COMPLETED. The Python version manifest was recorded. Doctor found all eight executables and ended with RESULT TOOLS_FOUND.

Python3, ansible-playbook, ansible-inventory, kolla-ansible and openstack resolve under /home/joe/venvs/kolla-iac/bin. SSH/Git resolve at /usr/bin/ssh and /usr/bin/git; Terraform is present at /usr/bin/terraform. This recovery did not install Terraform. Its actual version/provider behavior and exact resolved collection versions are not supplied in the short summary, so no new claims about those were inferred.

The PATH-related collection failure is resolved for this run. Tool preparation is complete; no repeat installation is needed. The report confirms successful collection/check commands and executable discovery, not node SSH, OpenStack API reachability or deployment. Node/cloud configuration remains unexecuted by this tool-preparation step. The README and Stage 1 lesson now record the reviewed live success. Scripts were unchanged by this documentation update.

## Next lesson: dedicated SSH-key access

prepare-ssh.sh defaults to verification; --apply creates/reuses ~/.ssh/openstack-iac-lab, loads the key into the caller's agent for four hours, verifies agent key usability and installs only its public key with ssh-copy-id. It selects only joe on the fixed node addresses, keeps host-key checking, verifies fresh SSH with password fallback/multiplexing disabled, and checks hostname/user/management address. A generated SSH-only test inventory runs Ansible ping without sudo. Sudo/network/storage/server policy is not changed, and existing key files are never overwritten. Reports and test inventory are private under build; the private key stays under the user's .ssh directory.

The tracked preparation inventory variables and Kolla inventory renderer now select this dedicated key and retain strict host-key checking. The configure generator carries the preparation variables into generated host inventory; VM-workload key settings are separate. Stage 2's standalone ping example explicitly disables sudo.

Fourteen isolated fixture tests cover all/single-node selection, public-only copy arguments, actual quoted remote identity checks, password-fallback/connection-reuse options, create versus verify mode, incomplete/multiple-key rejection, missing agent/key mismatch, sequential stop after a copy failure, wrong host/arguments, Ansible failure, private reports and key selection in both inventory paths. They execute no real SSH/agent/key-copy or key generation. The first live run has now reached key creation but stopped during unlock, as recorded below; no SSH_READY result has been claimed.

## Observed SSH stop before node access

Joe supplied the SSH summary beginning 2026-10-21T21:09:40Z, selecting all nodes with apply enabled. Create dedicated key reports COMPLETED; Unlock key for four hours failed. Source order places ssh-add before agent usability verification and the node loop. No public-key installation, fresh node login or Ansible ping was reached in this run. The generic stop message about earlier public-key additions does not establish that any additions occurred.

The supplied summary has no underlying ssh-add error or numeric exit status. No passphrase, permission or agent diagnosis is established. The Stage 1 lesson now records this partial result and gives one read-only sed command to display the unlock section of the existing full report. Preserve the existing key and review that error before any retry. README and the agent checkpoint point to that lesson. This update changes documentation only; scripts, keys, nodes and cloud configuration are unchanged. The raw report and private key are not published.

## Empty unlock log and reporting correction

Joe ran the requested sed extraction. It printed only the unlock heading and STOP line, with no diagnostic text. This confirms that reading the saved section cannot supply the missing cause. OpenSSH documents that passphrases are read from the terminal; the saved report need not contain those prompts. The original wrapper also omitted exit status and used the same public-key-additions sentence for every phase. Neither observation establishes the cause of Joe's failure.

prepare-ssh.sh now captures Bash PIPESTATUS immediately on failure and records command_exit separately from log_exit. It counts public-key installation attempts and explicitly reports when none were attempted. Three added fixture tests cover a silent unlock failure after key creation, a load-time agent failure after the initial agent check, and a log-command failure despite successful unlocking. They check stderr preservation, distinct exit codes, no node/Ansible calls and no false SSH_READY claim. Existing copy-failure coverage checks that additions are reported as retained when copying was attempted. These are local simulations, not a diagnosis of the live agent.

The Stage 1 lesson replaced the exhausted log extraction with a direct verbose ssh-add invocation and an immediate exit-code print. It explained the local four-hour agent effect, key-passphrase prompt and status meanings. No new script or chapter was introduced. That check was subsequently run on Hermes, with the result recorded below; no key/agent/node action was run by Codex and no raw private report or key content is published.

## Observed passphrase prompt and direct exit 1

Joe's direct ssh-add -v -t 4h invocation displayed Enter passphrase for /home/joe/.ssh/openstack-iac-lab, then ssh-add exit=1. No Identity added result, Bad passphrase retry or other diagnostic was supplied. This establishes a direct command failure after reaching passphrase entry; the script's logging pipeline is no longer involved in that check. It does not establish what Joe typed, an incorrect passphrase, or key corruption. The direct check made no node connection.

Reviewed upstream OpenSSH 9.6 ssh-add.c checks for an empty passphrase and returns failure without another error; a wrong non-empty passphrase normally returns to a retry prompt. readpass.c can return an empty string after an input-read failure. Empty/cancelled input therefore fits the visible result, but it remains an inference rather than a confirmed cause. The installed Hermes build was not newly identified by this output.

The lesson recorded the observed result and asked what was entered, without requesting the passphrase itself. Earlier diagnostics were folded into reviewed history. Joe subsequently clarified that the passphrase is unknown, as recorded below. That checkpoint update changed documentation only; it did not claim a new fixture-test run or live SSH success.

## Forgotten passphrase: preserve the old pair and use a new filename

Joe confirms that he does not remember choosing the key passphrase and had tried the Ubuntu account password/Enter. There is no need for another password guess or the same diagnostic. OpenSSH documents that a forgotten passphrase cannot be recovered and requires a new key/public-key installation.

The existing prepare-ssh.sh now selects ~/.ssh/openstack-iac-lab-ansible, prints that path in the summary, and explains the creation/repeat/load prompts. The original ~/.ssh/openstack-iac-lab pair remains at its existing names; no move, overwrite, deletion or passphrase change is issued. Tracked preparation variables and the Kolla inventory renderer select the same new identity; SSH test inventory derives it from the script. Workload VM keys are separate and unchanged.

The SSH fixtures now retain an existing forgotten pair alongside the selected key and verify its exact bytes remain intact on every run, its contents do not enter the report and its paths are never passed to SSH tools. Creation coverage checks the new filename, existing-pair coverage checks reuse, and tracked/Kolla inventory checks require the new identity. The recovery still uses the existing all-node script, public-only copy, strict host-key checks, no-password fresh login and Ansible ping without sudo. It installs no node packages and changes no disk/network/sudo policy. The subsequent live result is recorded below; local fixtures alone do not establish SSH_READY.

Stage 1 now leads with the recovery, file-effect table, exact prompt-to-credential table and one command block. Earlier diagnostic history was condensed. The report is reviewed before any host configuration. No keys, raw private reports or passphrases are published.

## Completed live SSH access and beginner lesson revision

Joe supplied the full terminal output and short summary for the run starting 2026-10-22T06:33:11Z, after updating from 613507a to 8c6d9ec. A new ED25519 pair was saved at /home/joe/.ssh/openstack-iac-lab-ansible and .pub. The agent accepted it with a 14400-second lifetime, and its public-key usability check completed. Each of node1 192.168.0.200, node2 192.168.0.201 and node3 192.168.0.202 reports one public key added and a successful fresh key-only login with expected account, hostname and management address. All three Ansible Python tests returned SUCCESS, pong and changed=false. The final live result is SSH_READY for all.

That establishes SSH access as joe and usable remote Python, without sudo in the test inventory. It does not establish Ansible privilege escalation, new host configuration, cloud deployment or the private file's encryption setting. No unlock passphrase prompt appears in the supplied new-key log; this is consistent with an empty passphrase, but typed input and file encryption were not inspected. The four-hour lifetime applies to the agent's copy and does not expire key files or node authorized-key entries. changed=false describes only the ping test; the preceding public-key installation changed authorized_keys.

At Joe's request, the Stage 1 lesson now starts with the private/public key model and a Mermaid SSH/Ansible flow, rather than the completed recovery. It distinguishes optional passphrase entry during key creation from cancellation at an existing protected key's unlock prompt, explains each of the four commands and interprets the live output. The same public key was installed on all three; private-key use remains on Hermes. Old recovery links are retained inside a collapsed completed reference. README and the agent checkpoint record success. This revision changes documentation only; the existing 112-test result is not presented as a new run. Raw private reports, private keys and passphrases are not published.

## Next host-preparation check: Ansible administrator access

check-admin.sh uses the existing project environment and tracked preparation inventory without requiring private/lab.yml, generating cloud configuration or changing verification flags. It resolves and validates exactly the preserved three node addresses, joe account and selected key. It then invokes check-admin.yml separately per selected node with sudo/root, an individual become-password prompt and key-only SSH. The only node commands are id -u and hostname -s, marked unchanged; the playbook asserts UID 0 and the expected hostname. Ansible temporary files and normal authentication logging can occur, but no host configuration/package/network/disk/sudo-policy task is included.

The wrapper records per-node success/failure and one private short summary plus the full log/history. Ordinary failed checks continue to later nodes; cancellation stops. SSH-password fallback stays disabled and host-key checking enabled. Passwords are read interactively by Ansible and not added to command arguments, inventory or reports. No installed tool or native sudo policy is modified by this check.

Eight fixture tests exercise all/single-node selection, separate become prompts per invocation, non-root and wrong-hostname rejection using the actual YAML assertion expressions, connection failure without false success, continuation, cancellation, inventory address/key rejection, wrong client/arguments and private report permissions. Fixture Ansible commands use Jinja2 already supplied by ansible-core; tests perform no real SSH or sudo. Native Ansible syntax and inventory parsing are checked locally without contacting lab nodes. This does not establish live administrator access; the user's report remains pending.

The Stage 2 guide now leads with the short sudo lesson, file map, identity-read table, diagram, one script command and result interpretation. Later host-role/Netplan command blocks are folded into reference. Stage 1 and README link directly to the current check. The next common-role installation lesson will explain package names and effects before apply; no package installation is suggested by this check.

## Latest SSH confirmation; administrator check still pending

Joe supplied build/ssh-access-summary.txt starting 2026-10-22T09:45:00Z. The selected key remains /home/joe/.ssh/openstack-iac-lab-ansible with fingerprint SHA256:OMSfEV5sjqG70NZvJB9whv54Oac1rzMezHgolaTKMmM. Unlock and public-key usability verification completed. Public-key installation and fresh key login completed for node1, node2 and node3; the Ansible SSH/Python check completed. The final result is again SSH_READY for all; sudo policy is unchanged.

The later summary does not contain a key-creation phase or an added-key count. It does not establish new key generation, Ansible sudo access or a cloud deployment. README, Stage 1 and the agent checkpoint now record this confirmation and retain the published administrator-access check as the next step. This update changes documentation only; no script or infrastructure action was executed, and the existing 120-test result is not presented as a new run. No raw private report, private key or password is published.

## First live administrator check: node1/node3 passed, node2 password rejected

Joe supplied the administrator-access report starting 2026-10-22T10:04:51Z. Local preparation-inventory validation passed. Node1 192.168.0.200 and node3 192.168.0.202 each verified effective UID 0 and the expected hostname, with ok=4, changed=0, unreachable=0 and failed=0. Node2 192.168.0.201 failed the first task with Incorrect sudo password, changed=0, unreachable=0 and failed=1. Its identity commands did not complete. Ansible returned 2 while the log command returned 0. Checks continued to node3 and the combined result correctly ended REVIEW.

The evidence establishes successful Ansible sudo access on node1/node3 and a sudo-authentication rejection on node2. It does not identify what was typed or establish the cause beyond the reported authentication failure. The documented next action uses the unchanged check-admin.sh wrapper with --node node2 and node2's Ubuntu joe password at BECOME password. It repeats only identity reads; the selected-node result must be reviewed alongside the earlier node1/node3 passes. Latest report files describe the latest selection; timestamped history retains the previous all-node run. No package, sudo-policy, network, storage or cloud configuration change is requested by this check.

README, both relevant guides and the agent checkpoint now reflect the partial live result. This is a documentation-only update; no new fixture-test run or live retry is claimed, and no raw private report or credential is published.

## Completed live administrator access on all three nodes

Joe supplied the all-node run starting 2026-10-22T10:14:57Z. Node1 192.168.0.200, node2 192.168.0.201 and node3 192.168.0.202 each verified effective UID 0 and the expected hostname. Every recap reports ok=4, changed=0, unreachable=0 and failed=0. Both terminal output and the summary end ADMIN_ACCESS_OK for all. This establishes successful SSH plus Ansible sudo identity checks at that time. The earlier node2 rejection is resolved in the later run; the output does not establish why the earlier password entry was rejected. No host preparation or cloud deployment is inferred from these identity reads.

## Next lesson: preview the common role before installation

The current Stage 2 workbook, linked from Stage 1 and README, now explains every declared package, system installation location, desired hostname, marked hosts block and Chrony behavior. Completed sudo/key recovery is folded into reference. The seven packages remain declared in group_vars; no package list expansion, network change or disk allocation is introduced.

The new preview-common.sh wrapper uses the existing project environment and tracked preparation inventory, validating the fixed three IPs, joe account and selected key. It always invokes base.yml with --check --diff, sudo/root and one password prompt per selected node. It saves private combined output, a short summary and timestamped history. A successful Ansible exit also requires the playbook's node-specific preview completion marker; missing/skipped-host output cannot claim success. Ordinary failures continue to later previews; cancellation stops. The wrapper has no apply mode.

The common role disables automatic python3-apt helper installation. For preview only, it reads service facts and defers the Chrony enable/start check if its unit is absent or not found; the explicit message describes that limitation. Existing units are checked in Ansible check mode. A real run still requires enabling/starting Chrony after package installation. Nine isolated fixture tests cover preview-only flags, separate/all/single selections, private reports, sudo rejection/continuation, cancellation, missing completion marker, inventory mismatch and invalid/nonterminal execution. The actual YAML service conditions are evaluated for absent/not-found/present units in preview and normal modes. Fixtures do not contact lab nodes or execute APT/services. The real preview and common-role application remain pending.

Local validation for this change passed: all 129 tests, native syntax checks for all seven Ansible playbooks, shell syntax, repository source/relative-link checks, workbook details/fence structure and Bash examples. The upstream Ansible check/diff and APT documentation and Ubuntu time-client guidance were reviewed. These checks establish source/fixture behavior, not a live preview, package transaction, service startup or clock synchronization.

## Completed live common-role preview

Joe supplied the common-preview report starting 2026-10-22T10:35:36Z. Preparation-inventory validation passed. Each of node1 192.168.0.200, node2 192.168.0.201 and node3 192.168.0.202 passed the OS assertion and predicted chrony plus tzdata-legacy installation, removal of systemd-timesyncd and the same marked hosts block containing the three preserved mappings. Hostname tasks reported ok. Each missing Chrony unit caused the enable/start check to be skipped and explained as DEFERRED. Every recap is ok=8, changed=2, unreachable=0, failed=0, skipped=1; each completion marker and final COMMON_PREVIEW_OK for all are present.

The two predicted changed tasks are APT and blockinfile, not a count of installed packages/files. APT proposed 0 upgrades, with 27 packages not upgraded on node1/node3 and 28 on node2. This evidence does not establish an actual package installation, service startup, time synchronization or the contents of hosts lines outside the displayed diff. No package versions are inferred. The reviewed result is now documented in the current apply lesson; completed preview and credential lessons are folded into reference.

## Next lesson: apply and verify the common role

The new apply-common.sh requires --apply, uses the existing project tools/preparation inventory/key, runs base.yml once per selected node with an individual sudo prompt and stops at the first task, verification, logging or completion-marker failure. It records private common-apply reports separately from preview reports. Completed changes remain on failure; no automatic rollback is claimed. Missing markers cannot claim success even if Ansible returns zero.

Changed hosts files now receive dated backups. Normal base.yml execution includes verify-common.yml; check mode skips that include. Verification requires the seven packages, expected hostname, preserved management IP/prefix, exact three IPv4 name mappings, enabled/running Chrony and successful bounded waitsync, tracking and source commands. The latter two commands are diagnostic reads; their errors and waitsync failure are followed by an explicit failing assertion. A success marker is emitted only after all verification assertions. Waitsync uses twelve checks two seconds apart, without extra correction/skew thresholds; it does not certify an accuracy bound.

Nine new isolated tests use the real wrapper and evaluate the actual YAML assertion expressions with fixture states. They cover all/single selection, explicit apply requirement, sudo failure, cancellation, missing marker, inventory refusal, invalid/nonterminal execution, private logs and rejection of missing packages, wrong hostname/IP, stopped Chrony, extra resolver addresses and unsuccessful synchronization. The fixtures perform no SSH, APT or service operation. Real common-role apply and its resulting state remain pending.

Local validation passed: all 138 tests, syntax checks for all seven playbooks, shell/source/relative-link checks and workbook command examples. Native Ansible also evaluated the real verification assertions against four local fixture cases: valid state, wrong management IP, extra resolver address and failed synchronization. Those runs include controller-side assertions/debug output only; they perform no SSH or node/system modification. Synchronization evidence preserves stdout, stderr and return codes before the final assertion. Upstream APT, Chrony waitsync and Ubuntu package/time-client sources were reviewed; no installed node versions or real synchronization were inferred from them.

## Observed common-role stop: duplicate node1 resolution

Joe supplied the real apply report starting 2026-10-22T12:12:23Z. Preparation-inventory validation passed. On node1 the package, hostname, hosts-block and Chrony service tasks reported ok; the installed-baseline assertion verified declared packages, expected hostname, preserved management IP/prefix and enabled/running Chrony. Resolver lookup returned both 127.0.1.1 and 192.168.0.200 for node1. The strict assertion at verify-common.yml line 41 failed as intended; lookups of node2/node3 performed on node1 matched their expected management addresses. Node1's recap is ok=13, changed=0, unreachable=0, failed=1, skipped=4. The wrapper recorded ansible_exit=2, log_exit=0 and stopped before node2/node3.

This establishes the existing baseline on node1, not a new package installation in that reported run. Package versions were not printed before the stop, and clock synchronization checks were not reached. No successful application on node2/node3 is inferred. The resolver result is observed; the complete hosts-file layout was not supplied. The original role managed its new block without retiring the selected node's pre-existing loopback alias. Bash's separate Permission denied message came from attempting to execute the private text report; cat read it successfully.

## Hostname correction with the strict resolver check preserved

The common role now imports hosts.yml, reads the actual hosts file and renders one backed-up candidate through a role-local filter/template. The fixed management block is maintained once. Only exact aliases matching the selected lab node are removed from 127.0.1.1 records; other aliases, comments, localhost/IPv6 lines and unrelated entries are preserved. A now-empty record is removed while its attached comment is retained. Incomplete, repeated or reversed lab markers are rejected. Existing file permissions are preserved. verify-common.yml and both all-node wrappers are unchanged; an unresolved extra address still fails verification.

Nine new tests cover the reported duplicate, all selected nodes, alias/FQDN/comment preservation, repeated/case-variant aliases, unrelated entries and literal template-like comment text, block replacement, newline/repeatability and malformed marker/unknown-host refusal. A native Ansible fixture runs the real role-local filter/template and hosts tasks against a temporary file: check mode predicts the change without writing, apply creates an exact pre-change backup and preserves mode 0640, and a second apply reports changed=0 with identical content and no additional backup. No real node or system hosts file is accessed.

Local checks passed: all 147 tests and native syntax checks for all seven playbooks. Repository source/link checks and command examples are checked before publication. README, Stage 1, Stage 2 and the agent checkpoint record the observed stop and documented resume command. Recovery on the real nodes, node2/node3 application and actual clock synchronization remain pending. No raw private report or credential is published.

## Simplified learning route after the preparation feedback

Documentation-only change: README now has one current checkpoint and the six-stage learning path. Stage 1 contains the active route: common baseline, one configuration review, network/LVM preparation, Kolla phases and service/API checks. Completed SSH/tool lessons are collapsed reference. Stage 2 explains reusable roles rather than hosting Stage 1's active recovery instructions. Stage 0 redirects to the actual current stage. No script, role, package list, verification assertion or infrastructure action is changed.

The initial external pool is scoped to Joe's explicitly offered .150–.152. That supports the first workload; full first/app/monitor coexistence still needs five addresses. Wider allocation is deferred rather than invented. The VIP reservation binding/current lease and node3 disk-health reuse review remain unresolved. Hosts-only configuration excludes future HCP/Terraform/app requirements. No verification flag is set by this documentation change.

While this documentation change was in progress, Joe supplied the successful corrected application beginning 2026-10-22T12:31:45Z; it supersedes the earlier stop. The new result and simulation are recorded below. Kolla deployment remains pending. Stage 1's finish is now explicitly Kolla/API/service verification; VM networking and cross-compute Cinder acceptance follow the first workload and remain required before database deployment. Prior fixture tests are not represented as a new run or live success.

## Completed real common-role application on all three

Joe's attached common-apply report starts 2026-10-22T12:31:45Z. Node1 reports ok=23, changed=1, unreachable=0, failed=0, skipped=3. Node2/node3 each report ok=23, changed=2, unreachable=0, failed=0, skipped=3. All three final node markers and APPLIED_AND_VERIFIED lines are present; the combined result is COMMON_APPLIED_OK for all. This resolves the earlier duplicate resolution failure. No common/access retry is requested.

Node1's hosts file changed, removing 127.0.1.1 node1; the baseline packages were already present. Node2/node3 each installed chrony plus APT's tzdata-legacy, removed systemd-timesyncd, removed their own loopback hostname alias and added the three management mappings. Their transactions show 0 upgraded, 2 newly installed, 1 removed and 28 not upgraded. The hostname tasks reported ok. Each hosts backup path was shown. All baseline and strict resolver assertions passed, with the management IP/prefix preserved.

All three report these seven versions: curl 8.5.0-2ubuntu10.16; git 1:2.43.0-1ubuntu7.4; jq 1.7.1-3ubuntu0.24.04.2; lvm2 2.03.16-3ubuntu3.2; smartmontools 7.4-2build1; chrony 4.5-1ubuntu4.2; python3 3.12.3-0ubuntu2.1. Chrony service assertions and waitsync/tracking/sources commands passed on all three. The report shows synchronization, not a certified accuracy bound: waitsync deliberately has zero correction/skew thresholds. This evidence does not establish persistent network configuration, a Cinder VG or running OpenStack.

## Local simulation requested before the next lab action

Reran the existing suite: all 147 tests passed in 31.300 seconds, without skips. This includes the real role-local hosts filter/template/tasks executed by native Ansible against a temporary file: preview without writing, real apply with exact backup and permission preservation, and an unchanged repeated apply. Wrapper fixtures exercise selected/all-node processing, actual YAML verification assertions and stop-on-failure boundaries. They perform no lab SSH/APT/service operation.

A separate disposable project copy exercised the actual configure.py --hosts-only generator with the full pinned upstream multinode sample retrieved at 15ce36696a21356eb59abb4473e210f13cf7c98c. An empty template and missing review flags were refused before file generation. The successful fixture explicitly supplied synthetic acceptance flags; HCP organization remained null and no Terraform files were generated. These flags do not establish any real VIP/DHCP or disk-health approval. Generated YAML candidates were mode 0600.

Native Ansible resolved the generated full inventory and confirmed control/network on all three, compute on node2/node3, storage/cinder-volume/cinder-volume-lvm/tgtd only on node3, Glance/Glance API on node1, and the preserved management IPs. The actual render-netplan.yml and role then rendered all three candidates with local transport forced. Assertions checked original management addresses, gateway/DNS, exact recorded USB MACs, ext0 naming, disabled provider DHCP/link-local and no provider host IP. The repeated native run reported changed=0 on all three with identical candidates. A duplicate-MAC fixture was refused. All simulation checks passed.

This is local source/rendering evidence. It does not run netplan generate/try on Ubuntu lab nodes, test the mini switch/USB behavior, establish DHCP/VIP ownership, provision a Cinder disk, run Kolla prechecks or deploy OpenStack. Real configuration still requires the explicitly listed remaining facts. No new runtime wrapper or infrastructure behavior is introduced.

## Node3 SATA reuse review from already recorded evidence

The existing Stage 0 record already contains node3 Kingston A400 SATA SMART overall PASSED, reported-uncorrectable raw 0, no ATA errors logged and a previous extended self-test completed without error. Its later cleanup result is CLEANED with no detected signatures/PV/children and the NVMe OS backing unchanged. This supports the selected empty lab disk's reuse review; no repeated scan or fresh self-test is required or claimed. This is a snapshot, not a reliability guarantee. The storage guard still verifies identity and current-use state before creating the VG.

NVMe self-test-log command failures and node1's unused SATA bad-block raw count remain distinct follow-up findings, without being labelled as diagnosed firmware defects or confirmed media failures. They are not represented as a new prerequisite for allocating node3's SATA disk. The earlier draft's request for node3's already collected report was removed. The remaining deployment-input question is the .100 reservation's DHCP product/device, binding/current lease and conflicting use. No real private configuration or verification flag was written.

Documentation validation for this publication passed: source/YAML/JSON/Python and fixed-IP checks, whitespace checks, balanced Markdown/details, all 41 local links/anchors and syntax for all 45 Bash examples across the nine Markdown documents. The publication changes six Markdown documents only; no runtime source or verification guard changes.
