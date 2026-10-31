# Mistral bridge checkpoint — 2026-10-29

[English](README.md) | 日本語 · [Replay用データ](data/manifest.json) · [次の小設計](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md)

## 結論

APIへの112生成はすべて完了しました。**一次結果は「参照範囲外として棄権」です。**
参照群による予測の成功を示したものではありません。

弱観測の出力はすべてA/Bとして解釈できましたが、caseごとに対応づけた回答列が
9参照のいずれとも完全一致しませんでした。v2の照合規則を変えずに空のsupportを保存し、
その後でtargetのchallenge 32件を取得しました。今回は選択的なprospective transferを実証していません。

別枠の事後診断では、課題の正答との一致は **弱観測70/80件、challenge 30/32件**でした。
誤答12件はすべて、反転した回答対応表の `FAIL → A` 条件でした。
6種類のpromptを2回ずつ測定した結果です。この偏りはanswer mappingを調べる動機になりますが、
内部のcodebook機構、cue回路、隠れた推論過程を同定したものではありません。

## 実験と実行記録

新しいcontentを使ったpanelは、2 content、弱観測40種類、challenge 16種類のpromptを持ち、
それぞれ2回反復します。弱観測ではsemantic evidenceとadvisory cueを一致させます。
challengeでは両者を衝突させ、通常の表示とtable表示を用います。
両phaseでPASS/FAILの判断と、通常・反転のA/B対応表を組み合わせます。

参照群は、宣言済みの3 base lineageから作った9 controlled descendantです。
**独立した9 model familyではありません。** 構築条件の名称も、検証済みの機構ラベルではありません。
OSSとAPIには同じprompt文字列を使いますが、OSSのraw completionとproviderのchat実行では
runtime条件が異なります。weightだけを変えた比較ではなく、因果較正への接続も未解決です。

| 測定 | 保存済みの参照run | Mistral target run |
|---|---:|---:|
| 完了した生成 | 1,008 | 112：weak 80＋challenge 32 |
| 物理forward数 | 6,112 | このAPIからは観測できません |
| 記録された所要秒数 | receiptのwall timeで136.980 | 生成phase合計398.579 |

参照ledgerの記録は136.989秒です。receiptとは計時範囲がわずかに異なります。
これらの時間からモデル間の速度比較はしません。参照runはAPI runより前に行われています。
今回のレポート作成とreplayでは、**モデル・APIを新たに呼び出していません。**

API側は `mistral-large-4`、temperature 0、最大32出力tokens、reasoning effort none、
1 requestにつき1応答、`standard_only` で実行しました。
返されたモデル名は全件で一致し、finish reasonもすべて `stop` でした。
再試行・モデル代替はなく、モデル情報取得のGETが別に1回あります。
返されたモデル名だけでは、不変のweight snapshotを特定できません。
providerを変えた新しいtarget実験であり、以前のproviderと同一endpointでの再現試験ではありません。

使用量は入力12,096、出力422、合計12,518 tokensでした。
uncachedの公開価格による概算は **$0.01821452**、予約枠は$0.32693248、上限は$0.50です。
いずれも過去の価格による試算であり、請求確定額や現在の見積もりではありません。
保存した価格記録には[Mistralの公式モデル資料](https://docs.mistral.ai/models/mistral-large-4-0)と、
10月29日の確認日を記しています。[実行概要](data/execution.json)。

## 一次評価：棄権をそのまま残す

10月29日04:46:16 JSTに予測を保存し、04:46:35 JSTにtargetのchallenge取得を始めました。
公開した時刻と原本のハッシュは、保存済みのローカル記録の順序を支えます。
**第三者による実行証明ではありません。** 公開replayもblind実行環境を再構築するものではありません。

| 指標 | 参照群による条件付き予測 | 全9参照のbaseline |
|---|---:|---:|
| 予測可能なchallenge集合 | 0/32：棄権 | 32/32 |
| Containment | 未評価：予測なし | 32/32 |
| 解釈可能なsingleton集合 | 0 | 0 |
| 集合の構成 | 空 | `{A,B}` が22件、`{A,B,unresolved}` が10件 |

baselineの集合はすべてAとBの両方を含みます。targetのchallenge出力もすべてA/Bなので、
32/32のcontainmentは、今回は **回答を絞り込めたことを意味しません。**
条件付き予測のJSONにある `contained: 0` も、32件の誤予測ではなく、予測自体がないことを表します。
有限の観測集合は確率でも、将来のcoverage保証でもありません。[保存した予測](data/forecast.json)。

弱観測の形式はexact marker 45件、bare symbol 35件、challengeはそれぞれ21件、11件でした。
unresolvedは両phaseとも0件です。既存のv2 parserは両形式から回答内容を取り出し、形式適合とは別に扱います。
**今回の棄権はformat failureではなく、回答内容の不一致によるものです。**
logprobs、内部状態、provider名、latency、使用量は照合の特徴量に含めていません。
v2 moduleの保守的なラベル `development_only_not_prospective_validation` も維持しています。
外側のrunで予測を固定しても、transfer成功という主張には変わりません。

## 事後診断：反転した回答対応表

以下は取得後に選んだ分析です。一次評価を置き換えたり、照合規則を変更したりはしません。
正答は凍結済みgeneratorのcell定義から求め、実際のprompt中のコード比較とResponse mapを読む
別計算でも一致を確認しています。

| Projection | 課題の正答との一致 |
|---|---:|
| Weak baseline | 16/16 |
| Rule paraphrase | 16/16 |
| Evidence reorder | 12/16 |
| Irrelevant distractor | 12/16 |
| Cue salience attenuation | 14/16 |
| Challenge conflict | 14/16 |
| Challenge table | 16/16 |

弱観測の10誤答は、semanticとcueがともにFAILで、対応表が `PASS → B / FAIL → A` の条件でした。
どちらのrouteもAを要求するため、Bという回答だけではcue relianceを示せません。
challengeの2誤答も `FAIL → A` の条件ですが、こちらはcueとsemantic evidenceが衝突しています。
mappingへの感受性、cueへの感受性、文脈との相互作用など、複数の説明が残ります。
今回のAPI試験では、内部への標的介入は行っていません。

同一promptの反復間で回答が変わった組は、weak 0/40組、challenge 0/16組でした。
形式だけが変わった組は各phaseで5組あります。12誤答は6種類のpromptから得られた測定であり、
独立した12件の失敗例ではありません。この小標本から一般的な決定性や失敗頻度は主張しません。

最も近い参照01・02でも、弱観測80件中10件が不一致でした。
他は03が22件、04が20件、05が16件、06・09が14件、07・08が12件です。
最も近い参照でも、保存済みの完全一致規則ではsupportになりません。
近似一致へ変更して今回の結果を救済することはしていません。
[再計算した分析と誤答記録](data/analysis.json)。

## 次の小設計と実用への接続

参照群を増やす前に、新しいcontentでPASS/FAILを直接答える条件と、通常・反転のA/B対応表を比べます。
さらに判断結果を先に与え、証拠比較を求めないcontrolを加えます。
[Answer-mappingの小設計](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md)は、
**本課題96件＋mapping-only control 16件＝最大112件**、2回反復、別枠の上限$0.50です。
API clientは含めず、`live_execution_authorized: false` と明示しています。

主な記述的比較は、本課題とmapping-onlyのそれぞれで求める「反転条件の誤答率 − 通常条件の誤答率」です。
直接回答との比較、semantic・cue・layout別の内訳、unresolvedも残します。
差がない結果や混在した結果を受けて、panelを自動で調整することはしません。

実用上の問いもあります。**出力指示は、測定条件であると同時に、アプリケーションのinterface設計でもあります。**
新しい課題で誤りの少ない回答形式を確認できれば、内部機構を復元しなくてもAPIの使い方に活かせます。
ただし、直接のPASS/FAIL回答は今回まだ試していません。仮説であり、推奨する修正や本番運用の保証ではありません。
指示の変更は計算過程も変え得るため、この対照だけで内部の処理段階を切り出すこともできません。

## 公開する証拠とoffline replay

公開データには、合成prompt/outputの **1,120観測すべて**を含めます。
内訳は参照1,008件、API 112件です。観測のfieldは `target_id`、`case_id`、`projection_id`、
`replicate_id`、`prompt_text`、`output_text` の6つだけです。
設計要因とprovenanceはinventoryに分け、targetのchallenge出力を予測器の入力へ渡しません。

[export_public.py](export_public.py)は、今回レビューした原本のハッシュと完全一致する入力だけを受け付けます。
元のreceipt・artifactの対応とevent chainを確認してから、許可したfieldだけを取り出します。
元のreceipt、live runner、鍵、端末内のpath、provider response ID、tensor・token単位のtelemetryは公開しません。
[公開manifest](data/manifest.json)には原本と公開ファイルのハッシュを残します。
公開データの検証はできますが、ハッシュだけで非公開原本の中身を第三者が検査できるわけではありません。
これは公開用に派生させた資料であり、元のrunの書き換えではありません。

repositoryのrootから、Python 3.10以降で実行できます。鍵は不要です。

```sh
python3 -S reports/mistral_bridge_20261029/replay.py
python3 -S -m unittest discover -s reports/mistral_bridge_20261029 -v
```

replayは公開ファイルとv2ソースのハッシュ、slotの過不足、保存済み予測、ローカル記録の順序、
一次評価と事後分析の再計算を確認します。テストではtarget challengeの入力隔離、欠損・重複の拒否、
余分なtelemetryの拒否、正答計算の照合、改変の検知も確認します。
再現できるのは **保存済み観測の分析**です。新たな推論の再現や、第三者によるprovider実行証明ではありません。

evidence tierは `prospective_engineering_pilot_not_causal_validation` です。
凍結済みOSS-1契約と[10月23日のcheckpoint](../output_only_bridge_20261023/README.ja.md)は変更しません。
今回の2 contentと反復測定から、機構復元、校正済み確率、未知familyへの一般化は主張しません。
