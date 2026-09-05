<template>
  <section class="sound-library-page">
    <header><div><h1>音效库</h1><p>浏览内置音效、试听和导入自己的素材。在项目台本的音效行点击「AI 推荐音效」，即可按小说情节挑选并加入。</p></div><el-button @click="$router.push('/projects')">进入项目挑选音效</el-button></header>
    <SoundLibraryPanel />
  </section>
</template>
<script setup>
import SoundLibraryPanel from '../components/SoundLibraryPanel.vue'
</script>
<style scoped>
.sound-library-page{max-width:1280px;margin:0 auto;padding:20px;display:grid;gap:24px}.sound-library-page header{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.sound-library-page h1{font-size:24px;margin:0 0 8px}.sound-library-page p{margin:0;max-width:720px;line-height:1.7;color:var(--el-text-color-secondary)}
</style>
