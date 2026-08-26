<script setup lang="ts">
import { computed } from "vue";
import { pillOf, useAppStore, type AiMsg } from "../stores/app";
import ResultTable from "./ResultTable.vue";

const props = defineProps<{ msg: AiMsg }>();
const store = useAppStore();

const pill = computed(() => pillOf(props.msg.status));
const meta = computed(() => {
  const m = props.msg;
  if (m.status === "running") {
    const last = m.steps[m.steps.length - 1];
    return last ? `· ${last.label}…` : "";
  }
  if (m.status === "cached") return "· 已跳过（缓存）";
  const errs = m.steps.filter((s) => s.state === "error").length;
  const dur = m.latencyMs != null ? ` · ${(m.latencyMs / 1000).toFixed(1)}s` : "";
  return `· ${m.steps.length} 步${dur}${errs ? ` · ${errs} 次失败重试` : ""}`;
});

function copyAnswer() {
  if (props.msg.answer) navigator.clipboard?.writeText(props.msg.answer);
}
</script>

<template>
  <div class="ai">
    <div class="striprow">
      <div
        class="strip"
        :style="{ animation: msg.status === 'running' ? 'pulse 1.6s ease-in-out infinite' : 'none' }"
        @click="store.panelId = store.panelId === msg.id ? null : msg.id"
      >
        <span v-if="msg.status === 'running'" class="spinner"></span>
        <span v-else class="dot" :style="{ background: pill.bg, color: pill.c }">{{ pill.i }}</span>
        <span :style="{ color: pill.c }" class="stitle">{{ pill.t }}</span>
        <span class="smeta">{{ meta }}</span>
        <span class="schev" :class="{ open: store.panelId === msg.id }">›</span>
      </div>
      <span v-if="msg.status === 'cached'" class="cachetag">缓存命中 · 零消耗</span>
    </div>

    <div v-if="msg.status === 'blocked'" class="blocked">
      <div class="btitle">回答已被幻觉校验拦截</div>
      <div class="btext">{{ msg.blockedText }}</div>
    </div>

    <div v-if="msg.answer && msg.status !== 'blocked'" class="answer">{{ msg.answer }}</div>

    <ResultTable v-if="msg.columns && msg.columns.length" :msg="msg" />

    <img v-if="msg.chartUrl" class="chart" :src="msg.chartUrl" alt="chart" />
    <div v-else-if="msg.chartError" class="charterr">图表生成失败：{{ msg.chartError }}</div>

    <div v-if="msg.status !== 'running'" class="foot">
      <span v-if="msg.answer" @click="copyAnswer">复制回答</span>
      <span @click="store.ask(msg.q)">重跑</span>
    </div>
  </div>
</template>

<style scoped>
.ai { display: flex; flex-direction: column; gap: 12px; }
.striprow { display: flex; align-items: center; gap: 8px; }
.strip { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--line); background: var(--card); border-radius: 999px; padding: 4px 12px 4px 10px; cursor: pointer; font-size: 12.5px; color: var(--ink2); }
.strip:hover { border-color: var(--ink3); }
.spinner { width: 11px; height: 11px; }
.dot { width: 14px; height: 14px; border-radius: 50%; font-size: 8.5px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.stitle { font-weight: 500; }
.smeta { color: var(--ink3); }
.schev { color: var(--ink3); font-size: 12px; line-height: 1; transition: transform 0.15s; display: inline-block; }
.schev.open { transform: rotate(90deg); }
.cachetag { font-size: 12px; color: var(--acc); background: var(--accbg); border-radius: 999px; padding: 3px 10px; }
.blocked { background: var(--errbg); border: 1px solid var(--err); border-radius: 10px; padding: 11px 14px; }
.btitle { font-size: 13.5px; font-weight: 600; color: var(--err); margin-bottom: 2px; }
.btext { font-size: 13.5px; color: var(--ink2); white-space: pre-wrap; }
.answer { font-size: 15px; color: var(--ink); white-space: pre-wrap; }
.chart { max-width: 100%; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
.charterr { font-size: 12.5px; color: var(--warn); }
.foot { display: flex; gap: 14px; font-size: 12px; color: var(--ink3); }
.foot span { cursor: pointer; }
.foot span:hover { color: var(--ink); }
</style>
