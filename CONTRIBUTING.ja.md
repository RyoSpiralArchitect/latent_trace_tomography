# 開発への参加

[English](CONTRIBUTING.md) | 日本語

Latent Trace Tomographyは、証拠を重視する研究リポジトリです。
変更後もscientific claim、artifact identity、failure surfaceを確認できて、初めて変更が完了します。

## 実装前の確認

1. estimandと、その操作的なground truthを明記します。
2. observation projectionとheld-out challenge projectionを分けます。
3. positive/negative anchor、matched null、棄権規則を定義します。
4. 結果を見る前に、model、tokenizer、task、case、projection、split、decoding、featureのidentityを固定します。
5. モデル/APIを呼ばずに構造をpreflightで確認し、評価ラベルやchallenge outputを見る前に計画・予測artifactをlockします。

現在のpreflightは、契約の形、phase order、凍結ファイルのハッシュ、実行可能な設計上の不変条件を検証します。
設計検証の通過はlive実行の許可ではありません。具体的なconstruction/discoveryの前提、registryの証拠、
モデルの利用可能性、provider capability、予算の妥当性は、それぞれの実行段階で確認する必要があります。

結果を見てから閾値やfactor gridを決めたprotocolを「事前登録」と呼ばないでください。
現在の合成protocolは意図的にretrospectiveとしています。

## 証拠のルール

- raw responseは追記のみとします。
- レビュー済みのrun directoryは上書きしません。
- protocol、prompt、response、split、manifestのidentityには、完全なSHA-256 digestを使います。
- 修正は、parent hash、理由、置き換えるIDを持つsuccessor artifactとして追加します。
- parse failure、棄権、API error、予定した全caseをレポートに残します。
- 資格情報を設定ファイルやartifactへ入れません。
- live targetを追加する前に、[RESPONSIBLE_USE.ja.md](RESPONSIBLE_USE.ja.md)の許可、保存期間、redaction、公開要件を適用します。

## Feature boundary

primary detectorが使えるのはprompt/output textと対応づけ用metadataだけです。
provider/model identity、latency、usage、request ID、system fingerprint、logprobs、内部観測は
provenanceまたはcontrol variableであり、primary featureではありません。

OSS内部の介入データは`InternalObserver`の境界内に置き、凍結したcausal profileまたはcalibration labelだけを介して渡します。
proprietary backendの抽象化にinternal observerを公開してはいけません。

## テスト

~~~bash
make test
make preflight
make smoke
~~~

新しいlive backendには、mockによるpayload/extractionテスト、retry/resumeテスト、指定値と実際の送信値の記録、
provider capabilityのsnapshot、呼び出し０回のpreflightテストが必要です。

Ruffとlint ruleは`pyproject.toml`で固定し、環境間で検証を再現できるようにしています。
ツールの更新には別のレビューが必要です。既定値の変更に合わせるためだけに、ハッシュ固定したソースを整形し直さないでください。

## 主張の言葉

「較正したequivalence classと整合する」「held-out failure behaviorを予測する」という表現を使います。
output-onlyの証拠を「思考の復元」「モデルの心を読む」「内部circuitの証明」と呼ばないでください。

## ライセンス

プロジェクトのコードと文書への貢献は`AGPL-3.0-only`（GNU Affero General Public License, version 3 only）で提供します。
第三者の資料を追加するときは由来を保全し、意図した再配布がそのライセンスで認められることを確認してください。
