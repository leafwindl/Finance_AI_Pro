from .deepseek import create_deepseek

# 保持 create_deepseek 别名以兼容旧调用方
get_llm = create_deepseek
