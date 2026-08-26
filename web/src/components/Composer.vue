<script setup lang="ts">
import { useAppStore } from "../stores/app";

defineProps<{ placeholder: string }>();
const store = useAppStore();

function send() {
  if (store.running) store.stop();
  else store.ask(store.draft);
}
</script>

<template>
  <div class="composer">
    <input
      v-model="store.draft"
      :placeholder="placeholder"
      @keydown.enter.prevent="send"
    />
    <div class="bar">
      <div class="chart" :class="{ on: store.chartOn }" @click="store.chartOn = !store.chartOn">
        <svg class="cic" width="13" height="13" viewBox="0 0 16 16" fill="none">
          <path d="M3 13.5V8M8 13.5V3.5M13 13.5V6.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        </svg>
        生成图表
      </div>
      <span class="hint">{{ store.running ? "流式接收中…" : "重复的问题会命中缓存 · Enter 发送" }}</span>
      <button class="send" :class="{ stop: store.running }" @click="send">
        {{ store.running ? "停止" : "发送" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.composer { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 11px 14px; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03); transition: border-color 0.15s, box-shadow 0.15s; }
.composer:focus-within { border-color: var(--acc); box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05); }
input { width: 100%; border: none; outline: none; background: none; color: var(--ink); font-size: 15px; padding: 3px 2px; }
.bar { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.chart { display: flex; align-items: center; gap: 6px; cursor: pointer; border: 1px solid var(--line); border-radius: 999px; padding: 3px 11px; font-size: 12.5px; color: var(--ink2); user-select: none; }
.chart.on { border-color: var(--acc); color: var(--acc); }
.cic { flex: none; }
.hint { font-size: 12px; color: var(--ink3); }
.send { margin-left: auto; border: none; border-radius: 9px; background: var(--acc); color: #fff; font-size: 13.5px; font-weight: 600; padding: 6px 18px; cursor: pointer; }
.send.stop { background: var(--err); }
</style>
