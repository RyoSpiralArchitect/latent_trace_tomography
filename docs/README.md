# Documentation

English | [日本語](README.ja.md)

Start with the [project README](../README.md), then read the
[Mistral checkpoint](../reports/mistral_bridge_20261029/README.md).
Both published checkpoints separate the saved primary abstention from post-hoc diagnosis.

## Reading paths

| Purpose | English | 日本語 |
|---|---|---|
| Project, setup, scientific boundaries | [README](../README.md) | [README](../README.ja.md) |
| Mistral result and replay (October 29) | [Report](../reports/mistral_bridge_20261029/README.md) | [レポート](../reports/mistral_bridge_20261029/README.ja.md) |
| Next answer-mapping diagnostic, design only | [Design](../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.md) | [小設計](../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md) |
| First live results and offline replay | [Report](../reports/output_only_bridge_20261023/README.md) | [レポート](../reports/output_only_bridge_20261023/README.ja.md) |
| V2 content/format/reference-set interface | [V2](../successors/oss_reliance_regime_v0/output_only_bridge_v2/README.md) | [V2](../successors/oss_reliance_regime_v0/output_only_bridge_v2/README.ja.md) |
| Earlier bounded bridge proposal (historical) | [Strategy](next_bridge_pilot.md) | [以前の作戦](next_bridge_pilot.ja.md) |
| Contribution and evidence rules | [Contributing](../CONTRIBUTING.md) | [開発への参加](../CONTRIBUTING.ja.md) |
| Authorization and data handling | [Responsible use](../RESPONSIBLE_USE.md) | [責任ある利用](../RESPONSIBLE_USE.ja.md) |

## Detailed research references

The following historical specifications remain in English. The bilingual root
README explains their main decisions; it is not a replacement specification.

- [Research contract](research_contract.md): estimand, evidence tiers, independent units.
- [Architecture](architecture.md): observation, calibration, and evaluation boundaries.
- [Roadmap](roadmap.md): gates from synthetic controls to prospective transfer.
- [Industrial thesis](industrial_thesis.md): a bounded audit instrument, not a thought reader.
- [Prior art](prior_art.md): related research and the intended contribution.
- [Frozen OSS-1 protocol](../protocols/oss_reliance_regime_v0/protocol.json).
- [As-run v1 source contract](../successors/oss_reliance_regime_v0/output_only_bridge_v1/README.md).

## Translation and evidence policy

English and Japanese narrative documents must preserve counts, denominators,
commands, identifiers, uncertainty, and claim strength. Neither translation may
upgrade development data into prospective evidence. If versions disagree, inspect
the linked machine-readable contract and data; do not silently choose the stronger
claim. Submit a correction to both narrative versions.

Hash-pinned protocols, archived source, manifests, and raw observations are not
rewritten for translation. Add a companion document instead. The public replay
checks all six v1 source hashes; the original abstention remains the primary result.

The core package, October 29 replay and answer-mapping design support Python 3.10+.
The October 23 archived replay needs Python 3.12. All documented offline examples
are call-free.
