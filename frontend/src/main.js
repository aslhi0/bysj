import { createApp } from 'vue'
/* 按需引入模板组件时，Message / MessageBox / Loading 等函数式 API 不会自动注入样式 */
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/overlay/style/css'
import 'element-plus/es/components/notification/style/css'
import './style.css'
import App from './App.vue'
import router from './router'

createApp(App).use(router).mount('#app')
