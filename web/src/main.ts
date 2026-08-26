import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import "./styles/tokens.css";

createApp(App).use(createPinia()).mount("#app");
