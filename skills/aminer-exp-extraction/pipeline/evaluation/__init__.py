"""板块 7 · 固定最优 wf 评估管线。

只评估当前最优 prod workflow ``prod-wf3-batch-bert-pipeline`` 对
``product_pipeline_pc2_handoff/`` 1325 篇的抽取质量，与 GLM5.2 Silver baseline
（2217 experiments）逐字段比对。不复盘 wf1/wf2/wf3 选型。

冻结入口：本模块 ``config.py`` 是全库唯一指定最优 wf 的位置。
"""
