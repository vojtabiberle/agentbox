# Always-on runner threat model (preview)

## Assets and trust

Protect host files, provider/GitHub credentials, cloud identity, model budget and
unrelated repositories. Treat PR diffs, prompts, model output and all workload code as
hostile. Trust administrators, the baked VM and digest-pinned workload image, root-owned
policy, Podman/kernel, broker/controller code and upstream providers. VM/cloud admins
can change the policy and are outside the attacker model. One VM belongs to one user;
this is not a hostile multi-tenant boundary.

## Mitigations

| Threat | Enforced boundary |
| --- | --- |
| PR changes config, plugins or Dockerfile | Server never discovers/loads project configuration or builds project images |
| Agent reads host credentials/runtime socket | Only approved workspace and broker socket are mounted; HOME is fresh tmpfs |
| Agent becomes host root | Rootless Podman, nonzero UID, no capabilities, no-new-privileges; host runner has no login/sudo |
| Direct network/metadata/DNS bypass | Network namespace has only loopback; nftables denies all runner-UID IPv4/IPv6 egress |
| Allowed domain resolves to internal address | Resolve/check all addresses, reject non-global/multicast, connect to checked IP |
| Agent steals long-lived keys | Keys exist only in broker memory; no key in workload environment, files or logs |
| Agent merges/pushes/posts elsewhere | GitHub operations use a separate unmounted controller socket with exact repository/route restrictions |
| Agent exceeds model allowance | Fixed-model/input/output admission plus atomic durable worst-case reservation before generation |
| Run loops or floods output | CPU/RAM/PID/tmpfs limits, timeout/output ceilings, bounded broker connections and cleanup |
| Restart bypasses stop | Root-owned STOP latch, systemd conditions and runtime/broker checks; kill command stops timer and broker |
| Duplicate review after crash | Durable claim before model/publication; ambiguous claims require operator intervention |

## Explicit limitations

- Container isolation shares the host kernel. Kernel/runtime escapes and compromise
  of the trusted broker/controller/image are not solved; use stronger VM-per-job
  isolation when the risk warrants it.
- A permitted destination can be an exfiltration channel. Model prompts necessarily
  reach the selected provider. Extra domain allowlists do not enforce tenant/account
  boundaries within GitHub, Datadog or other shared services.
- The reference reviewer can still produce malicious, misleading or sensitive text.
  Its comment is untrusted. Disabling tools limits actions, not the quality/safety of
  generated text. Human review remains necessary.
- No absolute monetary guarantee without a correctly reviewed cost reservation and
  provider pricing/limits. GCP infrastructure costs are separate. UTC admission-day
  accounting is not identical to provider billing-day accounting.
- A privileged host administrator can read memory/secrets and journals or modify policy.
  Disabling swap/core dumps and not persisting credentials does not make memory secret
  from root. Host changes outside this image can invalidate those guarantees.
- Network access already sent upstream cannot be undone. Killing the broker/workload
  closes local access; already accepted provider requests may still be billed.
- Workload logs are not a trusted record of its actions. Structured supervisor/broker
  events cover lifecycle and mediated external operations, not every local command.
- Read-write workspace mode is explicit and exposes exactly that tree to corruption
  and disk exhaustion; the reference uses read-only empty workspaces. No disk quota
  guarantee is made for arbitrary read-write workspaces.
- Root-owned policy is mandatory for server CLI, but a trusted host user can still run
  their own CLI outside it. Host access must stay restricted; this is not an OS policy
  preventing administrators from bypassing the runner.
- App token signing, Secret Manager access, GCP image boot/reboot/update, IAP and live
  model review require DEV integration validation. Local/mocked tests do not establish
  those properties on an actual cloud VM.
