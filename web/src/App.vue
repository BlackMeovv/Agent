<script setup lang="ts">
import { onMounted } from "vue";
import ChatMain from "./components/ChatMain.vue";
import InspectorPanel from "./components/InspectorPanel.vue";
import SideBar from "./components/SideBar.vue";
import { useAppStore } from "./stores/app";

const store = useAppStore();
onMounted(() => {
  store.init();
  // ?theme=dark|light 与 ?q=…&chart=1：分享链接 / 录 demo 用
  const params = new URLSearchParams(location.search);
  const theme = params.get("theme");
  if (theme === "dark" || theme === "light") {
    store.theme = theme;
    document.body.dataset.theme = theme;
  }
  const q = params.get("q");
  if (q) {
    if (params.get("chart") === "1") store.chartOn = true;
    store.ask(q);
  }
});
</script>

<template>
  <div class="layout">
    <SideBar />
    <ChatMain />
    <InspectorPanel v-if="store.panelMsg" :msg="store.panelMsg" />
  </div>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  background: var(--paper);
  color: var(--ink);
  overflow: hidden;
}
</style>
