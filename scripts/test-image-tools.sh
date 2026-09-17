#!/bin/sh
# Offline functional checks for upstream tool replacements. No host mounts needed.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
git init -q
test "$(git config --get filter.lfs.required)" = true
git lfs install --local
printf 'agentbox LFS roundtrip\n' > original
git lfs clean -- sample.bin < original > pointer
git lfs smudge -- sample.bin < pointer > restored
test "$(cat restored)" = 'agentbox LFS roundtrip'
gh --version
gh api --help > /dev/null
printf 'answer: 42\n' | yq -e '.answer == 42' > /dev/null
npm --version
npx --version
mkdir package
printf '{"name":"agentbox-offline-smoke","version":"1.0.0"}\n' > package/package.json
printf 'module.exports = 42;\n' > package/index.js
(cd package && npm pack --offline --ignore-scripts > /dev/null)
npm install --offline --ignore-scripts --no-audit --no-fund ./package/agentbox-offline-smoke-1.0.0.tgz
node -e 'if (require("agentbox-offline-smoke") !== 42) process.exit(1)'
if command -v pip3 >/dev/null; then
    python3 -m pip --version
    pip3 --version
    python3 - <<'PYTHON'
import zipfile
with zipfile.ZipFile("agentbox_smoke-1.0-py3-none-any.whl", "w") as wheel:
    wheel.writestr("agentbox_smoke.py", "VALUE = 42\n")
    wheel.writestr("agentbox_smoke-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: agentbox-smoke\nVersion: 1.0\n")
    wheel.writestr("agentbox_smoke-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: agentbox\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    wheel.writestr("agentbox_smoke-1.0.dist-info/RECORD", "")
PYTHON
    pip3 install --no-index --no-deps --target installed ./agentbox_smoke-1.0-py3-none-any.whl
    PYTHONPATH=installed python3 -c 'import agentbox_smoke; assert agentbox_smoke.VALUE == 42'
fi
