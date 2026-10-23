# 責任ある利用

[English](RESPONSIBLE_USE.md) | 日本語

Latent Trace Tomographyは、許可されたモデル評価、研究、incident diagnosis、governanceのためのプロジェクトです。

## 必要な許可

対象を利用できるのは、自ら所有・運用している場合、明示的な監査許可がある場合、または公開endpointを
文書化された条件の範囲で使う場合です。認証、rate limit、安全制御、課金制御、技術的な制限を回避しないでください。
model weight、秘密、非公開chain of thought、学習記録、個人情報の抽出に使ってはいけません。

## データの扱い

promptとoutputには、機密情報、規制対象の情報、著作物、個人情報が含まれる場合があります。
live運用では、次を定義する必要があります。

- 収集目的と法令・契約上の根拠
- 保存期間と削除時期
- 保存時と通信時の暗号化
- raw evidenceへのrole-based access
- 公開artifactのredaction rule
- 保存を許可するprovider response fieldのallowlist
- 保存前の資格情報、cookie、authorization headerの除去

SHA-256 manifestが提供するのは整合性であり、機密性やアクセス制御ではありません。

## 報告の範囲

観測できるresponse surface、較正したequivalence class、不確実性、棄権理由を報告します。
output-only推定を、非公開の内部circuit、隠れた思考、精神状態、意図の証明として示してはいけません。

医療、法務、金融、雇用、教育、安全、重要インフラなど、重大な影響を伴う判断では、この計測器は補助的な証拠に限ります。
分野の専門家によるレビューと、異議申立て・escalationの経路を設けてください。

## Dual-use review

active queryingはモデルやinference stackのfingerprintingにも使えます。
live studyの前にquery planの必要性を記録し、予算を最小限にし、適切な場合は対象の所有者へ監査を知らせます。
exact probeの公開が悪用につながらないかも評価してください。
機微なendpoint fingerprintの一般公開より、関係者と調整した開示を優先します。
