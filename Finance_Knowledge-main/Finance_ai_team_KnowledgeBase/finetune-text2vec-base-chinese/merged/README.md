# 模型权重说明

此目录原本存放微调版 text2vec 嵌入模型（finetune-text2vec-base-chinese/merged），
但 model.safetensors 权重文件（约 2.2GB）为 Git LFS 占位文件且残缺，未随仓库提交。

当前项目实际使用的嵌入模型为本地 **F:/bge-m3**（BAAI bge-m3 金融微调版，1024 维），
配置见 Finance_Knowledge-main/Finance_ai_team_KnowledgeBase/.env 的 EMBEDDING_MODEL。

如需恢复此目录模型：从原 HuggingFace 仓库（finetune-text2vec-base-chinese/merged）重新下载权重并放置于此。
