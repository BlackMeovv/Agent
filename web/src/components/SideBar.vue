<script setup lang="ts">
import { ref } from "vue";
import { useAppStore } from "../stores/app";

const store = useAppStore();
const schemaOpen = ref(false);
const memOpen = ref(false);
const openTables = ref<Record<string, boolean>>({});

function addMem() {
  const note = window.prompt("新增记忆（会注入到后续每次提问）");
  if (note && note.trim()) store.addMem(note.trim());
}
</script>

<template>
  <aside class="side">
    <div class="brand">
      <div class="logo">IA</div>
      <div class="name serif">Insight</div>
    </div>

    <div class="pad">
      <div class="row" @click="store.newChat()">
        <span class="ic">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
        </span>
        新建提问
      </div>
    </div>

    <div class="scroll">
      <div class="row" @click="schemaOpen = !schemaOpen">
        <span class="ic">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <ellipse cx="8" cy="3.8" rx="5.2" ry="2.2" stroke="currentColor" stroke-width="1.3" />
            <path d="M2.8 3.8v8.4c0 1.2 2.3 2.2 5.2 2.2s5.2-1 5.2-2.2V3.8" stroke="currentColor" stroke-width="1.3" />
            <path d="M2.8 8c0 1.2 2.3 2.2 5.2 2.2S13.2 9.2 13.2 8" stroke="currentColor" stroke-width="1.3" />
          </svg>
        </span>
        库表结构
        <span class="meta">{{ store.schema.length }} 表</span>
        <span class="mchev" :class="{ open: schemaOpen }">›</span>
      </div>
      <div v-if="schemaOpen" class="tree">
        <div v-for="tb in store.schema" :key="tb.name">
          <div class="trow" @click="openTables[tb.name] = !openTables[tb.name]">
            <span class="chev" :class="{ open: openTables[tb.name] }">›</span>
            <span class="mono tname">{{ tb.name }}</span>
            <span class="meta">{{ tb.columns.length }}</span>
          </div>
          <div v-if="openTables[tb.name]" class="cols">
            <div
              v-for="cl in tb.columns"
              :key="cl.name"
              class="crow mono"
              title="点击插入到输入框"
              @click="store.insertToken(cl.name)"
            >
              {{ cl.name }}<span class="cty">{{ cl.type }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="row" @click="memOpen = !memOpen">
        <span class="ic">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <path d="M8 2l1.5 4.5L14 8l-4.5 1.5L8 14 6.5 9.5 2 8l4.5-1.5L8 2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
          </svg>
        </span>
        记忆
        <span class="meta">{{ store.mems.length }} 条</span>
        <span class="mchev" :class="{ open: memOpen }">›</span>
      </div>
      <div v-if="memOpen" class="mems">
        <div v-for="mm in store.mems" :key="mm.id" class="mem">
          <span class="mtext">{{ mm.note }}</span>
          <span class="mdel" @click="store.delMem(mm.id)">✕</span>
        </div>
        <button class="madd" @click="addMem">＋ 添加记忆</button>
      </div>

      <div class="divider"></div>
      <div class="histlabel">历史</div>
      <div
        v-for="cv in store.convos"
        :key="cv.id"
        class="hist"
        :class="{ cur: cv.id === store.curConvo }"
        @click="store.pickConvo(cv.id)"
      >
        {{ cv.title }}
      </div>
    </div>

    <div class="foot">
      <div class="avatar">BM</div>
      <span class="uname">BlackMeovv</span>
      <button class="theme" title="切换主题" @click="store.toggleTheme()">
        <svg v-if="store.theme === 'light'" width="15" height="15" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="3.1" stroke="currentColor" stroke-width="1.3" />
          <path d="M8 1.3v1.6M8 13.1v1.6M1.3 8h1.6M13.1 8h1.6M3.3 3.3l1.1 1.1M11.6 11.6l1.1 1.1M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
        </svg>
        <svg v-else width="15" height="15" viewBox="0 0 16 16" fill="none">
          <path d="M13.4 9.6A5.9 5.9 0 1 1 6.4 2.6a4.7 4.7 0 0 0 7 7z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
        </svg>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.side { width: 252px; flex: none; background: var(--side); border-right: 1px solid var(--line); display: flex; flex-direction: column; overflow: hidden; }
.brand { padding: 18px 16px 10px; display: flex; align-items: center; gap: 9px; }
.logo { width: 22px; height: 22px; border-radius: 6px; background: var(--acc); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
.name { font-size: 19px; font-weight: 600; letter-spacing: -0.01em; }
.pad { padding: 4px 10px 10px; }
.scroll { flex: 1; overflow-y: auto; padding: 0 10px 12px; }
.row { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 8px; cursor: pointer; font-size: 14px; color: var(--ink); }
.row:hover { background: var(--soft); }
.ic { width: 16px; flex: none; display: flex; align-items: center; justify-content: center; color: var(--ink2); }
.meta { margin-left: auto; font-size: 12px; color: var(--ink3); }
.mchev { font-size: 12px; color: var(--ink3); transition: transform 0.15s; display: inline-block; }
.mchev.open { transform: rotate(90deg); }
.tree { padding: 2px 0 0; }
.trow { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.trow:hover { background: var(--soft); }
.chev { width: 10px; font-size: 11px; color: var(--ink3); transition: transform 0.15s; display: inline-block; }
.chev.open { transform: rotate(90deg); }
.tname { font-size: 12.5px; }
.cols { margin: 0 0 4px 24px; padding-left: 10px; border-left: 1px solid var(--line); }
.crow { display: flex; gap: 8px; padding: 2px 6px; border-radius: 5px; cursor: pointer; font-size: 12px; color: var(--ink2); }
.crow:hover { background: var(--accbg); color: var(--acc); }
.cty { color: var(--ink3); font-size: 10.5px; }
.mems { display: flex; flex-direction: column; gap: 5px; padding: 4px 4px 0; }
.mem { display: flex; align-items: flex-start; gap: 6px; background: var(--card); border: 1px solid var(--line); border-radius: 7px; padding: 6px 8px; font-size: 12px; color: var(--ink2); }
.mtext { flex: 1; }
.mdel { cursor: pointer; color: var(--ink3); line-height: 1.2; }
.mdel:hover { color: var(--err); }
.madd { align-self: flex-start; border: none; background: none; color: var(--acc); font-size: 12px; cursor: pointer; padding: 2px 4px; }
.divider { height: 1px; background: var(--line); margin: 14px 6px 8px; }
.histlabel { padding: 0 10px 4px; font-size: 12px; color: var(--ink3); }
.hist { padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 13.5px; color: var(--ink2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hist:hover { background: var(--soft); }
.hist.cur { background: var(--soft); color: var(--ink); }
.foot { border-top: 1px solid var(--line); padding: 10px 14px; display: flex; align-items: center; gap: 8px; }
.avatar { width: 24px; height: 24px; border-radius: 50%; background: var(--accbg); color: var(--acc); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; }
.uname { font-size: 13px; color: var(--ink2); }
.theme { margin-left: auto; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border: none; border-radius: 6px; background: none; color: var(--ink3); cursor: pointer; padding: 0; }
.theme:hover { background: var(--soft); color: var(--ink); }
</style>
