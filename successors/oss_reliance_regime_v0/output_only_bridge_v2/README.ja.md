# Output-only bridge v2：回答内容・形式・reference集合

[English](README.md) | 日本語

[v1の研究checkpoint](../../../reports/output_only_bridge_20261023/README.ja.md)に続く追加実装です。
v1のparser、保存した一次評価の棄権、公開データ、凍結済みOSS-1 contractは変更しません。
model loader、provider client、自動retry、live実行コマンドは含みません。

## ２つの変更

1. **回答内容と形式適合を分けます。** 前後の空白を除いた文字列が、厳密に`FINAL: A` / `FINAL: B`または
   裸の`A` / `B`なら、内容チャンネルに回答記号を渡します。形式適合とするのは前者だけです。
   空文字、複数marker、説明文、小文字、`FINAL: AB`など、それ以外はすべて未解決とします。
   raw observationは変更しません。裸の記号を黙って形式適合の成功に数えることもありません。
   保存したv1の行単位parserと異なり、v2は説明文の後にfinal markerが続く形も受理しません。
   これは意図した全文のresponse contractで、v1を単に緩めたものではありません。過去のv1 scoreをこの規則で採点し直しません。
2. １つのregime labelではなく、**caseごとに一致する全reference**を返します。
   同じcase/projection/replicateのslotで、正規化した弱観測の回答をすべて照合します。
   集計した周辺度数が同じだけでは一致としません。形式のcount、model identity、cluster labelは照合に使いません。
   cluster labelはprovenanceと集計のための宣言であり、独立性の証明ではありません。

対象の回答内容が未解決なら棄権します。未解決のreferenceは除外理由とともにcohortの報告へ残します。
完全な観測があっても一致しないreferenceも報告します。support setが空なら棄権し、
１referenceだけが一致しても、機構を一意に特定できたとは扱いません。

challengeの各slotでは、一致したreferenceが実際に返した回答の有限集合を出力します。
未解決の回答と形式ラベルも別々に残し、曖昧さを保持します。
この集合は、**較正済み確率、信頼区間、API挙動の上下限、将来のcoverage保証ではありません**。

## Interface

`latent_trace_tomography.reference_bridge.build_reference_report(bundle)`が受け付けるfieldは、次のものだけです。

- `schema_version`：`ltt_output_bridge_v2_inputs_v1`
- `weak_inventory`、`challenge_inventory`：４fieldのslotのlist
  （`case_id`、`projection_id`、`replicate_id`、`prompt_text`）
- `target_weak`：６fieldのobservation（slotのfieldに`target_id`と`output_text`を追加）
- `reference_weak`、`reference_challenge`：reference IDから６fieldのobservation listへの対応
- `reference_clusters`：reference IDから宣言したcluster IDへの対応

inventoryの欠落と重複を拒否し、promptは完全一致を要求します。
対象のchallenge output、logits、usage、model metadata、未知のfieldはestimatorの境界で拒否します。
入力順序は結果に影響しません。すべての入力、観測規則、実装bytesのハッシュをreportに記録します。
反復を独立な被験体とは数えません。これらの検査が確認するのはデータの整合性で、workerの隔離ではありません。

追加したCLIはoffline bundleを１つ読み、新しい出力ファイルだけを排他的に作成します。

```sh
PYTHONPATH=src python3 -m latent_trace_tomography.reference_bridge \
  --bundle /path/to/input_bundle.json --out /path/to/new_report.json
```

## 開発用のdemonstration

```sh
python3 -S successors/oss_reliance_regime_v0/output_only_bridge_v2/development_demo.py \
  --out /path/to/new_development_report.json
```

このdemonstrationは、すでに開示したv1データを使います。estimatorへ渡すAPI出力は弱観測だけですが、
データセットも設計判断も、もはやblindではありません。
開発上の期待値は`target-01`、`target-02`、`target-08`の一致です。
APIの弱観測の形式countは、exact marker 68件、bare symbol 12件のまま残します。
これは実装のregressionであり、**prospective transferの検証ではありません**。
全v2 reportには`development_only_not_prospective_validation`と記録します。
過去のv1の棄権を格上げせず、このoffline toolだけでlive lockを確立したとも主張しません。

新しいlive試験の前には、新しいcontent/seedと予算を選び、v2の規則と実装identityを保存し、
具体的なinventoryを固定します。対象のchallenge outputを開く前にreportを保存してください。
別途残っているcausal calibrationの不足も明示します。このPRは、その実験を許可・開始するものではありません。
提案する順序と、集合に回答が含まれることと有用な予測の違いは、[次期pilotの作戦](../../../docs/next_bridge_pilot.ja.md)を参照してください。
