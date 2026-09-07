<template>
  <section class="sound-library-page">
    <header><div><h1>音效与背景音乐</h1><p>浏览、试听内置素材，或导入自己的音频。点击「背景音乐」快速挑选配乐；在项目中加入时会自动放到 BGM 轨，可以调节音量和淡入淡出。</p></div><el-button @click="$router.push('/projects')">进入项目挑选素材</el-button></header>
    <SoundLibraryPanel />
  </section>
</template>
<script setup>
import SoundLibraryPanel from '../components/SoundLibraryPanel.vue'
</script>
<style scoped>
.sound-library-page{max-width:1280px;margin:0 auto;padding:20px;display:grid;gap:24px}.sound-library-page header{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.sound-library-page h1{font-size:24px;margin:0 0 8px}.sound-library-page p{margin:0;max-width:720px;line-height:1.7;color:var(--el-text-color-secondary)}
</style>
