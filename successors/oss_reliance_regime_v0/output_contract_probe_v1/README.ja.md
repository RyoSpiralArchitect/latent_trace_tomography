# Output-contract probe v1 — 設計のみ

[English](README.md) | 日本語 · [定義](design.json) · [Manifest](fixtures/manifest.json)

[GPT-6 Lunaの実験](../../../reports/gpt6luna_answer_mapping_20261031/README.ja.md)では、
読み取った答えは112/112件すべて正答でしたが、指定したmarkerを付けたのは86/112件でした。
また、反復56組のうち8組で形式が変わりました。
次は、記号だけを明示的に求めると、**正答と指定形式を同時に満たす割合**が変わるかを調べます。
結果を見てから選んだ設計であり、以前から立てていた機構仮説の検証ではありません。

## 固定したpanel

| 課題 | 要因 | Promptの種類 | 2回反復 |
|---|---|---:|---:|
| Full task | 2内容 × 2判断 × 2 cue × 2対応表 × 2指定形式 | 32 | 64 |
| Mapping-only | 2内容 × 2判断（提示済み） × 2対応表 × 2指定形式 | 16 | 32 |
| 合計 | | 48 | 96 |

指定形式は `FINAL: A/B` と、記号だけの `A/B` です。通常・反転の両対応表を含めます。
Full taskのlayoutはbaselineに固定し、直接PASS/FAILで答える条件とreorderは含めません。

条件に当てはまる親設計のcaseを、観測された回答によらずすべて採用します。
Marker条件のpromptは親設計と同じbytesです。Bare条件では、対応表2行と末尾の出力指示だけを変更します。
証拠、docket、cue、対応表の意味、正答は変えません。同じ2種類の内容を意図的に再利用して条件を対応させるため、
新しい独立標本ではありません。反復のpromptも同一で、順序はgeneratorのhash規則で固定しています。

定義、96件のrequest、採点キーは、結果取得後にローカルで保存した設計と同じbytesを維持しています。
Generatorだけを、非公開の実行機に依存しない形で書き直しました。公開manifestには、その新しいソースと
変更していない親generatorのhashを記録しています。IDは設計要因を含む監査用の結合キーであり、
モデル入力ではありません。将来のtransportでも送信するのは `prompt_text` だけです。

## 採点契約：live scorerは未実装

- 答えの読取り：親parserの規則どおり、外側の空白だけを除き、`FINAL: A/B` または記号A/Bを受理します。それ以外はunresolvedです。
- 指定形式の遵守：外側の空白を除いた後、marker条件では `FINAL: A` または `FINAL: B`、bare条件ではAまたはBのみを認めます。誤答でも形式が正しければ、この指標は満たします。
- Joint success：正答であり、かつ指定形式を守った回答です。Unresolvedはどちらも満たさず、分母から除きません。

主な記述的比較は「bareのjoint failure率 − markerのjoint failure率」です。
Full taskは各形式32件、mapping-onlyは各形式16件で、それぞれ計算します。
答えの誤り、形式違反、unresolved、対応するjoint outcome、反復間の変化は別々に残します。
親caseと反復番号を揃えて形式間を対応させます。依存する96件を独立標本と数えたり、そこから有意差を主張したりはしません。

観測上、答えの誤りを増やさずjoint failureが減れば、このpanelでのinterface改善候補とします。
差がない結果、混在した結果、悪化した結果も残し、prompt探索やpanel拡張を自動では行いません。
Promptを変えると計算過程も変わり得るため、内部の一段階を切り出す介入ではありません。
Structured output、parserによる修復、モデル比較、因果attributionは対象外です。

## 実行境界と次のPR

候補は引き続き `gpt-6-luna`、temperature 0、reasoning effort none、最大32出力tokens、toolなしです。
上限は96回・USD 0.50で、再試行・モデル代替・自動再開・Furnace作業は行いません。
次のrunで費用枠を確保する前に、利用可否と料金を再確認します。

`live_execution_authorized` は **false**、状態は `design_only_not_execution_ready` です。
このpackageにAPI clientやlive scorerは含めません。次の実装PRでは、上記3指標と境界テストを追加し、
まずモデルを呼ばない模擬実行を通します。その後、別途許可した実行計画を固定して、このpanelを動かします。
設計の公開だけでは、推論・prompt調整・OSS作業を許可しません。

Repositoryのrootから、Python 3.10以降で確認できます。

```sh
python3 -S successors/oss_reliance_regime_v0/output_contract_probe_v1/design.py verify
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/output_contract_probe_v1 -v
```

`prepare --out NEW_DIRECTORY` は上書きせずにrequestと採点キーを再生成します。
すべてのコマンドでモデル呼び出しは0回です。これはinterface診断の枝であり、
未解決のOSS causal-calibrationへの接続は、別の研究課題として残ります。
