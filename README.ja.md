# Latent Trace Tomography

[English](README.md) | 日本語 · [ドキュメント](docs/README.ja.md)

ブラックボックスの言語モデルを対象に、出力だけから挙動として識別できる計算様式を調べる、
output-only system identificationの研究プロジェクトです。

「モデルの隠れた推論を復元できるか」よりも、範囲を絞った問いを扱います。

> 制御したprompt/outputの観測群から、OSSで較正したselected-site intervention-susceptibility profileを、
> 未知のlearned-weight dependency clusterに属するモデルでも推定できるでしょうか。
> そして、推定できない場合に棄権できるでしょうか。

プロジェクト名は長期的な目標を表しています。最初に目指す論文規模の主張は、
操作的に定義したOSS reference profileのoutput-only推定と、未知のchallenge挙動の事前予測です。

## 基本的な考え方

~~~mermaid
flowchart LR
    A["OSSへの制御された介入"] --> B["較正用phantom"]
    B --> C["制御したprompt orbit"]
    C --> D["テキスト出力のみ"]
    D --> E["Regime estimator"]
    E --> F["推定または棄権"]
    F --> G["Held-out failureの予測"]
~~~

内部を観測できるモデルで、選んだ介入点への感受性と、外から見える摂動応答を対応づけます。
closed APIは、その較正済みの応答と比較します。得たいのは、適用範囲の確認と棄権を伴う
observational equivalence classです。較正済み確率、activation trace、隠れたchain of thoughtの復元ではありません。

CTの類推は研究の直感として使えますが、数学的な対応ではありません。
promptの変更は既知の線形Radon operatorではなく、計算そのものを変える可能性があります。
実際の研究対象は、制御した入力の集合に対するcausal response surfaceです。

## 現在あるもの

- [2026-10-29のMistral checkpoint](reports/mistral_bridge_20261029/README.ja.md)。
  参照1,008回答、API 112回答と、公開データのoffline replayを含みます。
  弱観測はすべて解釈できましたが、参照の回答列と一致せず、v2の一次結果は棄権でした。
  事後分析の正答一致はweak 70/80件、challenge 30/32件です。誤答12件はすべて反転した `FAIL → A` 条件でした。
  これは挙動の診断であり、内部機構のattributionではありません。
- モデルを呼ばない[answer-mapping probeの小設計](successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md)。
  本課題96件とmapping-only control 16件で、直接回答と通常・反転の回答対応表を比較します。
  リクエスト、採点キー、記述的な比較を固定していますが、live実行は未許可です。
  内部機構の復元を前提にせず、実用上のAPI interface設計も調べる構成です。
- 追加実装の[output-only bridge v2](successors/oss_reliance_regime_v0/output_only_bridge_v2/README.ja.md)。
  回答内容と形式適合を分け、caseごとに一致した全referenceと有限のchallenge-output集合を返します。
  module自体はモデルを呼ばず、開発用という保守的なラベルを維持しています。
  上記の小規模なMistral runに使っても、v1 checkpointの変更やprospective transferの成功を意味しません。
- [2026-10-23のoutput-only Furnace/API checkpoint](reports/output_only_bridge_20261023/README.ja.md)。
  保全したOSSモデルの1,008回答、112回のAPI呼び出し、公開した合成prompt/outputとoffline replayを含みます。
  主結果は予測の棄権です。別途行った事後の形式診断は、転移成功の証拠ではありません。
  ３つのOSS個体は弱観測の全文が一致しながら、challengeでは異なる挙動を示しました。
  これは範囲を限定したsuccessor pilotであり、凍結済みOSS-1の収集や内部機構の検証済みattributionではありません。
- semantic evidenceと相関したsurface cueという、既知の２つのhard routeを持つ合成較正器。
  実行に必要なのはPython標準ライブラリだけです。
- baselineの出力を揃えた観測、診断用projection、推定時には伏せるchallenge projection。
- logits、logprobs、latency、usage、モデル名、provider metadataを除外したtext-only feature path。
- single-projection、label-permutation、reduced-orbitによる非識別性の対照。
- 未観測のcue-flip / semantic-flip challengeに対する出力の事前予測。
- 上書きせず、原子的に公開するrun directory。ソース、protocol、設定、split、prediction lock、phase orderのハッシュを保存します。
- prediction artifactを書き出してハッシュを確定するまで開かないevaluation keyとchallenge-output phase。
- exact task generator、intervention table、dependency-cluster split、独立単位、blind evaluation interface、
  prospective challenge scoringを固定したOSS-1 contract。
- ３foldすべてのprediction commitmentが揃うまでrevealを認めないproduction coordinator。
  foldの由来と相互整合性を検証し、各clusterを等しく重みづけしたprospective gateを適用します。
  単一foldのscorerだけでは最終判定できません。
- 出力前に別々に確定するdiscovery authorizationとfinal execution lock、出力後に作る非公開の
  sealed-evaluation authorization。そのテンプレートは未割当のままです。
  別系統のlive successorは実行済みですが、その結果でテンプレートを埋めたり、過去の実行を遡って許可したりしません。
  `design_ready=true`はlive実行の準備完了を意味しません。
- 追記型の[controlled-anchor construction plan](successors/oss_reliance_regime_v0/controlled_anchor_phantom_v1/anchor_construction_plan.json)と
  [registry-authoring companion](operations/oss1_registry_authoring_v2/docs/registry_authoring_successor.md)。
  公開checkpointの９候補は`unresolved`のままです。successorでは各base familyに３つの制御された派生個体を割り当て、
  保全したcohortを今回の別試験に使いました。９派生個体を独立な９被験体とは数えません。
  構築条件名も検証済みの機構ラベルではなく、causal calibrationの接続は未解決です。

合成panelは計測器のregression testです。特徴量にはparseした最終判断だけを使い、
challenge generatorも観測generatorと同じhard-routeの意味論を共有しています。
検証できるのはleakage、phase、棄権、予測処理の接続です。
自然言語の残差から機構が読めることや、自然なモデルに同じrouteがあることの証拠ではありません。

## Quick start

~~~bash
git clone https://github.com/RyoSpiralArchitect/latent_trace_tomography.git
cd latent_trace_tomography

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

ltt preflight \
  --protocol protocols/oss_reliance_regime_v0/protocol.json

ltt oss-design-summary

ltt synthetic-demo \
  --out-dir artifacts/synthetic_projection_orbit_v1_seed7 \
  --seed 7
~~~

２つのOSSコマンドはモデルやAPIを呼び出しません。preflightは凍結ファイルのハッシュと実行可能な不変条件を検証し、
summaryは公開64-seed generatorの適合性ハッシュを再現します。どちらもモデル実行の手前で止まります。
live successorには、環境、検証済みの実体、RNG、module、tokenization、出力先の前提を満たす、
別のハッシュ付きauthorizationが必要です。
construction、registryの証拠確認、discovery authorization、final execution lockは別々のgateです。
リポジトリの公開やpreflightの通過だけでは、weight download、学習、モデル/API呼び出しを許可しません。

runnerは出力先ごとのlockを使い、既存のパスを拒否します。隣接するstaging directoryへ書き出し、
manifestの整合性を確認してから原子的に公開します。SHA-256 manifestは事後の改変を検出しますが、
OSがディレクトリを暗号学的に変更不能にするわけではありません。

reference seedでの結果は次のとおりです。

| Readout | Value |
|---|---:|
| Full projection-panel accuracy | 1.000 |
| Single baseline-projection accuracy | 0.500 |
| Label-permutation mean accuracy | 0.375 |
| Reduced matched-output orbit coverage | 0.000 |
| Held-out challenge prediction accuracy | 0.971 |

これらは合成bootstrapの結果で、事前登録ではなくretrospectiveと明記しています。

較正対象は12個体だけです。64-shuffle label nullの経験的な裾確率は0.108、最大accuracyは1.0でした。
したがって`R4`は、あらかじめ指定した平均差に対するpipeline regressionであって、有意性の主張ではありません。
自然なモデルの研究には、独立したdependency clusterと、検出力を考慮したnullが必要です。

## Scientific contract

主たる独立単位は`dependency_cluster_id`です。共有する学習済みweight、teacher/distillationの由来、
weight mergeを結ぶgraphから定義します。checkpoint、adapter、fine-tune、decoding run、prompt、caseは
その内側に入れ子になった測定であり、有効サンプル数を増やしません。

OSS較正の対象は、次のような連続値のselected-site intervention-susceptibility profileです。

~~~text
S_v = IIA_targeted_v - IIA_matched_null_v
delta_specific = S_semantic - S_surface_cue
~~~

raw targeted IIAとmatched-null IIAも保存します。主結果は連続profileの点推定と区間であり、較正済みposteriorではありません。
anchor labelとAUROCは補助的な要約です。challenge-responseの確率は別途凍結するprospective targetで、
codebookに対する`semantic_consistent`、`surface_cue_consistent`、`parse_failure`を扱います。
prospective pass metricはcluster-macro log lossだけです。

causal profileの各成分は実測countと対応づけ、`matched_null_kind=norm_matched_rotation`を明記します。
count付きself-shamとcontrol-siteの証拠を実行可能なgate reportへ渡し、凍結した閾値を適用します。
routeは0.25、self-shamは0.90、control-siteの絶対値は0.10、codebookは0.90、site stabilityは0.75です。
失敗した証拠も保存し、anchor summaryを`unresolved`にします。記録から除外しません。

OSS-1のexact taskは、content seedごとにsemantic decision、surface cue、answer codebookの2 × 2 × 2完全要因計画です。
弱観測はsemanticとcueが一致するcellと、判断を決定づけない変形に限ります。
cue maskingはprediction commitment後の診断です。衝突条件の両challenge rendererとrelational scoring keyは、
対応するevaluation phaseまで伏せます。

最上位の凍結対象は、[task generator specification](protocols/oss_reliance_regime_v0/task_generator_spec.json)、
[intervention table](protocols/oss_reliance_regime_v0/intervention_table.json)、
[dependency-cluster split rule](protocols/oss_reliance_regime_v0/family_split_rule.json)、
[independent-unit definition](protocols/oss_reliance_regime_v0/independent_unit_definition.json)、
[blind evaluation contract](protocols/oss_reliance_regime_v0/blind_evaluation_contract.json)の５つです。
最後の契約は、exactな[prospective scoring contract](protocols/oss_reliance_regime_v0/prospective_scoring_contract.json)を含みます。

pilot registryは厳密に９model unitです。３つのlearned-weight dependency clusterそれぞれに、
`semantic_anchor`、`surface_cue_anchor`、`mixed_anchor`を１つずつ置きます。
同一cluster内の３anchorはarchitecture familyとtokenizer identityを共有します。
全clusterにanchorの完全な組があるため、architecture、tokenizer、cluster identityだけではanchorを特定できません。
有効な`n`は９ではなく３です。

各foldのprospective closureには、正規化した６つの入力があります。
弱観測のrecordとinventory、development scoring keyとslot inventory、held-out scoring keyとslot inventoryです。
production coordinatorは３つの隔離されたfold commitmentが揃うまでrevealしません。
各foldのdevelopmentデータが他２foldのheld-outデータに対応することを、cluster IDを受け手の非公開HMAC namespaceに
変換して確認し、２つの凍結baselineを内部で再構成します。candidate codeはbaselineのvectorやscoreを渡せません。
candidate lossと各baseline lossを３つのheld-out dependency clusterで等重みに平均した後、
lossの小さいbaselineを選び、凍結した10 percent gateを適用します。

実行は２段階です。最初のdiscovery authorizationで、９unitのregistry、dependency graph、tokenizer check、
live-seed commitment、candidate-site inventory、algorithm、環境、discovery budgetを固定します。
得られたsite-discovery reportはcountと証拠の整合性を確認してハッシュを確定します。
その後、別のfinal lockで両artifactを結び、残るcausal-label、behavior-fit、sealed-test、diagnosticを許可します。
このlockは出力に依存しません。`authority_commitments`は`null`とし、出力から作ったscoring keyや
challenge commitmentを入れてはいけません。checked-inのdiscovery、final execution、private sealed evaluationの
３テンプレートはすべて未割当です。最後のものはsealed outputが存在してから作成します。

authorizationは非公開64-seedの`8/16/24/16` partitionを再生成し、任意に渡されたgraphを信用するのではなく、
ハッシュで固定したlearned-state ancestryからdependency edgeを導きます。
discoveryは全transformer-block candidateと全primary pairを対象にします。
causal profileはraw output、carrier binding、条件ごとのhook ledgerから再計算します。
固定したdiscovery後の全計画は16,992 forwardsです。
pre-auditor barrierは、再生成したprompt/raw-output inventoryと自己ハッシュ付きledgerのみを受け付けます。
内訳はcausal-label 8,064、behavior-fit 4,320、sealed-test 4,032、合計16,416 forwardsです。
この時点のdiagnostic forwardは０で、未実行のままにします。
これは宣言したauthority下でのinventoryと派生結果の整合性を確認するもので、各回答のlocked-model provenanceや
物理実行の証明ではありません。

4,032件の`D_sealed_test`出力がすべて揃ってから、evaluatorがfoldごとの非公開sealed authorizationを作成します。
各authorizationは、９対象全体のraw weak 2,880件とchallenge 1,152件、その出力から導いたkeyと匿名化したauditor surface、
そして１つのfold workerを結びます。raw model ID、dependency-cluster ID、private authorizationはworker側へ渡しません。
development scoring fileのdependency-cluster IDはHMAC由来の仮名です。
異なる３capability IDと、mount/cache/IPCを共有しない宣言を要求しますが、これはauthorityによる宣言であって
物理的な隔離の証明ではありません。fold内のestimator trainingとreplayは残るP1です。
別途証明しない限り、prediction-lockedとは呼べてもcertified blindとは呼べません。

`estimator_source`、`feature_spec`、`analysis_config`、`abstention_rule`のハッシュは全foldで同一にします。
学習済みestimator weightとfoldごとのcalibration statusは異なって構いません。
productionの`fold_runs`にはreveal bytesやnonceを入れません。
全commitment、bundle、prediction、redaction、common-rootの検証後にのみ、厳密な４fieldのauthority opening providerを呼び、
返されたbytesを別途再導出して検証します。cue-mask診断も３prediction commitmentが揃った後です。
これらのハッシュは宣言したauthority下での証拠の整合性を支えますが、物理runtimeの証明ではありません。

detectorが使うのは観測集合です。明示的なcue conflictとheld-out mismatch-table renderingは特徴量に含めません。
OSS studyのcue maskingも、一次の弱観測ではなくprediction commitment後の診断です。

成功には、推定したprofileがsealed relational outcome distributionを予測する必要があります。
決定的なcue介入を見てからrouteを判別するだけなら、behavioral stress testingであってtomographyではありません。

live backendを追加する前に、[research contract](docs/research_contract.md)、[architecture](docs/architecture.md)、
[凍結済みOSS protocol](protocols/oss_reliance_regime_v0/protocol.json)を確認してください。

## 主張の範囲

対応する証拠が揃った場合に使える表現です。現時点での達成を一括して宣言するものではありません。

- 「出力は、calibration Cのもとでregime class Rと挙動上整合します」
- 「estimatorはheld-out perturbationでfailure pattern Fを予測します」
- 「probe set Qのもとでは、この２regimeを識別できません」

次のようには主張しません。

- 「モデルの真のhidden traceやchain of thoughtを復元しました」
- 「proprietary modelが特定のlayer、head、circuitを使っています」
- 操作的定義からその言葉への接続を別途検証せずに、「モデルが検証した、記憶した、信じた、合理化した」と述べること。
- forward operatorが既知かつ単射であるかのように「tomographic reconstruction」と呼ぶこと。

## Roadmap

1. Phantom-0：schema、leakage対照、null、棄権を検証します。
2. OSS-1：controlled-anchor constructionの前提を確認・許可し、全予定結果を保全してregistryとsource evidenceを検証します。
   その後、別のdiscovery authorizationを割り当て、範囲を限定したsite discoveryと証拠の確認を行います。
   残りの測定はfinal execution lockを確定してから実行します。
3. Transfer-1：learned-weight dependency cluster全体をheld-outにします。checkpointとtask caseは入れ子の測定のままです。
4. Prospective-1：capabilityを分離した３fold workerを使い、全prediction commitment後にrevealします。
   等cluster重みのglobal gateを採点し、その後にだけ診断を公開します。
5. API-1：consistency class、不確実性、driftを報告します。未検証の内部の真実は主張せず、確率較正は別gateに残します。

詳細は[roadmap](docs/roadmap.md)と[industrial thesis](docs/industrial_thesis.md)を参照してください。
[以前のbridge pilot作戦](docs/next_bridge_pilot.ja.md)は、当時の提案として残しています。
現在の次の一手は[answer-mapping probe](successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.ja.md)です。
どちらの文書も実行許可ではありません。

## 範囲と倫理

これはモデル監査とsystem identificationのプロジェクトです。アクセス制御の回避、weightや秘密の抽出、
rate limitの迂回、非公開chain of thoughtへのアクセスは目的にしていません。
live adapterは公開されたAPIを使い、providerの条件と予算を守り、資格情報を環境変数などのsecret storeで管理します。
provider/version metadataは監査上のprovenanceにのみ使い、primary mechanism estimatorへ渡しません。

live作業では[RESPONSIBLE_USE.ja.md](RESPONSIBLE_USE.ja.md)に従い、対象への許可、保存期間、redaction、
重大な判断での人によるレビューを確認してください。

## 開発

~~~bash
make test
make smoke
~~~

core packageの実行時依存はPython 3.10以降の標準ライブラリだけです。
10月23日の保存済みreplayにはPython 3.12が必要です。
10月29日のreplayとanswer-mapping設計はPython 3.10以降に対応しています。
証拠とamendmentのルールは[CONTRIBUTING.ja.md](CONTRIBUTING.ja.md)を参照してください。

## 関連研究

black-box perturbation auditing、model fingerprinting、hidden-behavior audit、causal-variable benchmark、
identifiability limitはいずれも既存の研究分野です。目指す貢献は、次の組み合わせにあります。

> OSSで較正したselected-site intervention-susceptibility equivalence classをoutput-onlyで推定し、
> leave-dependency-cluster-out transferとprospective failure predictionで評価します。
> 棄権も明示して記録します。open-set validationと確率較正はsuccessor側のgateであり、現在のOSS-1の主張ではありません。

関連研究との境界と修正済みの参考文献は[docs/prior_art.md](docs/prior_art.md)にまとめています。

## ライセンス

[GNU Affero General Public License, version 3 only](LICENSE)（`AGPL-3.0-only`）です。
「version 3 or any later version」ではありません。

このrevisionのプロジェクトコードと文書に適用します。過去commitには、その時点のlicense noticeが残ります。
第三者のモデル、データセット、参照した著作物は、それぞれのライセンスに従います。
記録したupstream licenseを、このリポジトリのライセンスで変更するものではありません。
