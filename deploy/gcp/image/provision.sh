#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
find /etc/apt/sources.list.d -type f -exec sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' {} +
apt-get update
apt-get upgrade -y
apt-get install -y podman uidmap slirp4netns passt dbus-user-session python3-venv \
    nftables unattended-upgrades openssl ca-certificates curl git
# Dedicated UID makes firewall identity stable across image builds.
groupadd --system agentbox
useradd --system --uid 1001 --gid agentbox --home-dir /var/lib/agentbox-runner --create-home --shell /usr/sbin/nologin agentbox-runner
useradd --system --gid agentbox --home-dir /var/lib/agentbox-broker --create-home --shell /usr/sbin/nologin agentbox-broker
usermod --add-subuids 200000-265535 --add-subgids 200000-265535 agentbox-runner
chmod 700 /var/lib/agentbox-runner /var/lib/agentbox-broker
python3 -m venv /opt/agentbox
/opt/agentbox/bin/pip install "$AGENTBOX_WHEEL"
install -d -m 755 /etc/agentbox
install -d -m 700 -o agentbox-runner -g agentbox /var/lib/agentbox-runner/workspaces
install -m 644 /tmp/agentbox-files/*.service /tmp/agentbox-files/*.timer /etc/systemd/system/
install -m 755 /tmp/agentbox-files/agentbox-stop /tmp/agentbox-files/agentbox-ready /usr/local/sbin/
# No swap/core dumps: tmpfs and in-memory credentials must not become disk-backed.
swapoff -a
sed -i '/[[:space:]]swap[[:space:]]/d' /etc/fstab
install -d /etc/systemd/coredump.conf.d
printf '[Coredump]\nStorage=none\nProcessSizeMax=0\n' > /etc/systemd/coredump.conf.d/agentbox.conf
printf 'fs.suid_dumpable=0\n' > /etc/sysctl.d/90-agentbox.conf
cat > /etc/nftables.conf <<'NFT'
#!/usr/sbin/nft -f
flush ruleset
table inet agentbox {
    chain output {
        type filter hook output priority 0; policy accept;
        # All IP traffic from supervisor/container runtime UID is denied, including metadata/DNS.
        meta skuid 1001 counter reject
    }
}
NFT
systemctl enable --now nftables.service
install -d /etc/ssh/sshd_config.d
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/00-agentbox.conf
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades
install -d /etc/systemd/system/user@1001.service.d
printf '[Service]\nDelegate=cpu cpuset io memory pids\n' > /etc/systemd/system/user@1001.service.d/delegate.conf
systemctl daemon-reload
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
loginctl enable-linger agentbox-runner
systemctl start user@1001.service
# Preload the reviewed workload image before enabling the runner's IP deny rule.
nft delete table inet agentbox
cd /var/lib/agentbox-runner
runuser -u agentbox-runner -- env HOME=/var/lib/agentbox-runner XDG_RUNTIME_DIR=/run/user/1001 \
    podman pull "$AGENTBOX_WORKLOAD_IMAGE"
nft -f /etc/nftables.conf
# Do not enable review services in the distributable image; deployment provides root-owned policy.
systemctl daemon-reload
rm -rf /tmp/agentbox-files
rm -f "$AGENTBOX_WHEEL"
# Generalize machine/SSH identities before the image is captured.
rm -f /etc/ssh/ssh_host_*
truncate -s 0 /etc/machine-id
