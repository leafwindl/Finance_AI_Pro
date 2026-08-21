<script setup>
import SidebarBrand from './SidebarBrand.vue'
import SidebarAgentList from './SidebarAgentList.vue'
import SidebarUser from './SidebarUser.vue'
</script>

<template>
  <aside class="sidebar">
    <SidebarBrand />
    <SidebarAgentList />
    <SidebarUser />
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: 280px;
  flex-shrink: 0;
  height: 100vh;
  background: var(--sidebar-bg);
  color: var(--sidebar-text);
  border-right: 1px solid var(--sidebar-border);
  user-select: none;
  overflow: hidden;
}

.sidebar > :nth-child(2) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
