<script setup lang="ts">
// DeepQuery logo：对话气泡里的三根均衡器柱。animated 时柱子跳动（加载指示器）
withDefaults(defineProps<{ size?: number; animated?: boolean }>(), { size: 34, animated: false });
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 64 64"
    fill="none"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path
      d="M12.5 26.5 C11 16 21 8.5 32.5 9 C45.5 9.5 55 16 53.5 27.5 C52.2 37.5 44 43.5 33.5 43.5 C30.5 43.5 28 43.2 25.5 42.5 L16.5 49.5 C15 50.7 13.2 49.3 14 47.5 L17 40.5 C14 37 13 32 12.5 26.5 Z"
      stroke="var(--acc)"
      stroke-width="5.5"
    />
    <path class="bar b1" :class="{ on: animated }" d="M23.5 35 C23.1 33 23.2 31 23.7 28.5" stroke="var(--acc)" stroke-width="6.5" />
    <path class="bar b2" :class="{ on: animated }" d="M31.8 35.2 C31.5 31 31.6 25.5 32.2 21" stroke="var(--acc2)" stroke-width="6.5" />
    <path class="bar b3" :class="{ on: animated }" d="M40 35 C39.7 33 39.8 30 40.3 26" stroke="var(--acc)" stroke-width="6.5" />
  </svg>
</template>

<style scoped>
.bar { transform-box: fill-box; transform-origin: center bottom; }
.bar.on { animation: dq-bounce 0.9s ease-in-out infinite; }
.b2.on { animation-delay: 0.15s; }
.b3.on { animation-delay: 0.3s; }
</style>
