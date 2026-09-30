# Remote tasks: host setup guide

Step-by-step path from an empty Linux VM to a first remote task and an optional
Hermes gateway. The command reference is in the README section "Remote tasks"; this
guide covers host preparation and the problems met during real-host acceptance.

Placeholders: `<host>` is the registered remote name, `<dest>` its SSH destination
(an `~/.ssh/config` alias), `<user>` the SSH user on the remote,
`<org>/<repo>` the GitHub repository tasks work on.

## 1. The host

Any always-on Linux host you can SSH into works. Tested: Ubuntu 24.04 on a private
GCP VM without an external IP, reached through IAP, with OS Login.

- 2 vCPU / 8 GB RAM and 50 GB disk are enough for agent tasks and a Hermes gateway.
  Tasks do not get nested Docker, so project builds that need Compose run in CI.
- Outbound network access is required (GitHub, package registries, model APIs).
- Use a dedicated host. Docker group membership is root-equivalent, and agents run
  with `--dangerously-skip-permissions` inside their containers.

## 2. SSH from the laptop

Agentbox calls `ssh -o BatchMode=yes -- <dest>`, so `ssh <dest> true` must work
without any prompt. For a VM without an external IP, an IAP alias looks like this
(`~/.ssh/config`, or a file included from it):

```
Host <dest>
  HostName <instance-name>
  User <user>
  IdentityFile ~/.ssh/google_compute_engine
  UserKnownHostsFile ~/.ssh/google_compute_known_hosts
  HostKeyAlias compute.<instance-id>
  ProxyCommand gcloud compute start-iap-tunnel %h 22 --listen-on-stdin --project=<project> --zone=<zone> --verbosity=error
```

Run `gcloud compute ssh <instance-name> --tunnel-through-iap` once first: it creates
the OS Login user, uploads the key and records the host key used by `HostKeyAlias`.
If `gcloud` needs a re-login (`gcloud auth login`), every remote command fails until
you do it.

## 3. Prepare the host (once, as `<user>`)

Container runtime usable without `sudo`. With Docker, add the user to the `docker`
group; OS Login users are not in `/etc/passwd`, so use `gpasswd` instead of `usermod`,
then reconnect:

```bash
sudo gpasswd -a "$USER" docker
```

Tools and GitHub CLI:

```bash
sudo apt-get update && sudo apt-get install -y git tmux pipx
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt-get update && sudo apt-get install -y gh
```

The wizard checks all of this and prints what is missing, but it never runs `sudo`.

## 4. Agentbox on the laptop

Until remote tasks are in a release, install from a checkout that contains them:

```bash
pipx install --editable /path/to/agentbox
agentbox remote --help
```

`install.sh` installs the latest `main` from GitHub; do not use it for this. The
wizard installs the same code on the remote. After changing the checkout without a
version bump, push it with `agentbox remote setup <host> --reinstall`.

## 5. Run the wizard

```bash
agentbox remote setup <host> --ssh <dest>
```

Answers for a new remote:

- repository: `https://github.com/<org>/<repo>.git` (HTTPS, matching `gh auth login --web`)
- base_dir: an absolute path in the remote user's home, e.g. `/home/<user>/agentbox-remote/<repo>`
- agent: `claude`

Expected stops on a fresh host, each fixed by re-running after the action:

| Step | Message | Action |
| --- | --- | --- |
| tools | `Install on the remote: pipx` | install it (section 3) |
| github | `Run in your terminal: ssh -t <dest> gh auth login ...` | run it, choose HTTPS and "authenticate Git", confirm the device code |
| remote-config | confirmation prompt for `<base_dir>/agentbox.yaml` | answer `y` |

The `image` step builds the agent image without printing progress; the first build
takes a few minutes. A finished run ends with `INFO login: ...`.

## 6. Log the agent in once

Run the printed command, for example:

```bash
ssh -t <dest> "bash -lc 'env AGENTBOX_CONFIG=/home/<user>/agentbox-remote/<repo>/agentbox.yaml agentbox run /home/<user>/agentbox-remote/<repo>/repo --agent claude'"
```

- Claude Code asks to accept "Bypass Permissions mode". It runs inside the task
  container; accept it, otherwise background tasks wait for approval on every command.
- `/login` prints a long OAuth URL. Widen the terminal first: a wrapped URL copied in
  pieces loses its query string and the browser shows
  `Invalid code_challenge_method: missing`.
- The login lives in the repository's shared HOME, so every task uses it. `/exit` when done.

## 7. First task

```bash
agentbox remote run <host> --name smoke --branch <existing-branch> -- "Print the README title. Change nothing."
agentbox remote list <host>
agentbox remote attach <host> smoke        # detach: Ctrl+b d
agentbox remote logs <host> smoke
agentbox remote stop <host> smoke --remove-worktree
```

Close the laptop while a task runs and check `remote logs` afterwards: the task keeps
running in its tmux session on the host.

## 8. Hermes gateway (optional)

Hermes shares one HOME per repository. An interactive Hermes session and the gateway
service must not run at the same time, so stop the service before any interactive
step:

```bash
agentbox remote service stop <host> hermes
ssh -t <dest> "bash -lc 'env AGENTBOX_CONFIG=/home/<user>/agentbox-remote/<repo>/agentbox.yaml agentbox run /home/<user>/agentbox-remote/<repo>/repo --agent hermes -- setup'"
```

Choices that worked:

- Model: "Full setup", provider Anthropic, OAuth with a Claude account (no API key).
  "Quick Setup" uses the Nous Portal, a third-party service that would receive
  repository content.
- Terminal backend: keep `local` (the Hermes container itself).
- Tools: disable what a code agent does not need (browser automation, computer use,
  vision, image generation, text-to-speech, connections). Search, browser and TTS
  providers send data to third parties; skip them unless approved.

WhatsApp (Baileys bridge, unofficial API, account ban risk; a dedicated number is
recommended, self-chat mode works for a single user):

```bash
ssh -t <dest> "bash -lc 'env AGENTBOX_CONFIG=/home/<user>/agentbox-remote/<repo>/agentbox.yaml agentbox run /home/<user>/agentbox-remote/<repo>/repo --agent hermes -- whatsapp'"
agentbox remote service setup <host>
```

Pair by scanning the QR code (terminal at least 60 columns). In `service setup`,
enable WhatsApp and set "Allowed user IDs" and "Home chat ID" to your number with the
country code and no `+`. The paired session grants full access to that WhatsApp
account and is stored in the Hermes HOME on the host.

Start and check:

```bash
agentbox remote service start <host> hermes --restart-policy unless-stopped
agentbox remote service status <host> hermes
agentbox remote service logs <host> hermes --tail 30
```

SQLite WAL warnings in the log are harmless. Cron jobs are created by asking Hermes in
chat (for example over WhatsApp); the gateway runs them on schedule.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Error: No such command 'remote'` | laptop runs a release or `install.sh` build | section 4 |
| every command fails, `Reauthentication failed` | expired `gcloud` login used by the IAP ProxyCommand | `gcloud auth login` |
| `Task <name> not found on the remote` | no tmux session and no worktree | nothing to stop |
| `Login expired` or `401` in a task | agent login missing in the repository HOME | section 6 |
| gateway `restarting (exit 78)`, `WhatsApp enabled but not paired` | WhatsApp enabled without pairing | pair it, or disable WhatsApp in `service setup` |
| `ImportError: The 'anthropic' package is required` | image built before the Hermes `anthropic` extra was added | `remote setup --reinstall`, then stop/start the service |
| `whatsapp failed to connect` right after pairing | image built before the bridge dependencies were preinstalled | same as above |
| `ACTION remote-config: ... is tracked in the repository` | the repository tracks `.agentbox.yaml` | add the listed keys there |

## Teardown

`agentbox remote stop` every task, `agentbox remote service stop <host> hermes`, then
destroy the host. Everything on it (worktrees, logins, Hermes state, WhatsApp
session) is gone; a new host needs this guide again from section 3.
