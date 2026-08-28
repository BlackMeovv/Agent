import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import "./styles/tokens.css";

createApp(App).use(createPinia()).mount("#app");

// 滚动条闲置自动隐藏：滚动中给元素加 .scrolling，停手 900ms 后移除（样式见 tokens.css）
const scrollTimers = new WeakMap<Element, number>();
document.addEventListener(
  "scroll",
  (e) => {
    const el = e.target;
    if (!(el instanceof Element)) return;
    el.classList.add("scrolling");
    window.clearTimeout(scrollTimers.get(el));
    scrollTimers.set(el, window.setTimeout(() => el.classList.remove("scrolling"), 900));
  },
  { capture: true, passive: true },
);
