<script setup lang="ts">
import { computed } from "vue";
import { exportCsv } from "../lib/csv";
import type { AiMsg } from "../stores/app";

const props = defineProps<{ msg: AiMsg }>();

const numCols = computed(() =>
  (props.msg.columns || []).map((_, i) =>
    (props.msg.rows || []).length > 0 &&
    (props.msg.rows || []).every((r) => r[i] === null || typeof r[i] === "number"),
  ),
);
</script>

<template>
  <div class="card">
    <div class="head">
      <span class="label">查询结果 · {{ msg.rowCount }} 行</span>
      <button class="export" @click="exportCsv(msg.columns || [], msg.rows || [])">导出 CSV</button>
    </div>
    <div class="wrap">
      <table>
        <thead>
          <tr>
            <th class="idx">#</th>
            <th v-for="(c, i) in msg.columns" :key="c" :class="{ num: numCols[i] }">{{ c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, ri) in msg.rows" :key="ri">
            <td class="idx mono">{{ ri + 1 }}</td>
            <td v-for="(v, ci) in r" :key="ci" :class="{ num: numCols[ci] }">
              <i v-if="v === null">NULL</i><template v-else>{{ v }}</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="(msg.rowCount || 0) > (msg.rows?.length || 0)" class="more">
      共 {{ msg.rowCount }} 行，展示前 {{ msg.rows?.length }} 行
    </div>
  </div>
</template>

<style scoped>
.card { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--card); }
.head { display: flex; align-items: center; padding: 6px 12px; border-bottom: 1px solid var(--line); }
.label { font-size: 12px; color: var(--ink3); }
.export { margin-left: auto; border: none; background: none; color: var(--acc); font-size: 12px; cursor: pointer; padding: 0; }
.wrap { max-height: 280px; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { position: sticky; top: 0; background: var(--soft); color: var(--ink2); font-weight: 600; text-align: left; padding: 6px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th.idx { color: var(--ink3); font-weight: 400; text-align: right; width: 40px; }
td { padding: 6px 12px; border-bottom: 1px solid var(--line); color: var(--ink); white-space: nowrap; font-variant-numeric: tabular-nums; }
td.idx { text-align: right; color: var(--ink3); font-size: 12px; }
th.num, td.num { text-align: right; }
td i { color: var(--ink3); }
.more { padding: 5px 12px; font-size: 12px; color: var(--ink3); }
</style>
