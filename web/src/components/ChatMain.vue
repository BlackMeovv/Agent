<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useAppStore } from "../stores/app";
import AiMessage from "./AiMessage.vue";
import Composer from "./Composer.vue";

const store = useAppStore();
const scroller = ref<HTMLElement | null>(null);

const SAMPLES = [
  "支付总金额最高的前3个城市是哪几个？",
  "各品类的成交金额分别是多少？",
  "下单次数最多的前5名客户是谁？",
];

const greeting = computed(() => {
  const h = new Date().getHours();
  const part = h < 6 ? "凌晨好" : h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好";
  return `${part}，想看哪块数据？`;
});

watch(
  () => store.msgs.length + store.msgs.reduce((n, m) => n + (m.role === "ai" ? m.steps.length : 0), 0),
  () => nextTick(() => scroller.value?.scrollTo({ top: scroller.value.scrollHeight })),
);
</script>

<template>
  <div class="main">
    <div class="head">
      <div class="title">{{ store.title }}</div>
      <div class="spacer"></div>
      <div v-if="store.env" class="dbpill">
        <span class="okdot"></span>{{ store.env.db }}
      </div>
      <span v-if="store.env?.mock" class="mock">MOCK</span>
    </div>

    <template v-if="store.msgs.length === 0">
      <div class="empty">
        <div class="greet serif">{{ greeting }}</div>
        <div class="cwrap"><Composer placeholder="问一个关于数据的问题…" /></div>
        <div class="samples">
          <div v-for="s in SAMPLES" :key="s" class="sample" @click="store.ask(s)">{{ s }}</div>
        </div>
      </div>
    </template>

    <template v-else>
      <div ref="scroller" class="msgs">
        <div class="col">
          <template v-for="m in store.msgs" :key="m.id">
            <div v-if="m.role === 'user'" class="urow">
              <div class="ububble">{{ m.text }}</div>
            </div>
            <AiMessage v-else :msg="m" />
          </template>
        </div>
      </div>
      <div class="cbottom">
        <div class="cwrap"><Composer placeholder="继续追问，或换一个问题…" /></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.head { height: 48px; flex: none; display: flex; align-items: center; gap: 10px; padding: 0 22px; border-bottom: 1px solid var(--line); }
.title { font-size: 14px; color: var(--ink); }
.spacer { flex: 1; }
.dbpill { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink2); }
.okdot { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
.mock { font-size: 11px; font-weight: 600; color: var(--warn); background: var(--warnbg); border-radius: 4px; padding: 1px 7px; }
.empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 24px 60px; }
.greet { font-size: 34px; font-weight: 400; letter-spacing: -0.02em; margin-bottom: 26px; }
.cwrap { width: 100%; max-width: 680px; }
.samples { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; max-width: 680px; margin-top: 16px; }
.sample { border: 1px solid var(--line); border-radius: 999px; padding: 5px 13px; font-size: 12.5px; color: var(--ink2); background: var(--card); cursor: pointer; }
.sample:hover { border-color: var(--acc); color: var(--acc); }
.msgs { flex: 1; overflow-y: auto; padding: 26px 24px 8px; }
.col { max-width: 740px; margin: 0 auto; display: flex; flex-direction: column; gap: 26px; }
.urow { display: flex; justify-content: flex-end; }
.ububble { max-width: 76%; background: var(--soft); border-radius: 14px; padding: 9px 15px; font-size: 15px; }
.cbottom { flex: none; padding: 8px 24px 20px; display: flex; justify-content: center; }
</style>
