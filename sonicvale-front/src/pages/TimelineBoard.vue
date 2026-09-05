<template><p class="route-progress" role="status">正在打开章节的声音编排…</p></template>
<script setup>
import { onMounted } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { workspaceLocation } from '../workspace/navigation'
const route=useRoute(),router=useRouter()
onMounted(()=>router.replace(Number(route.query.project_id)?workspaceLocation(route.query.project_id,route.query.chapter_id,'timeline',route.query.line_id):'/projects'))
</script>
