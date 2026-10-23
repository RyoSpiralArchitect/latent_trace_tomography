# 炉とAPIの初回 output-only bridge — 2026-10-23

実測は完走。**主結果は予測を棄権（coverage 0/32）**であり、API内部の機構推定や、予測転移の成功ではない。
ただし次に直す場所を、形式適合と観測の識別力に分けて特定できた。

## 実行と監査

| 対象 | 実行数 | 所要時間 | 補足 |
|---|---:|---:|---|
| 炉・9個体 / 3モデル家系 | 1,008回答 | 129.8秒 | 6,050 physical forwards |
| API・弱観測 | 80 calls | 167.7秒 | challenge閲覧前に完了 |
| API・challenge | 32 calls | 63.9秒 | 凍結した棄権を維持 |

APIは `gpt-4.1-mini-2025-04-14`。今回の目的は最新モデルの能力競争ではなく、
出力のみの観測器を実際のAPIへ接続する小規模試験だった。
合計入力12,356 / 出力418 tokens、標準・キャッシュ割引なしの料金換算は **$0.0056112**。
請求書の実額ではない。事前予約見積りは$0.372736、宣言上限$0.50。
単価は[公式料金表](https://developers.openai.com/api/docs/pricing)、
モデル選択は[公式モデルページ](https://developers.openai.com/api/docs/models/gpt-4.1-mini)を実行前に確認した。

新規の56種類の合成プロンプトを各2回使用。学習プロンプト12,288件との完全一致は0件。
これは内容分布やテンプレートの独立性を意味しない。9個体を独立9サンプルとは数えない。
炉は既存GPUジョブと共存しており、所要時間をモデル間性能比較には使わない。

全件で暗黙再試行・モデル置換なし。APIのlogprobsは要求せず、秘密値はローカル環境変数からメモリ内のみで使用。
キーを炉に送っていない。APIには合成プロンプトだけを送った。`store=false`はゼロ保持保証とは異なる。
実行前の模擬テスト19件はMacと炉で通過。解析・事後診断を含む最終27件もMacで通過した。

レシート、全回答のハッシュ、APIリクエストの予約記録、イベントチェーン、forward数、
予測の再計算を照合済み。自己記録の整合性監査であり、第三者による実行証明ではない。
ローカル時計で以下の順序も確認した。

1. 弱観測完了: `2026-10-23T01:15:13.238636+00:00`
2. 予測／棄権保存: `2026-10-23T01:15:26.518438+00:00`
3. challenge開始: `2026-10-23T01:15:43.417940+00:00`

## 1. 形式違反が「参照外」に混ざった

凍結済みのparserは `FINAL: A` / `FINAL: B` を受理する。
APIは弱観測の12/80件、challengeの3/32件で `A` または `B` だけを返した。
したがって一次評価は弱観測68/80、challenge29/32がparse可能。
parse可能な回答はすべて課題のsemantic ruleと一致した。

APIの51次元特徴量に完全一致するOSS参照はなく、事前固定規則により棄権した。
これは「APIの内部計算が未知と判定できた」という意味ではない。
この特徴量は形式適合性と回答選択を混ぜており、少なくとも形式差が参照不一致を生んでいた。
同一プロンプトの2反復は、APIで56組中45組が全文一致。temperature 0でも今回の出力は完全一致しなかった。

別ファイルの**事後診断だけ**で裸のA/Bも同じ回答記号として読んだところ、
弱観測80/80、challenge32/32がsemantic ruleと一致し、弱観測特徴量は下記3参照と一致した。
元の回答、parser、特徴量、棄権、予測スコアは一切差し替えていない。
この診断を「事前に予測成功」と読み替えてはいけない。

## 2. 形式を直しても、弱観測の曖昧さは残る

以下の3個体は、弱観測80回答が**特徴量だけでなく全文一致**した。
しかし、challengeでsemantic ruleに一致した数は異なった。

| 参照個体（構築条件名） | 弱観測のsemantic一致 | challengeのsemantic一致 |
|---|---:|---:|
| GPT-2 / mixed | 80/80 | 16/32 |
| GPT-2 / semantic | 80/80 | 32/32 |
| SmolLM2 / semantic | 80/80 | 30/32 |

構築条件名は内部機構のground truthではない。
これは「有限の今回の弱観測では区別できなかった」という実測であって、
すべての入力・出力分布についての識別不能性定理ではない。
それでも、この観測パネルから1個の内部機構ラベルや一意の将来挙動を割り当てることは支持されない。

具体例 `challenge:0:2:challenge_conflict:r0`:

```text
required_code == candidate_code   → 課題の法則では PASS
advisory ribbon = FAIL            → cueとは衝突
response map: PASS → A, FAIL → B

GPT-2 / mixed:     \nFINAL: B
GPT-2 / semantic:  \nFINAL: A
SmolLM2 / semantic:\nFINAL: A
```

この差は**出力で観測した差**。既存のsemantic介入点の盲点が解消した証拠ではない。

## 全個体を残した一次評価

分母には形式失敗を含む。semantic一致は課題の法則への一致であり、内部のsemantic reliance推定ではない。

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

APIとOSSはプロンプト文字列を共有するが、APIのメッセージ包装・出力上限32とOSSのraw completion・上限16は異なる。
今回の結果を、同一推論条件の性能比較やfamily外への因果プロファイル転移と解釈しない。

## 次の一手

次版はモデル数を増やす前に、変更を2点に絞る。

1. **回答内容と形式適合を別の観測チャンネルへ。** 裸のA/BとFINAL形式の扱いを事前に固定し、曖昧な`FINAL: AB`などは引き続き未解決にする。raw textも残す。
2. **一意ラベルより整合する参照集合。** 同じ弱観測に複数のchallenge挙動が対応する場合は、その集合・差の範囲を報告する。今回の16/32〜32/32は有限参照の範囲であり、確率の信頼区間ではない。

現在のAPIデータは開発済みデータとして扱う。次の実測では新しい内容・seedを使用し、
規則を先に保存してから再度challengeを開く。現在の棄権結果を成功に再分類しない。
宣言した112回を超える追加API呼出し、再学習、因果測定は今回実施していない。

## 公開データと再計算

このPRは研究チェックポイントであり、v2改善とは分離している。内部機構の同定成功を主張しない。
公開データは全1,120回答の合成prompt / raw outputと識別用IDに限る。端末パス、API response ID、
資格情報、内部テンソル、生成token ID等は含めない。完全な実行証拠はローカルに保全し、
公開版はそのallowlist射影として別manifestに記録した。元のレシートを改変・再発行したものではない。

Python 3.12で、資格情報・モデル・ネットワークなしに主結果と事後診断を再計算できる。

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

公開replayが検証するのは公開データのハッシュ・完全性・計算結果であり、元の物理実行の第三者証明ではない。
実行時コードは改変せず保存した。live furnaceコマンドは配布しない保全モデル資産・親runner・
元の実行packageを必要とし、このチェックポイント単体から再実行するための配備手順ではない。
公開やテスト通過は新たなlive実行の許可ではない。
