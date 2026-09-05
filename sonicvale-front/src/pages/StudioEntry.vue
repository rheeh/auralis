<template><p role="status">正在打开项目工作台…</p></template>
<script setup>
import { onMounted } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { fetchChatSession } from '../api/drama'
const route=useRoute(),router=useRouter()
onMounted(async()=>{try{const sessionId=route.params.sessionId;if(sessionId){const response=await fetchChatSession(sessionId);if(response?.data?.project_id){await router.replace({path:`/projects/${response.data.project_id}/workspace`,query:{session_id:sessionId}});return}}const project=Number(route.query.project_id);await router.replace(project?{path:`/projects/${project}/workspace`,query:{...route.query}}:'/projects')}catch{router.replace('/projects')}})
</script>
