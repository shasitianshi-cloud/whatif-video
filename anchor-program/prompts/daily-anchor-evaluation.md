# Daily Anchor Evaluation

你会收到 Weekly Scope、6 个 Anchor 候选，以及最近历史。

只评价候选，不新增候选，不定义 What-if，不定义扰动。

对每个候选输出：
- curiosity: 0-5
- recognizability: 0-5
- consequence_depth: 0-5
- visual_potential: 0-5
- non_obviousness: 0-5
- propagation_viability: boolean
- scope_match: boolean
- duplicate_or_rephrase: boolean

评分含义：
- curiosity：看到“围绕这个对象的反事实问题”时，普通观众是否天然想知道后果；
- recognizability：普通观众是否立即知道或容易理解它是什么；
- consequence_depth：改变其一个主要关系/属性后，是否有足够长的现实因果传播空间；
- visual_potential：是否容易形成清晰、有动作或状态变化的视觉场景；
- non_obviousness：后果是否不是一眼就能猜完。

`propagation_viability=false`：对象几乎没有足够现实关系可供后续 Premise Discovery 展开。
`scope_match=false`：对象不属于本周作用域。
`duplicate_or_rephrase=true`：与近期历史中的 Anchor 本质相同或只是明显同义改写。

不要自行计算总分。不要因为成本、熟悉度或最容易解释而偏向最简单候选。

只输出 JSON object：
{
  "evaluations": [
    {
      "anchor": "...",
      "curiosity": 0,
      "recognizability": 0,
      "consequence_depth": 0,
      "visual_potential": 0,
      "non_obviousness": 0,
      "propagation_viability": true,
      "scope_match": true,
      "duplicate_or_rephrase": false
    }
  ]
}
