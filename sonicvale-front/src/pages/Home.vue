<template>
  <div class="landing-page" :class="{ 'demo-playing': demoPlaying }" @mousemove="handlePointer" @mouseleave="resetPointer">
    <section class="hero-shell">
      <header class="landing-nav enter-nav">
        <RouterLink to="/home" class="landing-brand" aria-label="Auralis 首页">
          <span class="brand-wave" aria-hidden="true"><i v-for="i in 7" :key="i" /></span>
          <strong>Auralis</strong>
        </RouterLink>
        <nav aria-label="首页导航">
          <a class="active" href="#hero">首页</a>
          <RouterLink to="/projects">创作</RouterLink>
          <RouterLink to="/projects">项目</RouterLink>
          <RouterLink to="/voices">音色库</RouterLink>
          <RouterLink to="/config">模型设置</RouterLink>
        </nav>
        <div class="nav-actions">
          <RouterLink class="ghost-link" to="/config">设置</RouterLink>
          <RouterLink class="nav-primary" to="/projects">开始创作</RouterLink>
        </div>
      </header>

      <div id="hero" class="hero-content">
        <div class="hero-copy">
          <p class="product-kicker enter-title">AI AUDIO DRAMA STUDIO</p>
          <h1 class="enter-title">Auralis</h1>
          <p class="cn-title enter-subtitle">AI 广 播 剧</p>
          <p class="hero-description enter-subtitle">把小说变成真正可制作的广播剧台本，为每个角色建立声线，并逐句生成、试听与精修。</p>
          <div class="hero-actions enter-actions">
            <RouterLink class="start-button" to="/projects"><span>✦</span>开始创作</RouterLink>
            <button class="demo-button" type="button" :aria-pressed="demoPlaying" @click="toggleDemo">
              <span class="button-icon">{{ demoPlaying ? 'Ⅱ' : '▶' }}</span>{{ demoPlaying ? '暂停 Demo' : '体验 Demo' }}
            </button>
          </div>
        </div>

        <div class="visual-stage" :style="stageTransform" aria-label="动态声场视觉">
          <canvas ref="waveCanvas" class="wave-canvas" aria-hidden="true" />

          <div class="ring-system enter-rings" :style="ringTransform" aria-hidden="true">
            <svg viewBox="0 0 620 620" role="presentation">
              <defs>
                <filter id="ringGlow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
                <linearGradient id="ringGold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff"/><stop offset=".48" stop-color="#e9d5ad"/><stop offset="1" stop-color="#9ebbd7"/></linearGradient>
              </defs>
              <g class="ring ring-one"><circle cx="310" cy="310" r="205"/><circle class="flow-dots" cx="310" cy="310" r="205"/></g>
              <g class="ring ring-two"><circle cx="310" cy="310" r="232"/><circle class="flow-dots sparse" cx="310" cy="310" r="232"/></g>
              <g class="ring ring-three"><circle cx="310" cy="310" r="259"/></g>
              <g class="ring ring-four"><circle cx="310" cy="310" r="282"/></g>
            </svg>
          </div>

          <div class="particle-field" :style="particleTransform" aria-hidden="true">
            <i v-for="particle in particles" :key="particle.id" :style="particle.style" />
          </div>

          <div class="singer-parallax enter-person" :style="personTransform">
            <img class="anime-singer" :src="singerImage" alt="戴耳机随音乐轻轻律动的二次元女歌姬" />
          </div>
        </div>

        <div v-if="latestProject" class="continue-card enter-actions" @click="openLatest">
          <div class="project-art"><span>{{ latestProject.name.slice(0,1) }}</span></div>
          <div><small>继续上次创作</small><strong>{{ latestProject.name }}</strong><span>{{ formatDate(latestProject.updated_at || latestProject.created_at) }}</span></div>
          <button type="button" aria-label="打开最近项目">›</button>
        </div>

        <a class="explore-link" href="#features">探索声音的无限可能<span>↓</span></a>
      </div>
    </section>

    <section id="features" class="feature-strip" aria-label="产品能力">
      <RouterLink v-for="item in features" :key="item.title" :to="item.to">
        <span class="feature-icon">{{ item.icon }}</span>
        <div><strong>{{ item.title }}</strong><small>{{ item.caption }}</small></div>
      </RouterLink>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchProjects } from '../api/project'
import singerImage from '../assets/visuals/auralis-anime-singer.png'

const router = useRouter()
const waveCanvas = ref(null)
const projects = ref([])
const demoPlaying = ref(false)
const pointer = ref({ x:0, y:0 })
const latestProject = computed(() => projects.value[0] || null)
const features = [
  { icon:'≋', title:'AI 台本改编', caption:'声音优先，克制旁白', to:'/projects' },
  { icon:'♬', title:'多角色声线', caption:'人物卡绑定独立音色', to:'/voices' },
  { icon:'⌁', title:'逐句音频精修', caption:'语速、音量、停顿与裁剪', to:'/projects' },
  { icon:'✦', title:'一页完成制作', caption:'台本、音色和音频同屏', to:'/projects' },
]
const particles = Array.from({ length:30 }, (_,id) => {
  const angle = (id * 137.5) * Math.PI / 180
  const radius = 18 + (id % 9) * 4.2
  return { id, style:{ left:`${50 + Math.cos(angle)*radius}%`, top:`${49 + Math.sin(angle)*radius*.72}%`, width:`${1 + id%3}px`, height:`${1 + id%3}px`, '--delay':`${-(id%11)*.9}s`, '--duration':`${9 + id%8}s` } }
})
const stageTransform = computed(() => ({ '--px':`${pointer.value.x*2}px`, '--py':`${pointer.value.y*2}px` }))
const ringTransform = computed(() => ({ transform:`translate3d(${pointer.value.x*5}px,${pointer.value.y*5}px,0)` }))
const particleTransform = computed(() => ({ transform:`translate3d(${pointer.value.x*8}px,${pointer.value.y*8}px,0)` }))
const personTransform = computed(() => ({ transform:`translate3d(${pointer.value.x*3}px,${pointer.value.y*4}px,0)` }))

let frameId = 0
let resizeObserver = null
let phase = 0
let energy = 0
let lastTime = 0

onMounted(async () => {
  try { projects.value = await fetchProjects() } catch { projects.value = [] }
  await nextTick()
  resizeObserver = new ResizeObserver(resizeCanvas)
  if (waveCanvas.value) resizeObserver.observe(waveCanvas.value)
  document.addEventListener('visibilitychange', handleVisibility)
  resizeCanvas()
  startWave()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  resizeObserver?.disconnect()
  document.removeEventListener('visibilitychange', handleVisibility)
})

function resizeCanvas() {
  const canvas = waveCanvas.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.max(1, Math.floor(rect.width * dpr))
  canvas.height = Math.max(1, Math.floor(rect.height * dpr))
  canvas.getContext('2d')?.setTransform(dpr,0,0,dpr,0,0)
}

function startWave() {
  cancelAnimationFrame(frameId)
  lastTime = performance.now()
  frameId = requestAnimationFrame(drawWave)
}

function drawWave(now) {
  const canvas = waveCanvas.value
  if (!canvas || document.hidden) return
  const ctx = canvas.getContext('2d')
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  const dt = Math.min(34, now-lastTime)
  lastTime = now
  phase += dt * .001 * (demoPlaying.value ? 1.35 : .72)
  energy += ((demoPlaying.value ? 1 : 0)-energy) * .035
  ctx.clearRect(0,0,width,height)
  const centerY = height * .54
  ctx.save()
  ctx.strokeStyle = 'rgba(73, 144, 196, .13)'
  ctx.lineWidth = 1
  ctx.setLineDash([2, 8])
  ctx.beginPath()
  ctx.moveTo(0, centerY)
  ctx.lineTo(width, centerY)
  ctx.stroke()
  ctx.restore()
  const gradient = ctx.createLinearGradient(0,0,width,0)
  gradient.addColorStop(0,'rgba(71,161,231,.12)')
  gradient.addColorStop(.26,'rgba(55,155,232,.82)')
  gradient.addColorStop(.56,'rgba(45,195,207,.98)')
  gradient.addColorStop(.78,'rgba(255,139,156,.9)')
  gradient.addColorStop(1,'rgba(255,181,117,.12)')
  ctx.strokeStyle = gradient
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.shadowBlur = 9 + energy*8
  ctx.shadowColor = 'rgba(52,170,221,.62)'
  ctx.beginPath()
  for (let x=2;x<=width;x+=7) {
    const normalized=x/width
    const focus=.18 + Math.exp(-Math.pow((normalized-.62)/.27,2))*.82
    const harmonic=Math.abs(Math.sin(x*.071-phase*3.4)*.58 + Math.sin(x*.023-phase*1.7)*.3 + Math.sin(x*.13-phase*4.8)*.12)
    const amplitude=2.5 + focus*(6 + harmonic*(22+energy*34))
    ctx.moveTo(x,centerY-amplitude)
    ctx.lineTo(x,centerY+amplitude)
  }
  ctx.stroke()
  ctx.globalAlpha=.22
  ctx.lineWidth=1.2
  ctx.beginPath()
  for (let x=0;x<=width;x+=4) {
    const focus=Math.exp(-Math.pow((x/width-.64)/.27,2))
    const y=centerY + Math.sin(x*.032-phase*2.1)*(3+focus*(11+energy*16))
    x===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y)
  }
  ctx.stroke()
  ctx.globalAlpha=1
  if (demoPlaying.value) {
    const playhead=((phase*.12)%1)*width
    const glow=ctx.createRadialGradient(playhead,centerY,0,playhead,centerY,22)
    glow.addColorStop(0,'rgba(255,255,255,.95)')
    glow.addColorStop(.25,'rgba(53,201,211,.72)')
    glow.addColorStop(1,'rgba(53,201,211,0)')
    ctx.fillStyle=glow
    ctx.beginPath()
    ctx.arc(playhead,centerY,22,0,Math.PI*2)
    ctx.fill()
  }
  frameId=requestAnimationFrame(drawWave)
}

function handleVisibility() { if (document.hidden) cancelAnimationFrame(frameId); else startWave() }
function toggleDemo() { demoPlaying.value=!demoPlaying.value }
function handlePointer(event) {
  if (window.matchMedia('(max-width: 760px), (pointer: coarse)').matches) return
  pointer.value={x:(event.clientX/window.innerWidth-.5)*2,y:(event.clientY/window.innerHeight-.5)*2}
}
function resetPointer(){pointer.value={x:0,y:0}}
function openLatest(){if(latestProject.value)router.push(`/projects/${latestProject.value.id}/workspace`)}
function formatDate(value){if(!value)return '最近编辑';const date=new Date(value);return Number.isNaN(date.getTime())?'最近编辑':date.toLocaleDateString('zh-CN',{month:'short',day:'numeric'})}
</script>

<style scoped>
.landing-page{min-height:100%;padding:4px;color:#102a4a;background:linear-gradient(135deg,#f1eee8,#dce6ef);box-sizing:border-box;font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.hero-shell{position:relative;min-height:calc(100vh - 180px);border-radius:22px;overflow:hidden;background:radial-gradient(circle at 68% 53%,rgba(255,250,235,.92) 0 3%,rgba(255,245,222,.42) 18%,transparent 42%),radial-gradient(circle at 31% 36%,rgba(255,255,255,.96),rgba(250,245,237,.88) 39%,transparent 66%),linear-gradient(112deg,#faf8f4 8%,#e9edf1 54%,#b9cddd 100%);box-shadow:0 24px 70px rgba(41,66,93,.18)}.hero-shell:after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(180deg,rgba(255,255,255,.26),transparent 30%),radial-gradient(circle at 78% 50%,transparent 20%,rgba(102,135,164,.1) 75%)}
.landing-nav{position:relative;z-index:20;display:grid;grid-template-columns:220px 1fr 220px;align-items:center;min-height:78px;padding:0 48px}.landing-brand{display:flex;align-items:center;gap:13px;color:#102a4a;text-decoration:none;font-size:25px}.brand-wave{display:flex;align-items:center;gap:3px;height:28px}.brand-wave i{width:3px;border-radius:3px;background:#102a4a}.brand-wave i:nth-child(1),.brand-wave i:nth-child(7){height:8px}.brand-wave i:nth-child(2),.brand-wave i:nth-child(6){height:16px}.brand-wave i:nth-child(3),.brand-wave i:nth-child(5){height:25px}.brand-wave i:nth-child(4){height:33px}.landing-nav nav{display:flex;justify-content:center;gap:48px}.landing-nav nav a{position:relative;padding:28px 0 13px;color:#25384d;text-decoration:none;font-size:14px}.landing-nav nav a:after{content:"";position:absolute;left:50%;right:50%;bottom:0;height:1px;background:#17395e;transition:left .2s,right .2s}.landing-nav nav a:hover:after,.landing-nav nav a.active:after{left:0;right:0}.nav-actions{display:flex;justify-content:flex-end;gap:12px}.ghost-link,.nav-primary{display:grid;place-items:center;min-width:76px;height:42px;border-radius:13px;color:#142a43;text-decoration:none;background:rgba(255,255,255,.7);box-shadow:inset 0 0 0 1px rgba(255,255,255,.72)}.nav-primary{min-width:106px;color:#fff;background:linear-gradient(135deg,#17375b,#061a34);box-shadow:0 12px 26px rgba(14,38,66,.2)}
.hero-content{position:relative;z-index:3;min-height:calc(100vh - 258px)}.hero-copy{position:relative;z-index:9;width:min(520px,40vw);padding:12vh 0 120px 7vw}.product-kicker{margin:0 0 18px;color:#75869a;font-size:11px;letter-spacing:.28em}.hero-copy h1{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:clamp(86px,10vw,168px);font-weight:400;line-height:.78;letter-spacing:-.06em}.cn-title{margin:30px 0 0;font-size:27px;letter-spacing:.48em}.hero-description{max-width:460px;margin:24px 0 0;color:#5a6c7e;font-size:14px;line-height:1.8}.hero-actions{display:flex;gap:20px;margin-top:35px}.start-button,.demo-button{display:flex;align-items:center;justify-content:center;gap:13px;height:60px;padding:0 34px;border:0;border-radius:30px;box-sizing:border-box;text-decoration:none;font-size:15px;transition:transform .18s ease,box-shadow .18s ease}.start-button{color:#fff;background:linear-gradient(135deg,#486584,#071f3c);box-shadow:0 16px 30px rgba(24,50,79,.22)}.start-button:hover{transform:translateY(-2px);box-shadow:0 17px 36px rgba(30,67,106,.32),0 0 24px rgba(150,195,230,.28)}.start-button:active,.demo-button:active{transform:scale(.97)}.demo-button{cursor:pointer;color:#26384a;background:rgba(255,255,255,.68);box-shadow:0 10px 28px rgba(65,82,100,.1),inset 0 0 0 1px rgba(255,255,255,.92)}.demo-button:hover{transform:translateY(-2px)}.button-icon{display:grid;place-items:center;width:25px;height:25px;border-radius:50%;font-size:10px;background:rgba(255,255,255,.8)}
.visual-stage{position:absolute;z-index:4;inset:0;pointer-events:none;transition:transform .8s cubic-bezier(.2,.8,.2,1)}.ring-system{position:absolute;right:7vw;top:48%;width:min(56vw,700px);aspect-ratio:1;translate:0 -50%;transition:transform .9s cubic-bezier(.2,.8,.2,1)}.ring-system svg{width:100%;height:100%;overflow:visible}.ring circle{fill:none;stroke:url(#ringGold);transform-origin:310px 310px;filter:url(#ringGlow)}.ring-one circle:first-child{stroke-width:4;opacity:.92;animation:ring-cw 17s linear infinite,ring-breathe 8s ease-in-out infinite}.ring-two circle:first-child{stroke-width:1.3;stroke-dasharray:8 13;opacity:.65;animation:ring-ccw 22s linear infinite}.ring-three circle{stroke-width:.8;stroke-dasharray:2 11;opacity:.48;animation:ring-cw 24s linear infinite}.ring-four circle{stroke-width:.6;stroke-dasharray:1 17;opacity:.4;animation:ring-ccw 19s linear infinite}.flow-dots{stroke-width:3!important;stroke-linecap:round;stroke-dasharray:1 34!important;animation:ring-cw 11s linear infinite!important}.flow-dots.sparse{opacity:.55;animation:ring-ccw 15s linear infinite!important}.demo-playing .ring-system{filter:brightness(1.14) drop-shadow(0 0 15px rgba(255,240,205,.5))}
.wave-canvas{position:absolute;z-index:2;left:0;top:42%;width:100%;height:28%;opacity:.86;filter:drop-shadow(0 0 5px rgba(255,249,230,.7))}.particle-field{position:absolute;z-index:5;right:5vw;top:10%;width:min(60vw,740px);height:78%;transition:transform 1s cubic-bezier(.2,.8,.2,1)}.particle-field i{position:absolute;border-radius:50%;background:#fff;opacity:.35;box-shadow:0 0 8px rgba(255,247,215,.8);animation:particle-float var(--duration) ease-in-out var(--delay) infinite,particle-blink 5s ease-in-out var(--delay) infinite}.listener-silhouette{position:absolute;z-index:7;right:calc(7vw + min(56vw,700px)/2 - 90px);top:36%;width:180px;height:360px;fill:#1f3147;filter:drop-shadow(0 20px 12px rgba(22,38,55,.18));transition:transform 1s cubic-bezier(.2,.8,.2,1);overflow:visible}.person-body{transform-origin:90px 210px;animation:body-groove 2.9s ease-in-out infinite}.person-head{transform-origin:90px 83px;animation:head-groove 2.9s ease-in-out -.16s infinite}.hair{opacity:.98;transform-origin:91px 40px;animation:hair-sway 2.9s ease-in-out -.28s infinite}.headphones{fill:none;stroke:#1f3147;stroke-width:7;stroke-linecap:round}.arm{transform-origin:90px 105px}.arm-left{animation:arm-left 2.9s ease-in-out infinite}.arm-right{animation:arm-right 2.9s ease-in-out infinite}.leg-left{transform-origin:82px 215px;animation:leg-shift 2.9s ease-in-out infinite}.leg-right{transform-origin:102px 215px;animation:leg-shift 2.9s ease-in-out -1.45s infinite}.coat-tail{transform-origin:90px 190px;animation:coat-sway 2.9s ease-in-out -.2s infinite}.demo-playing .person-body,.demo-playing .person-head,.demo-playing .hair,.demo-playing .arm,.demo-playing .leg-left,.demo-playing .leg-right,.demo-playing .coat-tail{animation-duration:2.55s}
.continue-card{position:absolute;z-index:11;right:3.5vw;bottom:24px;display:grid;grid-template-columns:58px minmax(150px,1fr) 34px;gap:12px;align-items:center;width:min(330px,28vw);padding:12px 14px;border-radius:20px;cursor:pointer;background:rgba(255,255,255,.68);box-shadow:0 16px 38px rgba(51,75,99,.14);backdrop-filter:blur(18px)}.project-art{display:grid;place-items:center;width:58px;height:58px;border-radius:14px;color:#fff;background:linear-gradient(145deg,#759ebc,#173856)}.continue-card small,.continue-card strong,.continue-card span{display:block}.continue-card small,.continue-card span{color:#6e7d8d;font-size:10px}.continue-card strong{margin:4px 0;font-size:13px}.continue-card button{width:34px;height:34px;border:0;border-radius:50%;cursor:pointer;color:#fff;background:#153656;font-size:22px}.explore-link{position:absolute;z-index:10;left:7vw;bottom:28px;display:flex;gap:34px;color:#485e75;text-decoration:none;font-size:12px;letter-spacing:.12em}.explore-link span{font-size:18px}
.feature-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:26px;padding:34px 7vw;background:rgba(255,255,255,.82)}.feature-strip a{display:flex;align-items:center;gap:24px;min-height:96px;padding:0 28px;border:1px solid rgba(35,63,90,.09);border-radius:22px;color:#213850;text-decoration:none;background:rgba(255,255,255,.54);box-shadow:0 12px 32px rgba(48,69,90,.05);transition:transform .2s ease,box-shadow .2s ease}.feature-strip a:hover{transform:translateY(-3px);box-shadow:0 16px 36px rgba(48,69,90,.1)}.feature-icon{font-size:33px}.feature-strip strong,.feature-strip small{display:block}.feature-strip small{margin-top:8px;color:#738294;font-size:12px}
.enter-nav{animation:enter-fade .65s ease both}.enter-title{animation:enter-rise .72s .12s ease both}.enter-subtitle{animation:enter-rise .72s .28s ease both}.enter-actions{animation:enter-rise .68s .42s ease both}.enter-rings{animation:enter-rings 1.05s .08s ease both}.enter-person{animation:enter-person .72s .48s ease both}
@keyframes ring-cw{to{transform:rotate(360deg)}}@keyframes ring-ccw{to{transform:rotate(-360deg)}}@keyframes ring-breathe{50%{opacity:.68;stroke-width:5.5}}@keyframes particle-float{50%{translate:4px -12px}}@keyframes particle-blink{50%{opacity:.1}}@keyframes body-groove{0%,100%{transform:translateY(0) rotate(-1deg)}50%{transform:translateY(-4px) rotate(1deg)}}@keyframes head-groove{0%,100%{transform:rotate(-1deg)}50%{transform:rotate(1.4deg)}}@keyframes hair-sway{0%,100%{transform:skewX(-1deg)}50%{transform:skewX(2deg)}}@keyframes arm-left{0%,100%{transform:rotate(1deg)}50%{transform:rotate(-3deg)}}@keyframes arm-right{0%,100%{transform:rotate(-1deg)}50%{transform:rotate(3deg)}}@keyframes leg-shift{0%,100%{transform:translateX(0)}50%{transform:translateX(2px)}}@keyframes coat-sway{0%,100%{transform:skewX(-1deg)}50%{transform:skewX(1.5deg)}}@keyframes enter-fade{from{opacity:0}to{opacity:1}}@keyframes enter-rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}@keyframes enter-rings{from{opacity:0;filter:blur(14px)}to{opacity:1;filter:blur(0)}}@keyframes enter-person{from{opacity:0;translate:0 12px}to{opacity:1;translate:0 0}}
@media(max-width:1100px){.landing-nav{grid-template-columns:180px 1fr 180px;padding:0 28px}.landing-nav nav{gap:22px}.hero-copy{width:45vw;padding-left:5vw}.continue-card{display:none}.feature-strip{gap:12px;padding-inline:3vw}.feature-strip a{padding:0 15px}.ring-system{right:-2vw}.listener-silhouette{right:calc(-2vw + min(56vw,700px)/2 - 90px)}}
@media(max-width:760px){.landing-page{padding:0}.hero-shell{min-height:800px;border-radius:0}.landing-nav{display:flex;justify-content:space-between;padding:0 20px}.landing-nav nav,.ghost-link{display:none}.landing-brand{font-size:21px}.hero-content{min-height:720px}.hero-copy{width:auto;padding:75px 24px 380px}.hero-copy h1{font-size:82px}.cn-title{font-size:20px}.hero-actions{gap:10px}.start-button,.demo-button{height:52px;padding:0 22px}.ring-system{right:50%;top:66%;width:480px;translate:50% -50%}.listener-silhouette{right:calc(50% - 70px);top:53%;width:140px;height:280px}.particle-field{right:0;top:37%;width:100%;height:52%}.wave-canvas{top:56%;height:22%}.explore-link{display:none}.feature-strip{grid-template-columns:1fr;padding:18px}.feature-strip a{min-height:78px}.nav-primary{min-width:94px}.hero-description{font-size:13px}}
@media(prefers-reduced-motion:reduce){.landing-page *{animation:none!important;scroll-behavior:auto!important}.ring-system,.particle-field,.listener-silhouette{transition:none!important}}
.demo-playing .ring-system{filter:brightness(1.14) drop-shadow(0 0 15px rgba(255,240,205,.5))!important}
.singer-parallax{position:absolute;z-index:7;right:calc(7vw + min(56vw,700px)/2 - 170px);top:21%;width:340px;height:500px;transition:transform 1s cubic-bezier(.2,.8,.2,1);filter:drop-shadow(0 24px 18px rgba(25,42,63,.2))}.anime-singer{width:100%;height:100%;object-fit:contain;transform-origin:50% 72%;animation:singer-groove 2.9s ease-in-out infinite}.demo-playing .anime-singer{animation-duration:2.55s}@keyframes singer-groove{0%,100%{transform:translateY(0) rotate(-.7deg)}50%{transform:translateY(-5px) rotate(.8deg)}}
.listener-silhouette{right:calc(7vw + min(56vw,700px)/2 - 80px);top:30%;width:160px;height:420px;fill:url(#silhouetteGradient);filter:drop-shadow(0 22px 14px rgba(16,24,32,.2))}.person-body{transform-origin:90px 245px}.headphones{stroke:#596571}.neck{opacity:.96}.torso{opacity:.98}.coat-tail{opacity:.94}
@media(max-width:1100px){.listener-silhouette{right:calc(-2vw + min(56vw,700px)/2 - 80px)}}
@media(max-width:760px){.listener-silhouette{right:calc(50% - 65px);top:50%;width:130px;height:340px}}
@media(max-width:1100px){.singer-parallax{right:calc(-2vw + min(56vw,700px)/2 - 160px);width:320px}}
@media(max-width:760px){.singer-parallax{right:calc(50% - 135px);top:49%;width:270px;height:360px}}

/* 品牌节拍与主视觉播放态 */
.brand-wave{height:32px;padding:0 5px}.brand-wave i{background:linear-gradient(180deg,#2d8fee,#2fc5cc 58%,#ff8fa4);transform-origin:center;animation:brand-equalizer 1.12s ease-in-out infinite}.brand-wave i:nth-child(1),.brand-wave i:nth-child(7){animation-delay:-.15s}.brand-wave i:nth-child(2),.brand-wave i:nth-child(6){animation-delay:-.45s}.brand-wave i:nth-child(3),.brand-wave i:nth-child(5){animation-delay:-.7s}.brand-wave i:nth-child(4){animation-delay:-.3s}.wave-canvas{opacity:1;filter:drop-shadow(0 0 7px rgba(39,165,219,.25))}.singer-parallax{right:calc(7vw + min(56vw,700px)/2 - 113px);top:30%;width:226px;height:334px}.demo-playing .brand-wave i{animation-duration:.72s}@keyframes brand-equalizer{0%,100%{transform:scaleY(.46);opacity:.64}45%{transform:scaleY(1.08);opacity:1}70%{transform:scaleY(.72);opacity:.86}}
@media(max-width:1100px){.singer-parallax{right:calc(-2vw + min(56vw,700px)/2 - 106px);width:212px;height:320px}}
@media(max-width:760px){.singer-parallax{right:calc(50% - 90px);top:56%;width:180px;height:240px}}
</style>
