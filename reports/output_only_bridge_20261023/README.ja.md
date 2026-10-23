# 炉とAPIの初回 output-only bridge — 2026-10-23

[English](README.md) | 日本語

実測は完走しました。**主結果は予測の棄権（coverage 0/32）**であり、API内部の機構推定や、予測転移の成功ではありません。
ただし、次に直す場所を形式適合と観測の識別力に分けて特定できました。

## 実行と監査

| 対象 | 実行数 | 所要時間 | 補足 |
|---|---:|---:|---|
| 炉・9個体 / 3モデル家系 | 1,008回答 | 129.8秒 | 6,050 physical forwards |
| API・弱観測 | 80 calls | 167.7秒 | challenge閲覧前に完了 |
| API・challenge | 32 calls | 63.9秒 | 凍結した棄権を維持 |

APIは `gpt-4.1-mini-2025-04-14`。今回の目的は最新モデルの能力競争ではなく、
出力のみの観測器を実際のAPIへ接続する小規模試験でした。
合計入力12,356 / 出力418 tokens、標準・キャッシュ割引なしの料金換算は **$0.0056112**。
請求書の実額ではありません。事前予約見積りは$0.372736、宣言上限は$0.50です。
単価は[公式料金表](https://developers.openai.com/api/docs/pricing)、
モデル選択は[公式モデルページ](https://developers.openai.com/api/docs/models/gpt-4.1-mini)を実行前に確認しました。
これらは実行時点の記録であり、現在の料金を示すものではありません。

新規の56種類の合成プロンプトを各2回使いました。学習プロンプト12,288件との完全一致は0件です。
これは内容分布やテンプレートの独立性を意味しません。9個体を独立9サンプルとは数えません。
炉は既存GPUジョブと共存していたため、所要時間をモデル間性能比較には使いません。

全件で暗黙再試行・モデル置換はありません。APIのlogprobsは要求せず、秘密値はローカル環境変数からメモリ内だけで使いました。
キーを炉には送らず、APIには合成プロンプトだけを送りました。`store=false`はゼロ保持保証とは異なります。
実行前の模擬テスト19件はMacと炉で通過し、解析・事後診断を含む最終27件もMacで通過しました。

レシート、全回答のハッシュ、APIリクエストの予約記録、イベントチェーン、forward数、
予測の再計算を照合しました。自己記録の整合性監査であり、第三者による実行証明ではありません。
ローカル時計で以下の順序も確認しました。

1. 弱観測完了: `2026-10-23T01:15:13.238636+00:00`
2. 予測／棄権保存: `2026-10-23T01:15:26.518438+00:00`
3. challenge開始: `2026-10-23T01:15:43.417940+00:00`

## 1. 形式違反が「参照外」に混ざった

凍結済みのparserは `FINAL: A` / `FINAL: B` を受理します。
APIは弱観測の12/80件、challengeの3/32件で `A` または `B` だけを返しました。
したがって一次評価では、弱観測68/80、challenge29/32がparse可能でした。
parse可能な回答はすべて課題のsemantic ruleと一致しています。

APIの51次元特徴量に完全一致するOSS参照はなく、事前固定規則により棄権しました。
これは「APIの内部計算が未知と判定できた」という意味ではありません。
この特徴量は形式適合性と回答選択を混ぜており、少なくとも形式差が参照不一致を生んでいました。
同一プロンプトの2反復では、APIの56組中45組が全文一致しました。temperature 0でも、今回の出力は完全には一致していません。

別ファイルの**事後診断だけ**で裸のA/Bも同じ回答記号として読んだところ、
弱観測80/80、challenge32/32がsemantic ruleと一致し、弱観測特徴量は下記3参照と一致しました。
元の回答、parser、特徴量、棄権、予測スコアは一切差し替えていません。
この診断を「事前に予測成功」と読み替えてはいけません。

## 2. 形式を直しても、弱観測の曖昧さは残る

以下の3個体は、弱観測80回答が**特徴量だけでなく全文一致**しました。
しかし、challengeでsemantic ruleに一致した数は異なります。

| 参照個体（構築条件名） | 弱観測のsemantic一致 | challengeのsemantic一致 |
|---|---:|---:|
| GPT-2 / mixed | 80/80 | 16/32 |
| GPT-2 / semantic | 80/80 | 32/32 |
| SmolLM2 / semantic | 80/80 | 30/32 |

構築条件名は内部機構のground truthではありません。
これは「有限の今回の弱観測では区別できなかった」という実測であって、
すべての入力・出力分布についての識別不能性定理ではありません。
それでも、この観測パネルから1個の内部機構ラベルや一意の将来挙動を割り当てることは支持されません。

具体例 `challenge:0:2:challenge_conflict:r0`:

```text
required_code == candidate_code   → 課題の法則では PASS
advisory ribbon = FAIL            → cueとは衝突
response map: PASS → A, FAIL → B

GPT-2 / mixed:     \nFINAL: B
GPT-2 / semantic:  \nFINAL: A
SmolLM2 / semantic:\nFINAL: A
```

この差は**出力で観測した差**です。既存のsemantic介入点の盲点が解消した証拠ではありません。

## 全個体を残した一次評価

分母には形式失敗を含みます。semantic一致は課題の法則への一致であり、内部のsemantic reliance推定ではありません。

| target | 構築条件／対象 | 弱観測semantic一致 /80 | challenge semantic一致 /32 | challenge parse /32 |
|---|---|---:|---:|---:|
| 01 | GPT-2 mixed | 80 | 16 | 32 |
| 02 | GPT-2 semantic | 80 | 32 | 32 |
| 03 | GPT-2 surface | 52 | 12 | 32 |
| 04 | Pythia mixed | 64 | 16 | 32 |
| 05 | Pythia semantic | 68 | 26 | 30 |
| 06 | Pythia surface | 72 | 0 | 32 |
| 07 | SmolLM2 mixed | 78 | 16 | 32 |
| 08 | SmolLM2 semantic | 80 | 30 | 32 |
| 09 | SmolLM2 surface | 72 | 0 | 32 |
| 10 | GPT-4.1 mini API | 68 | 29 | 29 |

APIとOSSはプロンプト文字列を共有しますが、APIのメッセージ包装・出力上限32とOSSのraw completion・上限16は異なります。
今回の結果を、同一推論条件の性能比較やfamily外への因果プロファイル転移とは解釈しません。

## 次の一手

次版はモデル数を増やす前に、変更を2点に絞ります。

1. **回答内容と形式適合を別の観測チャンネルへ。** 裸のA/BとFINAL形式の扱いを事前に固定し、曖昧な`FINAL: AB`などは引き続き未解決にします。raw textも残します。
2. **一意ラベルより整合する参照集合。** 同じ弱観測に複数のchallenge挙動が対応する場合は、その集合・差の範囲を報告します。今回の16/32〜32/32は有限参照の範囲であり、確率の信頼区間ではありません。

現在のAPIデータは開発済みデータとして扱います。次の実測では新しい内容・seedを使い、
規則を先に保存してから再度challengeを開きます。現在の棄権結果を成功に再分類しません。
宣言した112回を超える追加API呼出し、再学習、因果測定は今回実施していません。

## 公開データと再計算

このPRは研究チェックポイントであり、v2改善とは分離しています。内部機構の同定成功は主張しません。
公開する観測データは、全1,120回答の合成prompt / raw outputと識別用IDに限ります。端末パス、API response ID、
資格情報、内部テンソル、生成token ID等は含めません。完全な実行証拠はローカルに保全し、
公開版はそのallowlist射影として別manifestに記録しました。元のレシートを改変・再発行したものではありません。
exporterは、このレビュー済みcheckpointの保全元ハッシュに固定しています。
未レビューの変更は書き出す前に拒否します。将来のrunに使える汎用sanitizerではなく、新しいrunには別の公開レビューが必要です。

Python 3.12で、資格情報・モデル・ネットワークなしに主結果と事後診断を再計算できます。

```sh
python3 -S reports/output_only_bridge_20261023/replay.py
python3 -S -m unittest discover -s reports/output_only_bridge_20261023 -v
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/output_only_bridge_v1 -v
```

- [公開manifestと元証拠のハッシュ](data/manifest.json)
- [課題・個体inventory](data/inventory.json)
- [全合成入出力](data/observations.jsonl)
- [事前保存した棄権](data/forecast_lock.json)
- [一次評価](data/analysis.json)
- [事後の形式診断](data/posthoc_format_diagnostic.json)
- [保全証拠の実行監査サマリー](data/verification.json)
- [公開射影のexporter](export_public.py)
- [実行時のコードと契約のスナップショット](../../successors/oss_reliance_regime_v0/output_only_bridge_v1/README.md)

公開replayが検証するのは公開データのハッシュ・完全性・計算結果であり、元の物理実行の第三者証明ではありません。
実行時コードは改変せず保存しています。live furnaceコマンドには、配布していない保全モデル資産・親runner・
元の実行packageが必要です。このチェックポイント単体から再実行するための配備手順ではありません。
公開やテスト通過は、新たなlive実行の許可ではありません。
