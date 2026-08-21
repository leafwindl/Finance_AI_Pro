<script setup>
</script>

<template>
  <div class="sidebar-brand">
    <div class="brand-icon">
      <el-icon :size="24"><TrendCharts /></el-icon>
    </div>
    <div class="brand-text">
      <h1>东方证券</h1>
      <p>知识库智能体助手</p>
    </div>
  </div>
</template>

<style scoped>
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 22px 20px 20px;
  flex-shrink: 0;
}

.brand-icon {
  display: grid;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  color: #fff;
  border-radius: 12px;
  background: linear-gradient(135deg, #0f6cbd, #3d90d6);
  box-shadow: 0 6px 16px rgba(15, 108, 189, 0.3);
  place-items: center;
}

.brand-text h1 {
  margin: 0;
  color: var(--sidebar-text);
  font-size: 20px;
  font-weight: 750;
  letter-spacing: -0.4px;
  line-height: 1.2;
}

.brand-text p {
  margin: 2px 0 0;
  color: var(--sidebar-text-muted);
  font-size: 12px;
}
</style>
