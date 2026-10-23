# 次のbridge pilot：複雑にする前に、有用性を測ります

[English](next_bridge_pilot.md) | 日本語

2026-10-23のcheckpointを受けた提案です。**凍結済みprotocolでもlive実行の許可でもありません。**
この文書を追加しても、推論、学習、因果測定は始まりません。

## 今回の結果から変わった問い

v1はAPIのchallenge 32件すべてで棄権しました。事後診断では形式差が見つかり、
弱観測では区別できない３referenceが、challengeでは異なる挙動を示しました。
v2はcontentとformatを分け、３referenceすべてを残します。
すでに開示した開発データでは、challenge 32 slot中18 slotにreference間の曖昧さが残ります。

したがって次の問いは、「内部機構を復元できたか」ではありません。

> 新しいcontentでも、対象のchallenge outputを見る前に弱観測の回答を照合することで、
> 限界を明示しつつ有用なreference集合を得られるでしょうか。

## 小さな実装PRを１本、その後に別途許可したlive pilot

1. **Offlineのprospective coordinatorを作ります。** v2のparserとexact-match ruleは変更せずに再利用します。
   規則、実装、具体的なinventory、referenceの証拠、対象の弱観測、reference reportを、上書きしないcommitment artifactに保存します。
   対象のchallengeは、そのcommitment後に別のevaluatorだけが受け取ります。
   既存のv2 reportはdevelopment-onlyのままにし、prospective evidenceの段階は、別versionのcoordinator receiptで扱います。
   開発用reportのラベルを貼り替えて済ませません。
2. **Fixtureで全順序を模擬実行します。** 中断、結果不明のrequest、出力先の衝突、古いハッシュ、slot欠落、
   早すぎるchallenge開示をテストします。完了・試行した全requestをbudget ledgerへ結びます。
   暗黙retry、再開による予算の復活、model fallbackは認めません。
3. **新しいrun manifestをレビューします。** 新しいcontent/seedを使い、endpointとruntimeを固定し、
   保全モデルの利用可能性、料金、capabilityを再確認します。模擬実行が通ってからlive authorizationを得ます。
4. **一度実行し、lock、reveal、scoreの順に進めます。** 保全した９OSS referenceと、予定した全API結果を残します。
   未解決のtext、除外、error、棄権も含めます。停止・不完全終了したrunを隠したり、黙って差し替えたりしません。

このpilotには、新モデル、再学習、site search、広いweak-probe探索を混ぜません。
何が結果の変化につながったのかを切り分けるためです。

## 提案する規模と予算

規模は前回と同じ小さな要因計画を提案します。新しいcontentを２つ使い、
弱観測は８aligned case × ５projection × ２反復でAPI 80回、
challengeは８conflict case × ２renderer × ２反復でAPI 32回です。
合計はAPI 112回、９referenceでOSS 1,008回答になります。

前回のdecoding上限を維持するなら、OSSの上限案は16,128 physical forwards / 600秒です。
APIの金額上限案は引き続き$0.50ですが、authorization前に料金とrequest上限を確認し、予約額を再計算します。
前回の$0.372736を現在の料金見積りとして流用しません。
新しい予約額が上限を超える場合は実行前に止めます。
APIとOSSのruntime差もレポートに残し、同一推論条件での比較とは示しません。

新しいcontentは、保全したtraining/development promptと完全一致しないことを確認します。
ただし、それだけで分布の独立性が成立するわけではありません。
２反復から信頼できる出力分布を推定することはできず、９派生個体も独立な９サンプルにはなりません。

## 結果を見る前に固定するreadout

今回は記述的なcountを報告するengineering pilotに留め、有意性は主張しません。
新しい出力を得る前に、定義と具体的なevaluatorのbytesを固定します。最小限のreadoutは次のとおりです。

| Readout | 解釈上の条件 |
|---|---|
| Content resolutionとformat compliance | 分母を分け、裸のA/Bを形式適合の成功に数えません |
| Reference support | 全個体と除外理由を残します。宣言したlineage数は独立性の証明ではありません |
| Set availability | 空でないreference集合のslot数 / 全予定challenge slot数です。正しく予測した割合とは異なります |
| Set containment | `unresolved`も含む対象のcanonical answerが、commit済み集合に含まれるかをcountと分母で報告します |
| Set sizeとsingleton performance | `{A, B, unresolved}`なら全結果を含められますが、情報はありません。外れと未解決singletonも残します |
| Unconditional reference baseline | ９referenceすべてから同じslotごとの集合を作り、containmentと集合サイズを比較します。reveal後にbaselineを選びません |

単一の解決済み回答を予測した件数 / 全予定slot数と、その部分集合での正答率を報告します。
`unresolved`だけのsingletonを解決済み回答に数えません。
challenge classと反復ごとのcontent/format failureも示します。
referenceの頻度を較正済み確率や区間に読み替えないでください。

slot欠落やcommitment chainの破損は、prospective scoringの不完全終了です。
科学上の棄権とは区別します。一方、空のsupportや対象の弱観測で未解決のcontentがある場合は、
宣言した規則に従って棄権します。部分的な記述結果を出す場合も、実際の分母を示し、
予定したpilot全体が完了したようには扱いません。

## 結果に応じた次の判断

- 形式の問題が解けても集合が広いままなら、それを有用な限界の結果として残します。
  OSSのdevelopmentデータで識別力の高いweak projectionを開発し、別successorを固定して新しい対象データで試します。
  今回の対象challengeで調整したものを、そのまま同じchallengeで検証しません。
- conditionalな集合がunconditional baselineより狭くなり、観測したcontainmentも維持できた場合は、
  新しい独立なheld-out資料で反復してから、安定した予測価値を主張します。１回のpilotでは一般的なtransferを立証できません。
- 回答が集合の外に出たら、失敗として報告します。reveal後にsupportを広げたり、受理する形式を増やしたりして、
  一次評価の成功とは呼びません。
- supportが空なら、domain mismatchをofflineで調べます。自動で追加callを買ったり、exact-matchの閾値を下げたりしません。

## Mech int側は別の検証として進めます

選択したsemantic carrierでtargeted/nullがともに０だった点は、calibrationの不足として残っています。
APIの観測へ`semantic reliance`を付与する前に、範囲を独立に定めたcarrier/intervention診断で、
使えるcausal referenceを確立する必要があります。構築条件名だけでは、そのラベルを与えられません。
この検証とbehavior pilotは別です。一方の改善を、もう一方の実証とは扱いません。

実用上はbehavior drift、failure-surface prediction、OSS-calibrated attributionの順に進み、
attributionには固有の証拠を要求します。現在のリポジトリは研究用の計測器で、production monitoringの保証ではありません。
