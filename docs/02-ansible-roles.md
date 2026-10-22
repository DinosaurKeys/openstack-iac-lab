# Stage 2 — Ansible roles, YAML inventory, and node rebuilding

**Current checkpoint:** Stage 1 host preparation, using the Ansible roles explained here. SSH, sudo and the common-role preview passed on all three nodes. **Next: apply the reviewed common role and verify the result.**

## Apply the reviewed common role

### 1. Read the successful preview

Report start: **`2026-10-22T10:35:36Z`**. Final result: **`COMMON_PREVIEW_OK for all`**.

| Node | Preserved address | Preview recap |
|---|---|---|
| node1 | `192.168.0.200` | `changed=2`, `failed=0`, `unreachable=0`, `skipped=1` |
| node2 | `192.168.0.201` | `changed=2`, `failed=0`, `unreachable=0`, `skipped=1` |
| node3 | `192.168.0.202` | `changed=2`, `failed=0`, `unreachable=0`, `skipped=1` |

**Two changed tasks:** the APT package task and the marked `/etc/hosts` block. These were predictions. Hostnames already matched. The Chrony service task was skipped because the package was still absent; the explicit `DEFERRED` message was expected.

### 2. What the real run will change

| Observed proposal, on every node | Purpose and location |
|---|---|
| Install `chrony` | Ubuntu system clock service; commands under `/usr`, configuration under `/etc/chrony` |
| Install `tzdata-legacy` | Supporting time-zone data selected by APT; a system data package on each node |
| Remove `systemd-timesyncd` | Replace the installed time client with the role's chosen Chrony service |
| Add the marked `/etc/hosts` block | Map `node1` → `.200`, `node2` → `.201`, `node3` → `.202` locally on each node |
| Enable/start Chrony | Synchronize the node's system clock using its installed configuration |

APT proposed no new installation for the other six declared packages. Their purposes are explained in the [completed preview lesson](#preview-the-common-role). `tzdata-legacy` is an automatically selected supporting package; it is not an extra role or time service.

The preview showed **0 upgrades**, with **27 packages not upgraded on node1/node3 and 28 on node2**. Those counts describe available packages outside that transaction. This role requests package presence, rather than a full operating-system upgrade.

**Preview limitation:** a real run re-evaluates the desired configuration and can refresh APT metadata older than one hour. It is not a saved package transaction. The actual package versions and dependency changes will be recorded in the real report.

If `/etc/hosts` changes, Ansible saves its previous contents to a dated backup on that node and prints the backup path. The role preserves the management IP configuration; verification reads the actual address afterward.

### 3. Apply on one node at a time

`scripts/apply-common.sh` runs the same `base.yml` and `common` role, then checks the actual result. Hermes uses its existing project environment and SSH key; the system package installation happens on the selected nodes.

```mermaid
flowchart TD
    A["Apply common on selected node"] --> B["Verify actual configuration"]
    A -->|"Task fails"| F["Stop and save report"]
    B -->|"Check fails"| F
    B -->|"Passed; nodes remain"| A
    B -->|"Last node passed"| S["Combined verified result"]
```

**Run on Hermes from `~/git/openstack-iac-lab`:**

```bash
git pull --ff-only
bash scripts/apply-common.sh joe --node all --apply
```

**This command makes real package/name/time changes.** `--apply` selects that behavior explicitly. Each node asks separately for its Ubuntu `joe` password at `BECOME password:`. The wrapper uses the fixed node addresses and existing `~/venvs/kolla-iac` tools.

### 4. What the script verifies

| Check | Required result |
|---|---|
| Package facts | All seven declared common packages are installed; versions are printed |
| Hostname | Matches the selected inventory node |
| Built-in management NIC | Still has that node's preserved IP and `/24` prefix |
| IPv4 name resolution | Each of `node1`, `node2`, `node3` resolves to its preserved IP |
| Chrony service | Running and enabled at boot |
| `chronyc waitsync 12 0 0 2` | Reports synchronization within 12 checks, two seconds apart |

The two zero arguments disable extra correction/skew thresholds; the check requires Chrony to report synchronization. It does not certify a particular clock-accuracy limit. Tracking and time-source output are included for review.

On an apply run, `changed` counts **tasks that actually changed configuration**. Its value can differ from the preview. Verification reads report no configuration changes.

Expected final line:

```text
RESULT: COMMON_APPLIED_OK for all; installed baseline and time synchronization verified.
```

The wrapper prints the short summary and saves **`build/common-apply-summary.txt`** plus **`build/common-apply-report.txt`** privately. Timestamped history remains under ignored `build/`; preview reports are separate.

**On failure:** the wrapper stops before the next node. Completed changes remain; this is not an automatic rollback. A missing completion marker also prevents a success claim. Review the actual failed task and existing report before another apply. Resolver failures show the unexpected addresses; synchronization failures include Chrony's tracking/source output.

**Share the printed apply summary.** We will review the real result before networking changes. The role itself performs no Netplan edit, disk allocation or OpenStack deployment. The real apply remains unverified until its report is supplied.

Sources: [Ubuntu time synchronization](https://ubuntu.com/server/docs/how-to/networking/timedatectl-and-timesyncd/), [Ubuntu tzdata packages](https://packages.ubuntu.com/search?keywords=tzdata), [Ansible APT semantics](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/apt_module.html), [Chrony waitsync](https://chrony-project.org/doc/4.5/chronyc.html#waitsync).

<details>
<summary>Completed lesson: package purposes, common-role structure and the preview command</summary>

## Preview the common role

**Completed:** the real preview starting `2026-10-22T10:35:36Z` passed on all three nodes. Continue with the apply lesson above. This reference explains the package list and the preview behavior.

### 1. What we have proved

The report starting **`2026-10-22T10:14:57Z`** ends with **`ADMIN_ACCESS_OK for all`**.

| Node | Preserved address | Administrator check |
|---|---|---|
| node1 | `192.168.0.200` | Root UID `0`; hostname matched |
| node2 | `192.168.0.201` | Root UID `0`; hostname matched |
| node3 | `192.168.0.202` | Root UID `0`; hostname matched |

Each recap shows `ok=4`, `changed=0`, `unreachable=0`, `failed=0`. Ansible can now perform administrator tasks. The earlier node2 authentication failure is resolved in this run; the log does not establish what caused the earlier rejected entry.

### 2. What is the common role?

A **role** is a reusable folder of Ansible tasks. Our `common` role describes the basic packages, node names and clock service wanted on every node. It prepares Ubuntu for later OpenStack work.

```mermaid
flowchart TD
    I["hosts.yml: three nodes"] --> P["base.yml: use common"]
    P --> R["common/tasks/main.yml"]
    G["group_vars: package list"] --> R
    R --> A["APT packages"]
    R --> N["Hostnames and hosts entries"]
    R --> T["Chrony clock service"]
```

### 3. What would be installed, where and why?

These are **Ubuntu system packages on node1, node2 and node3**, installed through APT. Programs live under `/usr`; system configuration lives under `/etc`. Hermes keeps its existing tools in `~/venvs/kolla-iac`.

| Package | Main command | Why the node needs it |
|---|---|---|
| `curl` | `curl` | Test HTTP endpoints and transfer files |
| `git` | `git` | Retrieve and inspect versioned source when needed |
| `jq` | `jq` | Read and filter JSON command output |
| `lvm2` | `lvm`, `pvs`, `vgs`, `lvs` | Manage Linux logical volumes; node3 will later use LVM for Cinder |
| `smartmontools` | `smartctl` | Read disk health information |
| `chrony` | `chronyd`, `chronyc` | Keep the node clock synchronized |
| `python3` | `python3` | Run Ansible modules on the node |

`state: present` means keep packages already installed and install missing ones. APT also resolves dependencies and may replace conflicting packages. **Review any proposed removals**, including replacement of an existing time client such as `systemd-timesyncd` by Chrony. Package versions and the transaction depend on each node's APT metadata.

The APT module also needs the existing `python3-apt` system package. Automatic installation of that helper is disabled: if it is missing, the preview stops for review.

| Other role task | Later real-run effect | Why |
|---|---|---|
| Hostname | Ensure `node1`, `node2` or `node3` matches inventory | Keep node identity consistent |
| `/etc/hosts` | Maintain one marked block with `.200 node1`, `.201 node2`, `.202 node3` | Resolve the management names locally |
| Chrony service | Enable at boot and start it | Maintain time synchronization |

The role contains no Netplan edit, disk allocation or cloud deployment. Management IPs stay as recorded above.

### 4. Preview all three nodes

**Preview means calculate, then review.** The wrapper always runs the existing `base.yml` playbook with `--check --diff`; it has no apply mode. Ansible predicts supported changes and shows available before/after differences.

| File | Job |
|---|---|
| `ansible/inventory/group_vars/all.yml` | Declares the seven packages, `joe` account and project key |
| `ansible/playbooks/base.yml` | Selects the common role for the lab nodes |
| `ansible/roles/common/tasks/main.yml` | Defines the desired host configuration |
| `scripts/preview-common.sh` | Checks inventory, previews each selected node and saves one combined report |

**Run on Hermes from `~/git/openstack-iac-lab`:**

```bash
git pull --ff-only
bash scripts/preview-common.sh joe --node all
```

At each `BECOME password:` prompt, enter that node's Ubuntu `joe` password. The wrapper uses `~/venvs/kolla-iac` and the existing `~/.ssh/openstack-iac-lab-ansible` key. It asks separately for each selected node.

### 5. Read the preview, then stop

| Output | Meaning |
|---|---|
| `ok` | The task predicts no configuration change, or completed a read/check |
| `changed` | A change is **predicted**, not applied |
| File diff with `-` / `+` lines | Existing content / proposed content |
| `DEFERRED: chrony.service is absent` | Package installation is predicted; its missing service cannot yet be checked |
| `COMMON_PREVIEW_OK` | The role preview completed; review its predictions |
| `FAILED`, final `REVIEW` | Inspect the error before any real run |

**Chrony detail:** if its unit already exists, Ansible previews enabling/starting it. If absent, only that service check is deferred and explained. This preview never proves actual service startup or clock synchronization. Previewing against current APT metadata also does not prove a later download or installation will succeed.

The script prints all node output and a short summary. The combined proposed changes are saved privately in **`build/common-preview-report.txt`**; the summary is `build/common-preview-summary.txt`. Timestamped history stays in ignored `build/`. Ordinary node failures are recorded while later previews continue; cancellation stops. Ansible temporary files and normal authentication logs can occur.

**Share the preview output, including proposed package and `/etc/hosts` changes.** We will review those details before the real common-role run. A successful preview is not a completed host installation.

Sources: [Ansible check and diff modes](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html), [APT module](https://docs.ansible.com/projects/ansible-core/2.20/collections/ansible/builtin/apt_module.html), [Ubuntu time synchronization](https://ubuntu.com/server/docs/how-to/networking/timedatectl-and-timesyncd/).

</details>

<details>
<summary>Completed lesson: Ansible sudo access and the resolved node2 password rejection</summary>

## Check Ansible administrator access

**Completed:** the later all-node run starting `2026-10-22T10:14:57Z` passed on all three. The commands and earlier rejection below are retained as learning history. Continue with the common-role preview above.

**Stage 1 host preparation, using this stage's Ansible files.** SSH already lets Hermes log in as `joe`. Installing packages and configuring system services later require administrator privileges. This check proves that Ansible can use `sudo` before we apply the common role.

**The new word is `become`:** Ansible logs in as `joe`, then uses `sudo` to run the selected task as `root`. Linux identifies root with user ID **`0`**.

```mermaid
flowchart TD
    I["YAML inventory"] --> A["Ansible on Hermes"]
    K["Hermes private key"] --> A
    A -->|"SSH login"| J["joe on the selected node"]
    J -->|"sudo with joe's password"| R["root reads identity"]
    R -->|"UID and hostname"| A
```

| Project file | Its job |
|---|---|
| `ansible/inventory/hosts.yml` | Lists the three node names, preserved IPs and groups |
| `ansible/inventory/group_vars/all.yml` | Supplies the `joe` account and selected SSH key |
| `ansible/playbooks/check-admin.yml` | YAML task list: read effective user ID and hostname, then check the results |
| `scripts/check-admin.sh` | Runs that playbook once per selected node and saves one combined report |

**Exactly what runs on each node:**

| Command | Expected result | Effect |
|---|---|---|
| `id -u` after sudo | `0` | Reads the effective user ID |
| `hostname -s` | `node1`, `node2` or `node3`, matching the selected host | Reads the hostname |

This step installs no package and edits no node configuration. Normal Ansible temporary files and SSH/sudo logging can still occur. It uses the tracked preparation inventory; no cloud VIP, floating-IP pool or storage approval is needed for these identity reads.

**Prompt:** `BECOME password:` means **that selected node's Ubuntu `joe` sudo password**. The SSH key handles login. The wrapper asks separately for node1, node2 and node3, so passwords do not have to be identical. Characters stay hidden; the entered passwords are not written into the reports.

**Run on Hermes from `~/git/openstack-iac-lab`:**

```bash
git pull --ff-only
bash scripts/check-admin.sh joe --node all
```

The summary prints at the end and is saved as **`build/admin-access-summary.txt`**. Detailed output is in `build/admin-access-report.txt`; timestamped history and the resolved inventory snapshot stay in private, ignored `build/` files.

| Summary output | Meaning |
|---|---|
| `node1: PASSED; UID 0 and expected hostname verified` | Ansible used sudo successfully on the intended node; the same rule applies to node2/node3 |
| `RESULT: ADMIN_ACCESS_OK for all` | All three identity checks passed |
| A node says `FAILED`, final result `REVIEW` | Read that node's error in the detailed output; do not apply host configuration yet |
| `STOP` before node checks | Local prerequisites or the resolved inventory did not match; no node command was attempted |

An ordinary node failure is recorded and the read-only checks continue to the other selected nodes. Cancelling stops later checks. `--node node2` selects only that node for a targeted check when needed.

**Review the short summary before host configuration.** A pass proves Ansible's sudo access. The next lesson will explain the common role's packages and proposed changes before applying it. The first live result is recorded below.

### Reviewed result: node2 sudo password

**Resolved by the later all-node run:** node2, node1 and node3 all passed at `2026-10-22T10:14:57Z`. The following explains the earlier report; another authentication retry is unnecessary.

Report start: **`2026-10-22T10:04:51Z`**. Final result: **`REVIEW`**.

| Node | Preserved address | Observed result | Meaning |
|---|---|---|---|
| node1 | `192.168.0.200` | `ADMIN_OK`; UID `0`; hostname matched | Ansible used sudo successfully |
| node2 | `192.168.0.201` | `Incorrect sudo password` | SSH reached the node; sudo rejected the password before the identity commands ran |
| node3 | `192.168.0.202` | `ADMIN_OK`; UID `0`; hostname matched | Ansible used sudo successfully |

**Cause → effect:** node2 rejected the supplied sudo password, so its first task failed. The independent read-only checks continued to node3 as designed. The final `REVIEW` means the administrator-access checkpoint is incomplete. All nodes report `changed=0`; no host configuration was applied.

The log does not establish whether the password was mistyped or a different credential was entered. At `BECOME password:`, use **node2's Ubuntu `joe` account password**. Typing stays hidden.

**Retry on Hermes, from `~/git/openstack-iac-lab`:**

```bash
git pull --ff-only
bash scripts/check-admin.sh joe --node node2
```

This runs the same identity reads on node2 only. The expected final line is:

```text
RESULT: ADMIN_ACCESS_OK for node2; identity checks passed.
```

**Share the printed summary.** It is also saved to `build/admin-access-summary.txt`. The latest report files will describe this node2-only run; the earlier all-node report remains in timestamped history. We will review the new result alongside the recorded node1/node3 passes before applying the common role. If sudo rejects the password again, share the error text so we can investigate node2's local sudo authentication.

<details>
<summary>Two error details explained</summary>

| Output | Meaning |
|---|---|
| `Origin: .../check-admin.yml:9:7` | Location of the failed task in the YAML file; the reported failure is sudo authentication |
| `ansible_exit=2; log_exit=0` | Ansible reported failure; the command saving its output succeeded |

</details>

Source: [Ansible become and sudo-password prompts](https://docs.ansible.com/projects/ansible-core/devel/playbook_guide/playbooks_privilege_escalation.html).

</details>

## Why roles?

A playbook describes which hosts to work on. A role packages one responsibility: tasks, templates, handlers, and defaults. Inventory says where hosts belong; group_vars contains shared settings; host_vars contains differences such as a USB NIC's MAC address.

The supplied common and Netplan examples can be used during Stage 1's preparation. This stage explains and validates that structure before extending it to applications.

```mermaid
flowchart TD
    P["base.yml / render-netplan.yml"] --> I["YAML inventory: names, IPs, groups"]
    I --> G["group_vars: user, gateway, shared packages"]
    I --> H["host_vars: each provider NIC MAC"]
    G --> C["common role: packages, names, time"]
    H --> N["netplan role: render candidates on Hermes"]
    N --> R["Console review → install → netplan try"]
```

<details>
<summary>Later command reference: inventory, common role, Netplan and Kolla sudo</summary>

Complete the current administrator-access check and review its summary before using this later reference.

## 1. Examine the supplied inventory

Run from the repository root in the kolla-iac virtual environment:

```bash
ansible-inventory --graph
ansible lab_nodes --list-hosts
ansible control --list-hosts
ansible lab_nodes -m ansible.builtin.ping -e '{"ansible_become":false}'
```

Expected: exactly node1/node2/node3 in lab_nodes and control. Hermes is not a managed lab node. Ansible's ping module tests SSH/Python operation; it is not an ICMP ping. The extra variable disables sudo for this login test; later privileged playbooks use `--ask-become-pass`.

The preparation inventory is intentionally smaller than Kolla's service inventory. Stage 1 generates the latter from the full installed sample, preserving its child groups. Do not use the small preparation inventory as a substitute for Kolla's complete inventory.

When using the central private/lab.yml configuration, use `-i build/inventory.yml` with the commands in this stage, or use labctl's entry points. The tracked inventory/host_vars files show the source structure; the generated inventory embeds the reviewed values so you do not maintain two copies of live input.

## 2. Inspect hosts, then apply common

```bash
ansible-playbook ansible/playbooks/preflight.yml --ask-become-pass
ansible-playbook ansible/playbooks/base.yml --syntax-check
ansible-playbook ansible/playbooks/base.yml --check --diff --ask-become-pass
ansible-playbook ansible/playbooks/base.yml --ask-become-pass
ansible-playbook ansible/playbooks/base.yml --ask-become-pass
```

The common role installs explicit packages, sets hostnames, writes a marked /etc/hosts block, and enables Chrony. It does not reset Ceph, edit storage, or deploy OpenStack. On the second normal run, configuration tasks should report no changes unless the machine changed between runs. A check-mode run is a preview, not proof that a real run will succeed.

If the last command repeatedly changes something, inspect the particular task before proceeding. Avoid tasks such as an unconditional `echo >> /etc/hosts`, which append another duplicate on each run.

## 3. Render networking without cutting off SSH

At each node, read `ip -br link` and the actual provider NIC MAC. Fill the corresponding host_vars file. Check management-interface names and set verified DNS servers in group_vars. Then:

```bash
ansible-playbook ansible/playbooks/render-netplan.yml --syntax-check
ansible-playbook ansible/playbooks/render-netplan.yml
cat build/netplan/node1.yaml
cat build/netplan/node2.yaml
cat build/netplan/node3.yaml
```

The role fails if a provider MAC is still a placeholder or DNS is empty. It writes candidates under build/netplan on Hermes, not /etc/netplan on the nodes.

For a freshly installed node, compare the candidate with **all** files in /etc/netplan. Back up the existing configuration privately. From its local console, install one reviewed definition, remove conflicting definitions only after reviewing their ownership, and run:

```bash
sudo netplan generate
sudo netplan try --timeout 120
```

Test SSH, the default route, DNS, and the expected interface addresses from another terminal before accepting the change. Verify the actual rollback state if it times out. Repeat one host at a time. Keep provider ext0 free of a host IP; Kolla will attach it to OVS.

## 4. Sudo and Kolla

The confirmed account is `joe` on all three reinstalled nodes; both preparation and generated Kolla inventories use it. Discovery succeeded with SSH passwords. The report's "passwordless sudo is unavailable" message is expected with normal Ubuntu sudo and is not a discovery failure. Regular ansible-playbook commands use `--ask-become-pass` for sudo; unattended SSH access must be prepared separately before running them. Kolla's selected Python CLI does not expose that same flag; use Ansible's environment setting when needed:

```bash
export ANSIBLE_BECOME_ASK_PASS=True
```

Run the Kolla command normally; the underlying Ansible process prompts. Do not set this to an actual password. Alternatively, explicitly review a lab deployment-account sudo policy. Passwordless sudo is a permission choice, not a prerequisite for understanding roles.

</details>

## 5. Rebuild a node without confusing the layers

| Layer | Correct operation | What it does not do |
|---|---|---|
| Terraform workload | Review destroy plan → apply → recreate | Does not reinstall physical Ubuntu |
| Physical host | Reinstall Ubuntu → restore identity/network → common role | Does not recreate old VMs or volumes |
| OpenStack services | Follow Kolla's host lifecycle/recovery procedure | Does not restore a lost LVM disk |

On this layout every physical node is a controller. A host reset therefore removes a controller as well as any compute/storage roles it carries. Do not start with a random live `--limit node2` Kolla deployment: Kolla documents limitations around --limit, and full service-group context matters.

First complete the requested **full lab rebuild**. For a later controlled one-host exercise:

1. Record controller/database/message health and take recoverable private control-plane backups.
2. Evacuate or deliberately delete disposable instances on the chosen compute. Verify that it is not the only Glance/LVM host needed by the exercise.
3. Follow the selected Kolla release's removal/replacement procedure for that host; decide how the database and RabbitMQ member identities will be removed/re-enrolled.
4. Reinstall Ubuntu with its same hostname/IP, verify its new SSH fingerprint, apply preparation roles, then follow the reviewed Kolla rejoin procedure.
5. Check quorum and service health before doing anything to a second controller.

That final controller rejoin depends on the observed cluster state; it is not represented as a generic one-command promise here.

## Finish line and recovery

Understand the graph, obtain repeatable common-role results, and render the same Netplan candidate from the same inputs. Keep the console available during networking changes. Restore the saved configuration from the console if the candidate loses connectivity. Do not continue into Kolla with unresolved interface or hostname resolution problems.

## Sources

- [Ansible roles](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_reuse_roles.html)
- [Ansible inventory](https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html)
- [Netplan try](https://netplan.readthedocs.io/en/stable/netplan-try/)
- [Kolla operations and --limit caveats](https://docs.openstack.org/kolla-ansible/2026.1/user/operating-kolla.html)
- [Ansible become_ask_pass setting](https://docs.ansible.com/ansible/latest/reference_appendices/config.html#default-become-ask-pass)

Next: [Stage 3](03-terraform-modules.md).
