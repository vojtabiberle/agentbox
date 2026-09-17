# Image dependency security assessment

Assessed 2026-09-17. Scope: the Linux amd64 base/Python/PHP images published with
[v0.4.0](https://github.com/vojtabiberle/agentbox/releases/tag/v0.4.0).
Raw Grype matches are package-version matches, not proof of exploitable code paths.
No findings are hidden by scanner exclusions or blanket CVE waivers.

## Assessment and fixes

| Component | Exposure and decision | Replacement |
| --- | --- | --- |
| npm bundle | Agents use npm to fetch and unpack untrusted packages. Archive exhaustion, extraction, matching and signature-verification findings are relevant; container isolation does not protect writable workspaces or disk capacity. Replace the entire bundle, not selected nested modules. | npm 11.19.1, upstream archive with pinned SHA256; no older Fedora npm copy installed |
| git-lfs | The old Go dependency versions produced seven Critical matches. Update the supported tool, then inspect the exact Linux package dependency graph for the remaining SSH/OpenPGP matches. Do not label version matches as confirmed authentication bypasses. | Git LFS 3.8.0, upstream binary with architecture-specific SHA256 |
| gh | Embedded gRPC and Go module/network/crypto dependencies lagged the advisory fixes; network operations make updating preferable to assuming unused paths. | GitHub CLI 2.101.0, upstream binary with architecture-specific SHA256 |
| yq | Embedded network/text dependencies lagged security fixes. YAML processing may consume untrusted input. | yq 4.53.6, upstream binary with architecture-specific SHA256 |
| pip (Python stack) | Both findings involve processing/installing packages, an intended development operation. Fedora's recorded backports did not establish fixes for these two IDs. | pip 26.2.1, checksum-pinned upstream wheel; no older python3-pip RPM installed |

Versions/checksums were verified against official GitHub release metadata, npm registry
integrity metadata and PyPI metadata. This deliberately adds maintenance responsibility
for these pins; Fedora continues to maintain the other OS packages. Linux amd64 was
executed; ARM64 checksums are provided but native ARM64 execution is not claimed.

Upstream sources: [Git LFS](https://github.com/git-lfs/git-lfs/releases/tag/v3.8.0),
[GitHub CLI](https://github.com/cli/cli/releases/tag/v2.101.0),
[yq](https://github.com/mikefarah/yq/releases/tag/v4.53.6),
[npm](https://registry.npmjs.org/npm/11.19.1),
[pip](https://pypi.org/project/pip/26.2.1/).

## Remaining module matches

- `GO-2026-6355`, `GO-2026-6303`, `GO-2026-6354`: Grype reports High matches for
  `golang.org/x/crypto v0.54.0` embedded in Git LFS 3.8.0. These concern SSH channel
  handling and SSH server authentication. `go list -deps .` at upstream tag `v3.8.0`
  on Linux amd64 includes only `golang.org/x/crypto/md4` and `pbkdf2`, not `ssh`.
  Git LFS's own SSH wrapper starts an external SSH process. **Not affected by these
  specific advisories in the assessed build**; retain the raw matches and recheck
  when updating the binary. No local fork of the tool is justified for unreachable code.
- `GO-2026-5932`: the deprecated `x/crypto/openpgp` package is reported with Unknown
  severity for Git LFS and gh. Neither `go list -deps .` at Git LFS `v3.8.0` nor
  `go list -deps ./cmd/gh` at gh `v2.101.0` includes that package. **Not affected in
  these assessed builds**. gh does include `x/crypto/ssh`, at the patched v0.57.0.

Evidence sources: [Git LFS dependency manifest](https://github.com/git-lfs/git-lfs/blob/v3.8.0/go.mod),
[external SSH implementation](https://github.com/git-lfs/git-lfs/blob/v3.8.0/ssh/ssh.go),
[gh dependency manifest](https://github.com/cli/cli/blob/v2.101.0/go.mod),
[SSH channel advisory](https://pkg.go.dev/vuln/GO-2026-6355),
[SSH authentication advisory](https://pkg.go.dev/vuln/GO-2026-6303),
[SSH channel establishment advisory](https://pkg.go.dev/vuln/GO-2026-6354),
[OpenPGP advisory](https://pkg.go.dev/vuln/GO-2026-5932).
This is source dependency evidence for exact upstream tags, not a general guarantee
about other releases or a function-level analysis of stripped binaries.

## Scan results

| Stack | v0.4.0 Critical / High / Medium / Low / Unknown | Patched image |
| --- | --- | --- |
| base | 8 / 29 / 22 / 2 / 2 | 0 / 3 / 0 / 0 / 2 |
| Python | 8 / 29 / 24 / 2 / 2 | 0 / 3 / 0 / 0 / 2 |
| PHP | 8 / 29 / 22 / 2 / 2 | 0 / 3 / 0 / 0 / 2 |

The five residual matches are assessed above. Counts describe scanner findings,
not independently reproduced exploits. New database revisions can change counts.

## Complete original finding inventory

Grouped by artifact version and installed location. Every v0.4.0 finding is included;
repeated matches across stack variants are listed once. All rows except pip apply to
all three stacks. Critical/High/Medium/Low/Unknown are scanner severities.

| Artifact | Location | Original advisory matches |
| --- | --- | --- |
| @sigstore/core 2.0.0 | `/usr/lib/node_modules_22/npm/node_modules/@sigstore/core/package.json` | [GHSA-jfc7-64v2-mr8c](https://github.com/advisories/GHSA-jfc7-64v2-mr8c) (Medium) |
| brace-expansion 2.0.2 | `/usr/lib/node_modules_22/npm/node_modules/brace-expansion/package.json` | [GHSA-3jxr-9vmj-r5cp](https://github.com/advisories/GHSA-3jxr-9vmj-r5cp) (High), [GHSA-f886-m6hf-6m8v](https://github.com/advisories/GHSA-f886-m6hf-6m8v) (Medium), [GHSA-mh99-v99m-4gvg](https://github.com/advisories/GHSA-mh99-v99m-4gvg) (High), [GHSA-rgw5-rvv9-x895](https://github.com/advisories/GHSA-rgw5-rvv9-x895) (High) |
| golang.org/x/crypto v0.36.0 | `/usr/bin/git-lfs` | [GHSA-45gg-vh54-h5m9](https://github.com/advisories/GHSA-45gg-vh54-h5m9) (Medium), [GHSA-5cgq-3rg8-m6cv](https://github.com/advisories/GHSA-5cgq-3rg8-m6cv) (Critical), [GHSA-78mq-xcr3-xm33](https://github.com/advisories/GHSA-78mq-xcr3-xm33) (Medium), [GHSA-89gr-r52h-f8rx](https://github.com/advisories/GHSA-89gr-r52h-f8rx) (Critical), [GHSA-9m57-25v3-79x9](https://github.com/advisories/GHSA-9m57-25v3-79x9) (Medium), [GHSA-f5wc-c3c7-36mc](https://github.com/advisories/GHSA-f5wc-c3c7-36mc) (Critical), [GHSA-f6x5-jh6r-wrfv](https://github.com/advisories/GHSA-f6x5-jh6r-wrfv) (Medium), [GHSA-j5w8-q4qc-rx2x](https://github.com/advisories/GHSA-j5w8-q4qc-rx2x) (Medium), [GHSA-jppx-rxg9-jmrx](https://github.com/advisories/GHSA-jppx-rxg9-jmrx) (Critical), [GHSA-q4h4-gmj2-qvw2](https://github.com/advisories/GHSA-q4h4-gmj2-qvw2) (High), [GHSA-qpw4-5x99-6vjp](https://github.com/advisories/GHSA-qpw4-5x99-6vjp) (Medium), [GHSA-rm3j-f69w-wqmq](https://github.com/advisories/GHSA-rm3j-f69w-wqmq) (Critical), [GHSA-vgwf-h737-ff37](https://github.com/advisories/GHSA-vgwf-h737-ff37) (Critical), [GHSA-w879-237q-wc7r](https://github.com/advisories/GHSA-w879-237q-wc7r) (High), [GHSA-x527-x647-q7gg](https://github.com/advisories/GHSA-x527-x647-q7gg) (Critical), [GO-2025-4116](https://pkg.go.dev/vuln/GO-2025-4116) (High), [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932) (Unknown), [GO-2026-6303](https://pkg.go.dev/vuln/GO-2026-6303) (High), [GO-2026-6354](https://pkg.go.dev/vuln/GO-2026-6354) (High), [GO-2026-6355](https://pkg.go.dev/vuln/GO-2026-6355) (High) |
| golang.org/x/crypto v0.54.0 | `/usr/bin/gh` | [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932) (Unknown), [GO-2026-6303](https://pkg.go.dev/vuln/GO-2026-6303) (High), [GO-2026-6354](https://pkg.go.dev/vuln/GO-2026-6354) (High), [GO-2026-6355](https://pkg.go.dev/vuln/GO-2026-6355) (High) |
| golang.org/x/mod v0.37.0 | `/usr/bin/gh` | [GO-2026-6179](https://pkg.go.dev/vuln/GO-2026-6179) (High), [GO-2026-6180](https://pkg.go.dev/vuln/GO-2026-6180) (High) |
| golang.org/x/net v0.38.0 | `/usr/bin/git-lfs` | [GHSA-5cv4-jp36-h3mw](https://github.com/advisories/GHSA-5cv4-jp36-h3mw) (Medium), [GO-2026-4440](https://pkg.go.dev/vuln/GO-2026-4440) (Medium), [GO-2026-4441](https://pkg.go.dev/vuln/GO-2026-4441) (Medium), [GO-2026-4918](https://pkg.go.dev/vuln/GO-2026-4918) (High), [GO-2026-5025](https://pkg.go.dev/vuln/GO-2026-5025) (Medium), [GO-2026-5026](https://pkg.go.dev/vuln/GO-2026-5026) (High), [GO-2026-5027](https://pkg.go.dev/vuln/GO-2026-5027) (Medium), [GO-2026-5029](https://pkg.go.dev/vuln/GO-2026-5029) (Medium), [GO-2026-5030](https://pkg.go.dev/vuln/GO-2026-5030) (Medium), [GO-2026-5942](https://pkg.go.dev/vuln/GO-2026-5942) (High) |
| golang.org/x/net v0.55.0 | `/usr/bin/yq` | [GO-2026-5942](https://pkg.go.dev/vuln/GO-2026-5942) (High) |
| golang.org/x/sys v0.31.0 | `/usr/bin/git-lfs` | [GO-2026-5024](https://pkg.go.dev/vuln/GO-2026-5024) (Low) |
| golang.org/x/text v0.23.0 | `/usr/bin/git-lfs` | [GO-2026-5970](https://pkg.go.dev/vuln/GO-2026-5970) (High) |
| golang.org/x/text v0.37.0 | `/usr/bin/yq` | [GO-2026-5970](https://pkg.go.dev/vuln/GO-2026-5970) (High) |
| google.golang.org/grpc v1.82.1 | `/usr/bin/gh` | [GHSA-2v4p-qf9q-27wj](https://github.com/advisories/GHSA-2v4p-qf9q-27wj) (High), [GHSA-qc2q-p7wx-3px3](https://github.com/advisories/GHSA-qc2q-p7wx-3px3) (Medium), [GHSA-vp52-pcj8-j9qc](https://github.com/advisories/GHSA-vp52-pcj8-j9qc) (High) |
| ip-address 10.1.1 | `/usr/lib/node_modules_22/npm/node_modules/ip-address/package.json` | [GHSA-22jq-vg5j-6vgg](https://github.com/advisories/GHSA-22jq-vg5j-6vgg) (Medium), [GHSA-4xrf-jv44-h6hh](https://github.com/advisories/GHSA-4xrf-jv44-h6hh) (Medium), [GHSA-mwp4-54f8-5fhr](https://github.com/advisories/GHSA-mwp4-54f8-5fhr) (High) |
| pacote 19.0.2 | `/usr/lib/node_modules_22/npm/node_modules/pacote/package.json` | [GHSA-w4pp-8pjf-rmxw](https://github.com/advisories/GHSA-w4pp-8pjf-rmxw) (High) |
| pacote 20.0.1 | `/usr/lib/node_modules_22/npm/node_modules/@npmcli/metavuln-calculator/node_modules/pacote/package.json` | [GHSA-w4pp-8pjf-rmxw](https://github.com/advisories/GHSA-w4pp-8pjf-rmxw) (High) |
| picomatch 4.0.3 | `/usr/lib/node_modules_22/npm/node_modules/picomatch/package.json` | [GHSA-3v7f-55p6-f55p](https://github.com/advisories/GHSA-3v7f-55p6-f55p) (Medium), [GHSA-c2c7-rcm5-vvqj](https://github.com/advisories/GHSA-c2c7-rcm5-vvqj) (High) |
| pip 26.0.1 | `/usr/lib/python3.14/site-packages/pip-26.0.1.dist-info/METADATA` | [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v) (Medium), [GHSA-jp4c-xjxw-mgf9](https://github.com/advisories/GHSA-jp4c-xjxw-mgf9) (Medium) |
| postcss-selector-parser 7.1.1 | `/usr/lib/node_modules_22/npm/node_modules/postcss-selector-parser/package.json` | [GHSA-w9m9-85wc-3x92](https://github.com/advisories/GHSA-w9m9-85wc-3x92) (Low) |
| sigstore 3.1.0 | `/usr/lib/node_modules_22/npm/node_modules/sigstore/package.json` | [GHSA-52v5-jr5w-gjxr](https://github.com/advisories/GHSA-52v5-jr5w-gjxr) (High) |
| tar 7.5.11 | `/usr/lib/node_modules_22/npm/node_modules/tar/package.json` | [GHSA-23hp-3jrh-7fpw](https://github.com/advisories/GHSA-23hp-3jrh-7fpw) (Critical), [GHSA-8x88-c5mf-7j5w](https://github.com/advisories/GHSA-8x88-c5mf-7j5w) (High), [GHSA-gvwx-54wh-qm9j](https://github.com/advisories/GHSA-gvwx-54wh-qm9j) (Medium), [GHSA-r292-9mhp-454m](https://github.com/advisories/GHSA-r292-9mhp-454m) (High), [GHSA-vmf3-w455-68vh](https://github.com/advisories/GHSA-vmf3-w455-68vh) (Medium), [GHSA-w8wr-v893-vjvp](https://github.com/advisories/GHSA-w8wr-v893-vjvp) (Medium) |

## Verification and update policy

Image scans use the same Syft/Grype versions and database as the baseline, with full
RPM coverage checks and unchanged raw output. Publication now fails on Critical
findings. Other severities remain visible and require assessment; they are not
silently accepted by a version-independent exception.

Offline image checks exercise Git LFS clean/smudge roundtrips, gh startup/help, yq
parsing, npm/npx startup and an actual local package install. The Python stack also
installs a local wheel with pip. Claude startup and runtime CI protect agent compatibility.

Existing v0.4.0 image digests remain immutable. Install the patched agentbox release
and rebuild local images, or explicitly select the patched prebuilt release tag.
Refreshing an old versioned tag does not upgrade its version. Workspace dependencies,
user toolsets and project Dockerfile additions are outside this three-image assessment.
