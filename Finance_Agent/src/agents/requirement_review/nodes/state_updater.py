"""步骤7: 状态更新 — 追加收集信息 + 程序化完整性判断"""
from ..state import RequirementState, merge_collected_info


def append_to_collected_info(state: RequirementState) -> dict:
    collected_info = list(state.get("collected_info", []))
    extracted = state.get("extracted_dimensions", {})
    collected_info.append(extracted)

    # 程序化重新判断完整性
    merged = merge_collected_info(collected_info)
    dimensions = ["background", "objective", "system", "scenario", "acceptance", "priority"]
    is_complete = all(
        merged.get(dim) is not None and str(merged.get(dim)).strip() != ""
        for dim in dimensions
    )

    print(f"[状态更新] 已收集 {len(collected_info)} 轮, is_complete={is_complete}")
    return {"collected_info": collected_info, "is_complete": is_complete}
