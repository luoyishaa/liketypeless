# 人工审阅规则

先用 `make_review_sheet.py` 生成待评 CSV。两名不同的真人审阅者各自听原音频/看原文后，独立填写一份；不要参考对方分数，也不要让被测模型给自己打分。只填写适用于该样本的列：纯 ASR 样本填 ASR 忠实度，整理样本填五个 yes/no，中英翻译样本填两项 1–5 分。未审阅的样本不计为已审阅。

- `asr_faithfulness_1_to_5`：5 为关键内容准确、仅标点细节不同；3 为部分词错但主旨可辨；1 为关键意思错误。CER 是自动量化，不能替代这一判断。
- `meaning_preserved`：否定、时间、数字、姓名、条件、任务、结论、列表顺序或语气有实质变化就填 `no`。
- `deleted_meaningful_content`：任何有意义内容丢失填 `yes`；口头填充词不算。
- `added_information`：出现原文没有的事实、建议、总结、判断填 `yes`。
- `protected_terms_preserved`：任一保护词或其指代实体丢失填 `no`。
- `punctuation_appropriate`：标点帮助阅读且不改变语气/句意填 `yes`。
- `translation_faithfulness_1_to_5`：事实、数量、姓名、条件、否定、语气完整对应为 5；关键事实误译为 1。
- `translation_naturalness_1_to_5`：英语可直接使用为 5；严重不通顺为 1。自然不代表可以增加或删减事实。

两位审阅者在任一 yes/no 上分歧时，需要第三位提交相同 `id`、`reviewer=adjudicator` 的裁决行；`merge_reviews.py` 会拒绝缺裁决、重复 ID、分数越界和单人审阅。1–5 分取两位审阅者均值，并保留原始 CSV 以便复核。

安全红线：有意义内容删除、无根据添加、原意改变或保护词丢失。候选版本自动违规率高于基线，CI 失败；真人审阅中若出现任何严重红线，应暂停发布并逐条复核，不能靠平均分掩盖。
