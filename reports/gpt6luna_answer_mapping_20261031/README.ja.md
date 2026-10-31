# GPT-6 Luna answer-mapping checkpoint — 2026-10-31

[English](README.md) | 日本語 · [Replay用データ](data/manifest.json) · [次の小設計](../../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.ja.md)

## 結果

112件の生成はすべて完了しました。**固定したparserでは112件すべてが正答でしたが、
指定した `FINAL:` 付きの回答は86件でした。** 記号だけの回答も実行前から許容していたため、
残る26件を後からparserを変えて救済したわけではありません。

| 条件 | 正答 / 予定数 | Exact marker | Bare symbol |
|---|---:|---:|---:|
| Full task：直接PASS/FAIL | 32/32 | 32 | 0 |
| Full task：standard map | 32/32 | 13 | 19 |
| Full task：inverted map | 32/32 | 25 | 7 |
| Mapping-only：standard map | 8/8 | 8 | 0 |
| Mapping-only：inverted map | 8/8 | 8 | 0 |
| 合計 | 112/112 | 86 | 26 |

事前に定めた「invertedの誤り率 − standardの誤り率」は、両課題とも **0ポイント**でした。
解釈できない回答と拒否応答はいずれも0件です。同じpromptを2回送った56組では、読み取った答えが
すべて一致しました。追加の **post-hoc** 分析では、8/56組で回答文字列と形式が変わっていました。
変化したのは `FINAL:` の有無で、答えは変わっていません。

これは小規模な挙動診断であり、内部の計算段階を復元した結果ではありません。
以前の[Mistralの参照範囲外棄権](../mistral_bridge_20261029/README.ja.md)はそのまま保持します。
今回のrunでは、OSSで較正した参照profileを推定していません。

## 出力を得る前に固定したもの

[元の設計](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md)の
prompt、順序、採点キー、parser、記述的な比較をそのまま使いました。
別途許可された出力前の実行計画で、候補だったMistralから `gpt-6-luna` に対象を変更し、
API設定を固定しています。元の設計の「実行未許可」というfieldは書き換えていません。

内訳はfull task 96件、判断を先に与えるmapping-only control 16件です。
56種類のpromptを各2回測定しました。Full taskでは、内容2種類、PASS/FAIL、advisory cueの
一致・衝突、証拠のbaseline・reorder、直接回答・通常対応表・反転対応表を組み合わせています。
Mapping-onlyでは内容2種類、与えたPASS/FAIL、通常・反転対応表を組み合わせ、
証拠比較とadvisory cueは含めません。

Providerへ送ったのはprompt本文だけで、query IDや採点情報は送っていません。
Scorerに渡すのもquery IDと出力文字列だけです。Provider名、token使用量、所要時間、
応答metadata、内部状態、logprobsは採点の特徴量に含めません。
内容は2種類で、条件の組合せと反復は互いに依存します。**112件を独立な被験体とは数えません。**

Responses APIを使い、temperature 0、reasoning effort `none`、最大32出力tokens、
default service tier、tool・streamingなし、truncation無効、`store:false`に設定しました。
最後の設定はprovider側での保存が一切ないという保証ではありません。
返却されたmodel名は全件 `gpt-6-luna` と一致しましたが、aliasだけでは不変のcheckpointを
特定できません。再試行・モデルの差し替えはなく、モデル情報取得のGETが別に1回あります。

## 実行記録とAPI監査への示唆

実行時間は292.889秒でした。使用量は入力11,144、出力732、合計11,876 tokensです。
保存した10月31日の単価では、通常入力料金による概算はUSD 0.0014804、
全入力を固定済みの短いcontext向けcache書き込み最高単価で計算した概算上限はUSD 0.003152でした。
実行の費用上限はUSD 0.50です。これらは過去の使用量に基づく概算で、請求額や現在の見積もりではありません。
[実行概要と価格の出典](data/execution.json)。

`FINAL:` 付きの形式だけを受け付けるシステムなら、同じ保存済み回答のうち受理できるのは86/112件です。
今回の研究用parserなら112/112件を受理できます。これは受理規則をofflineで比べた結果であり、
新たなモデル実験ではありません。正答と指定形式の遵守を、監査で別々に記録する意義が見えました。
別のpromptやparserによって将来の応答が改善することまで示したわけではありません。

今回、temperature 0でも回答形式は一定ではありませんでした。その原因がモデル・推論基盤・
別の要因のどれかは、この観測から特定できません。前回のMistralとはモデルもprompt panelも異なるため、
優劣比較、同じ失敗の再現、未知familyへの一般化も主張しません。
112件を独立標本とみなした信頼区間や有意差検定は行いません。

## 公開する証拠とreplay

公開する112件の回答は、`query_id` と `output_text` の2 fieldだけで構成します。
対応するpromptと採点キーは元の設計のfixtureで確認できます。集計した実行metadataは別ファイルです。

[Exporter](export_public.py)は、レビューした原本のhashと一致する入力だけを受け付けます。
リクエスト・応答・保存のイベントと終了receiptの対応を確認し、明示したfieldだけを公開用に取り出します。
元のreceipt、端末内のpath、live runner、鍵、provider response ID、応答ごとのtelemetryは公開しません。
[Manifest](data/manifest.json)に原本と公開ファイルのhashを残しています。
公開データと分析は検証できますが、hashだけでは非公開原本を閲覧したり、provider実行を独立に証明したりはできません。
原本を書き換えたものではなく、公開用に派生させた記録です。

Repositoryのrootから、Python 3.10以降で実行できます。鍵は不要です。

```sh
python3 -S reports/gpt6luna_answer_mapping_20261031/replay.py
python3 -S -m unittest discover -s reports/gpt6luna_answer_mapping_20261031 -v
```

Replayでは、元の設計ソースと公開ファイルのhash、slotの過不足、保存済み分析、実行集計の計算を検証します。
テストは欠損・重複slot、余分なtelemetry、unresolvedを含む分母、重複JSON key、非有限数、
改変検知、公開境界を対象にしています。モデル・APIの追加呼び出しは0回です。
Evidence tierは `descriptive_behavioral_diagnostic_not_mechanistic_validation` です。

## 次の境界

[96件のoutput-contract設計](../../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.ja.md)では、
同じ判断課題で `FINAL: A/B` を求める条件と、`A/B` だけを求める条件を比べます。
正答かつ指定形式、正答、形式遵守を別々に数えます。今回の結果を見て選んだ問いであり、
以前から立てていた機構仮説ではありません。未実行で、live実行の準備もまだ完了していません。
公開やmergeは、次のAPI実験の実行許可にはなりません。
