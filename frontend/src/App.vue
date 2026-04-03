<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <el-container class="layout">
    <el-aside width="200px">
      <div class="logo">测试平台</div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#1d1e1f"
        text-color="#cfd3dc"
        active-text-color="#409eff"
      >
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/projects">测试项目</el-menu-item>
        <el-menu-item index="/cases">测试用例</el-menu-item>
        <el-menu-item index="/suites">测试套件</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header height="56px" class="header">
        <span class="title">{{
          route.name === 'home'
            ? '概览'
            : route.name === 'projects'
              ? '测试项目'
              : route.name === 'suites'
                ? '测试套件'
                : '测试用例'
        }}</span>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.logo {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-weight: 600;
  color: #fff;
  background: #141414;
  border-bottom: 1px solid #303030;
}
.header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
.title {
  font-size: 16px;
  font-weight: 500;
}
.main {
  background: var(--el-fill-color-blank);
}
</style>
