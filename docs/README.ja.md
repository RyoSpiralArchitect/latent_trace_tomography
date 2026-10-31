# ドキュメント

[English](README.md) | 日本語

まず[プロジェクトのREADME](../README.ja.md)、次に
[GPT-6 Luna checkpoint](../reports/gpt6luna_answer_mapping_20261031/README.ja.md)をお読みください。
正答と出力形式の遵守を分けて報告しています。以前のbridge checkpointの棄権も、事後診断とは別に保持します。

## 目的別の入口

| 目的 | English | 日本語 |
|---|---|---|
| 概要・セットアップ・主張の範囲 | [README](../README.md) | [README](../README.ja.md) |
| 10月31日のGPT-6 Luna結果とreplay | [Report](../reports/gpt6luna_answer_mapping_20261031/README.md) | [レポート](../reports/gpt6luna_answer_mapping_20261031/README.ja.md) |
| 次のoutput-contract試験：未実行 | [Design](../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.md) | [小設計](../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.ja.md) |
| 保存済み回答を採点する・モデルなしで動作を確かめる | [Guide](../successors/oss_reliance_regime_v0/output_contract_scoring_v1/README.md) | [採点と模擬実行](../successors/oss_reliance_regime_v0/output_contract_scoring_v1/README.ja.md) |
| 10月29日のMistral結果とreplay | [Report](../reports/mistral_bridge_20261029/README.md) | [レポート](../reports/mistral_bridge_20261029/README.ja.md) |
| 凍結済みの親answer-mapping設計 | [Design](../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.md) | [小設計](../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md) |
| 初回の実測結果とoffline replay | [Report](../reports/output_only_bridge_20261023/README.md) | [レポート](../reports/output_only_bridge_20261023/README.ja.md) |
| V2のcontent/format/reference-set interface | [V2](../successors/oss_reliance_regime_v0/output_only_bridge_v2/README.md) | [V2](../successors/oss_reliance_regime_v0/output_only_bridge_v2/README.ja.md) |
| 以前の小規模bridge試験の提案 | [Strategy](next_bridge_pilot.md) | [以前の作戦](next_bridge_pilot.ja.md) |
| 開発への参加と証拠の扱い | [Contributing](../CONTRIBUTING.md) | [開発への参加](../CONTRIBUTING.ja.md) |
| 実行許可とデータ管理 | [Responsible use](../RESPONSIBLE_USE.md) | [責任ある利用](../RESPONSIBLE_USE.ja.md) |

## 詳細な研究資料

以下の既存仕様書は英語の原本を維持しています。主要な設計判断は英日のルートREADMEで説明していますが、
READMEは仕様書の代わりではありません。

- [Research contract](research_contract.md)：estimand、証拠の段階、独立単位を定義しています。
- [Architecture](architecture.md)：観測、較正、評価の境界を説明しています。
- [Roadmap](roadmap.md)：合成対照からprospective transferへ進む条件をまとめています。
- [Industrial thesis](industrial_thesis.md)：思考を読む装置ではなく、範囲を限定した監査器としての用途を示しています。
- [Prior art](prior_art.md)：関連研究と目指す貢献を整理しています。
- [凍結済みOSS-1 protocol](../protocols/oss_reliance_regime_v0/protocol.json)。
- [v1実行時のsource contract](../successors/oss_reliance_regime_v0/output_only_bridge_v1/README.md)。

## 翻訳と証拠の扱い

英日どちらでも、数値、分母、コマンド、識別子、不確実性、主張の強さを揃えます。
翻訳を理由に開発用データをprospective evidenceへ格上げしません。
記述が食い違う場合は、リンク先の機械可読な契約とデータを確認してください。
強い方の主張を黙って採用せず、両言語の文書を修正します。

ハッシュ固定したprotocol、実行時ソース、manifest、生の観測記録は翻訳で書き換えません。
必要な説明は別文書に追加します。公開replayはv1の６ソースすべてのハッシュを検証し、
元の棄権を一次結果として維持します。

core package、10月29日・31日のreplay、両probe設計はPython 3.10以降に対応しています。
10月23日の保存済みreplayにはPython 3.12が必要です。
掲載しているofflineの実行例では、モデルやAPIを呼び出しません。
