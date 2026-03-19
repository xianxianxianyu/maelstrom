# P1-08: coverage_matrix 节点

## 依赖
- P1-05（Gap Engine 图定义）

## 目的
实现覆盖矩阵构建节点，从去重后的论文集中提取 task-method-dataset-metric 四维信息，构建覆盖矩阵，识别研究空白区域。

## 执行方法
1. 在 `src/maelstrom/graph/nodes/coverage_matrix.py` 中实现：
   - 从 state.papers 中提取四维信息：
     - task: 论文解决的研究任务
     - method: 使用的方法/模型
     - dataset: 使用的数据集
     - metric: 评估指标
   - 使用 LLM 辅助提取（从 abstract + title 中识别）
   - 构建矩阵：dict 结构，key 为 (task, method, dataset, metric) 组合，value 为论文引用列表
   - 计算覆盖率统计：tasks 数、methods 数、datasets 数、empty_cells_pct
   - 写入 state.coverage_matrix
2. Prompt 设计：给定论文 title + abstract，提取 task/method/dataset/metric
3. 批量处理：对论文分批调用 LLM（避免单次 prompt 过长）

## 验收条件
- 覆盖矩阵包含 task/method/dataset/metric 四维
- 每个非空 cell 关联到具体论文 paper_id
- coverage_matrix_summary 统计正确（tasks/methods/datasets 数量，empty_cells_pct）
- LLM 提取结果结构化（非自由文本）
- 大量论文时分批处理不超时

## Unit Test
- `test_matrix_structure`: 验证矩阵包含四维 key
- `test_matrix_paper_refs`: 验证非空 cell 关联正确的 paper_id
- `test_matrix_summary_stats`: 验证 summary 统计数值正确
- `test_matrix_empty_cells`: 验证 empty_cells_pct 计算正确
- `test_llm_extraction_mock`: mock LLM，验证从 abstract 提取 task/method/dataset/metric
- `test_batch_processing`: 50 篇论文分批处理，验证全部被处理
- `test_matrix_no_papers`: 空论文列表时返回空矩阵
