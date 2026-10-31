# Answer-mapping probe v1 — 小規模な切り分け実験の設計

[English](README.md) | 日本語

[Mistral実験](../../../reports/mistral_bridge_20261029/README.ja.md)では、誤答12件がすべて
`FAIL → A` の条件に集中しました。この小設計では、判断結果を先に与えても同じ誤りが出るのか、
証拠の比較と回答記号への対応付けを同時に求めたときだけ崩れるのかを調べます。
今回は設計のみです。新たなlive runは行わず、今回の棄権も変更しません。

## 固定するpanel

| 構成 | 要因 | promptの種類 | 2回反復した件数 |
|---|---|---:|---:|
| 本課題 | 2 content × 2 semantic × 2 cue × 2 layout × 3回答形式 | 48 | 96 |
| mapping-only control | 2 content × 2判断結果 × 2対応表 | 8 | 16 |
| 合計 | | 56 | 112 |

- semanticは、candidate codeとrequired codeが等しければPASS、それ以外はFAILです。
- cueのPASS/FAILはsemanticと独立に組み合わせます。
- layoutはコードを通常順に並べる条件と、順序を反転する条件です。規模を抑えるため、
  distractorとattenuationは今回は含めません。
- 本課題は、直接のPASS/FAIL回答、通常の `PASS→A / FAIL→B`、反転した `PASS→B / FAIL→A` の3形式です。
- mapping-only controlではPASS/FAILの判断結果を先に与えます。コード比較もcueも提示せず、
  通常・反転の対応表で記号へ変換することだけを求めます。
- 対応表の行順はPASS、FAILで固定します。行順と記号の事前傾向を切り分ける設計ではないため、
  差が残れば追加の対照が必要になる場合があります。

新しい2種類のcontent codeと、各反復内でハッシュ順に並べた実行順を固定します。
2回の反復では同一のpromptを使用します。公開済みの2つの開発用panelとの完全一致がないことを
テストしますが、参照できない訓練データとの非重複や、分布の独立性は主張しません。
生成器とテンプレートには以前の課題との共通性が残ります。2 contentは検出力を設計した確認試験でも、
独立した複数model familyの評価でもありません。

## 先に決める読み方

主な比較は、**反転条件の誤答率 − 通常条件の誤答率**です。
本課題は各形式32観測、mapping-only controlは各対応表8観測として、別々に算出します。
件数と分母を示し、統計的有意性や機構同定の成功とは扱いません。

補助的に、直接回答と符号化回答の正誤を組にした表、semantic・cue conflict・layout別の内訳、
形式とunresolvedの件数、反復間の回答差を残します。直接回答はPASS/FAILだけのbare形式、または
厳密な `FINAL: PASS` / `FINAL: FAIL` を受け入れます。符号化回答はA/Bだけ、または `FINAL: A` / `FINAL: B` です。
前後の空白以外は補正しません。
unresolvedも予定した分母に含め、誤答として集計します。欠損・重複は実行不備であり、
科学的な棄権や誤答ゼロとして処理しません。

| 観測された結果 | そこから言える範囲 |
|---|---|
| 判断結果を先に与えても、反転条件と通常条件の誤答率に差が出る | 証拠比較を求めなくても、回答対応表に敏感な挙動が残ります |
| 直接回答とmapping-onlyは正しいが、符号化した本課題で誤る | 課題の組合せや文脈に依存する失敗と整合します |
| 本課題の直接回答でも誤る | 誤りはA/Bへの符号化だけには限定されません |
| 差がない、結果が混在する、unresolvedが出る | そのまま報告し、自動で拡張・再調整しません |

複数の結果は併存し得ます。回答指示を変えるとprompt全体が変わり、計算過程も変わる可能性があります。
この対照だけで内部の処理段階を切り出したり、cue回路や校正済みの機構ラベルを同定したりはできません。
仮説は10月29日の結果を見て立てたものです。次に新しいcontentで測定しても、
以前から固定されていた仮説の確認試験とは呼びません。

## 実行前の境界

[design.json](design.json)と[manifest](fixtures/manifest.json)で、リクエスト、採点キー、
生成器の内容を固定します。`live_execution_authorized` は明示的に `false` です。
API clientは含めず、鍵もFurnaceも使用しません。

後日実行する際は、明示的な許可、endpointと料金の確認、通信設定の固定、模擬実行が必要です。
候補は `mistral-large-4`、temperature 0、最大32出力tokens、reasoning effort none、standard tier、
1呼び出し1応答です。最大112生成・0.50米ドルを上限とし、再試行、モデル代替、技術的な失敗後の
継続は行いません。1回あたり入力2,048／出力32 tokensの予約額は実行前に再計算します。
前回の0.32693248米ドルは過去の価格による試算です。OSSの再学習やmodel family追加も範囲外です。

```sh
python3 -S successors/oss_reliance_regime_v0/answer_mapping_probe_v1/design.py verify \
  --out successors/oss_reliance_regime_v0/answer_mapping_probe_v1/fixtures
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/answer_mapping_probe_v1 -v
```

`prepare --out NEW_DIRECTORY` は同じ入力と採点用データを、既存ファイルを上書きせず生成します。
`requests.json` はquery IDとprompt文字列だけを持ち、採点情報は別ファイルです。
ただしquery IDには設計要因が含まれるため、監査用の照合キーに限って使います。
将来のAPI接続で送るのは **prompt_textだけ**です。IDや採点キーは送りません。
この追試の結果にかかわらず、既存のv2参照照合結果は維持します。
