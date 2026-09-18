
const logger = require('./logger');
const { decodeText } = require('./logger');
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn, exec } = require('child_process')
const os = require('os')
const http = require('http')
const {isAuralisHealth}=require('./backend-health.cjs')
const INSTANCE_TOKEN = require('crypto').randomBytes(32).toString('hex')

const PROJECT_ROOT = path.resolve(__dirname, '..', '..')
const BACKEND_PORT = process.env.AURALIS_BACKEND_PORT || '8200'
const BACKEND_URL = process.env.AURALIS_BACKEND_URL || `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = process.env.AURALIS_FRONTEND_URL || 'http://127.0.0.1:5173'
let backendProcess = null
const selectedDestinations=new Set()
const selectedSources=new Set()

function requestUrl(url, timeout = 1000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, res => {
      let body=''
      res.on('data',chunk=>{body+=chunk;if(body.length>16384)req.destroy(new Error('Unexpected health response'))})
      res.on('end', () => {
        if(res.statusCode!==200)return reject(new Error('Service not ready'))
        if(new URL(url).pathname==='/health'){
          if(!isAuralisHealth(res.statusCode,body))return reject(new Error('Wrong backend identity or not ready'))
        }
        resolve(true)
      })
    })
    req.on('error', reject)
    req.setTimeout(timeout, () => {
      req.destroy(new Error(`timeout: ${url}`))
    })
  })
}

async function isUrlReady(url) {
  try {
    await requestUrl(url, 800)
    return true
  } catch {
    return false
  }
}

async function startBackend() {
  if (await isUrlReady(`${BACKEND_URL}/health`)) {
    console.log('检测到已运行后端，复用：', BACKEND_URL)
    return
  }

  const isDev = !app.isPackaged
  let command
  let args = []
  let cwd
  let env = process.env

  if (isDev) {
    const backendDir = path.join(PROJECT_ROOT, 'SonicVale')
    const pythonPath = process.platform === 'win32'
      ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
      : path.join(backendDir, '.venv', 'bin', 'python')

    if (!fs.existsSync(pythonPath)) {
      throw new Error(`未找到后端 Python 运行时：${pythonPath}，请先运行 ./scripts/dev.sh 或安装后端依赖。`)
    }

    command = pythonPath
    args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', BACKEND_PORT]
    cwd = backendDir
    env = {
      ...process.env,
      AURALIS_CONFIG_DIR: process.env.AURALIS_CONFIG_DIR || path.join(PROJECT_ROOT, '.local-data'),
      PYTHONPYCACHEPREFIX: process.env.PYTHONPYCACHEPREFIX || path.join(PROJECT_ROOT, '.pycache'),
    }
  } else {
    command = path.join(process.resourcesPath, 'app.asar.unpacked', 'electron', 'main.exe')
    args = []
    cwd = path.dirname(command)
    env = {
      ...process.env,
      AURALIS_STOCK_AUDIO_DIR: path.join(process.resourcesPath, 'assets', 'audio', 'cc0'),
    }
  }

  console.log('启动后端：', command, args.join(' '))

  backendProcess = spawn(command, args, {
    cwd,
    env: {...env,AURALIS_INSTANCE_TOKEN:INSTANCE_TOKEN},
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  // 日志输出（可选）
  backendProcess.stdout.on('data', data => {
    console.log(`[后端] ${decodeText(data)}`);
  });

  backendProcess.stderr.on('data', data => {
    console.error(`[后端错误] ${decodeText(data)}`);
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`后端退出，code=${code}, signal=${signal}`);
  });
}

async function waitForUrlReady(url, retries = 60, delay = 500) {
  for(let attempt=0;attempt<retries;attempt++) {
    try{return await requestUrl(url)}
    catch(error){if(attempt===retries-1)throw error;await new Promise(resolve=>setTimeout(resolve,delay))}
  }
}

function waitForBackendReady(retries = 60, delay = 500) {
  return waitForUrlReady(`${BACKEND_URL}/health`, retries, delay)
}

function waitForFrontendReady(retries = 60, delay = 500) {
  return waitForUrlReady(FRONTEND_URL, retries, delay)
}

function createWindow() {
  const win = new BrowserWindow({

    width: 1360,
    height: 765,
    show: false, // ✅ 先不显示，等最大化后再显示
    icon: path.join(__dirname, '../resource/icon/yingu.ico'),

    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      additionalArguments: [`--auralis-api=${encodeURIComponent(BACKEND_URL)}`,`--auralis-token=${INSTANCE_TOKEN}`,`--auralis-home=${encodeURIComponent(os.homedir())}`],
    },
    autoHideMenuBar: true, // 这会让菜单栏自动隐藏，但通过 Alt 可以唤出

  })

  win.webContents.setWindowOpenHandler(()=>({action:'deny'}))
  win.webContents.on('will-navigate',(event,url)=>{if(url!==win.webContents.getURL())event.preventDefault()})
  win.once('ready-to-show', () => {
    win.maximize() // ✅ 启动时自动最大化（不是全屏）
    win.show()     // ✅ 再显示窗口
  })
  const isDev = !app.isPackaged
  if (isDev) {
    // 开发环境：直连 Vite
    win.loadURL(FRONTEND_URL)
    // win.webContents.openDevTools({ mode: 'detach' })
  } else {
    // 生产环境：直接加载打包后的静态文件，不阻塞首屏
    win.loadFile(path.join(__dirname, '../dist/index.html'))

    // 非阻塞地检测后端是否就绪，用于日志/提示
    waitForBackendReady()
      .then(() => console.log('后端就绪'))
      .catch(e => {
        console.error('后端未就绪:', e)
        win.loadURL('data:text/html;charset=utf-8,<h1 style="font-family:sans-serif">Backend is not ready</h1><p>Please restart Auralis.</p>')
      })
  }
}

// ============== 事件入口 ===============

app.whenReady().then(async () => {
  try {
    await startBackend()
    await waitForBackendReady()
    if (!app.isPackaged) {
      await waitForFrontendReady()
    }
    createWindow()
  } catch (err) {
    console.error('后端启动失败:', err)
    const errorWin = new BrowserWindow({ width: 600, height: 300 })
    errorWin.loadURL(`data:text/html;charset=utf-8,
  <!DOCTYPE html>
  <html>
    <head><meta charset="UTF-8"></head>
    <body>
      <h2 style="font-family:sans-serif">后端启动失败</h2>
      <p>请检查后端程序并重启应用</p>
    </body>
  </html>
`);
  }
})

// 杀死后端
function killBackendTree(child) {
  if (!child || !child.pid) return
  const pid = child.pid

  if (process.platform === 'win32') {
    exec(`taskkill /PID ${pid} /T /F`, (err) => {
      if (err) console.warn('taskkill 失败：', err.message)
    })
  } else {
    try {
      // 先温柔地
      process.kill(pid, 'SIGTERM')
      // 兜底：0.8s 后还活着就强杀整个进程组
      setTimeout(() => {
        try { process.kill(-pid, 'SIGKILL') } catch { }
        try { process.kill(pid, 'SIGKILL') } catch { }
      }, 800)
    } catch (e) {
      // 可能已退出
    }
  }

}
function shutdown() {
  killBackendTree(backendProcess)
}
app.on('before-quit', shutdown)
app.on('will-quit', shutdown)
app.on('quit', shutdown)

app.on('window-all-closed', () => {
  shutdown()
  if (process.platform !== 'darwin') app.quit()
})

// 处理 Ctrl+C / 任务管理器结束 等
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
process.on('exit', shutdown)


// ============== IPC 处理 ===============
function handleNative(channel,handler) {
  ipcMain.handle(channel,(event,...args)=>{
    const frame=event.senderFrame
    const expected=app.isPackaged?require('url').pathToFileURL(path.join(__dirname,'../dist/index.html')).href:FRONTEND_URL
    if(!frame||frame!==event.sender.mainFrame||frame.url.split('#')[0].replace(/\/$/,'')!==expected.replace(/\/$/,''))throw new Error('Untrusted IPC sender')
    return handler(event,...args)
  })
}

// 选择参考音频
handleNative('dialog:pick-audio', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: '选择参考音频',
    properties: ['openFile'],
    filters: [
      { name: 'Audio', extensions: ['mp3', 'wav', 'm4a', 'ogg', 'flac'] }
    ]
  })

  if (canceled || !filePaths || !filePaths[0]) return null
  selectedSources.add(path.resolve(filePaths[0]))
  return filePaths[0] // 返回绝对路径
})

// 打开文件夹
handleNative('dialog:open-folder', async (event, folderPath) => {
  if (typeof folderPath!=='string'||!path.isAbsolute(folderPath)||!fs.statSync(folderPath).isDirectory())throw new Error('请选择有效的本地文件夹')

  try {
    await shell.openPath(folderPath)
    return true
  } catch (e) {
    console.error('打开文件夹失败', e)
    return false
  }
})

//选择音色文件夹
handleNative('select-voice-folder', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null

  const rootPath = result.filePaths[0]
  const folders = fs.readdirSync(rootPath, { withFileTypes: true }).filter(dirent => dirent.isDirectory())

  const resultList = []

  for (const folder of folders) {
    const emotion = folder.name
    const emotionPath = path.join(rootPath, emotion)
    const files = fs.readdirSync(emotionPath)

    for (const file of files) {
      const strength = path.parse(file).name
      const reference_path = path.join(emotionPath, file)

      resultList.push({
        voice_name: path.basename(rootPath),
        emotion_name: emotion,
        strength_name: strength,
        reference_path
      })
    }
  }

  return resultList
})


// ✅ 选择文件夹：返回选中的绝对路径
handleNative('dialog:selectDir', async () => {
  const result = await dialog.showOpenDialog({
    title: '选择项目根路径',
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled || !result.filePaths || !result.filePaths.length) return null
  return result.filePaths[0]
})

// 保存文件对话框
handleNative('dialog:save-file', async (event, options) => {
  const { title, defaultPath, filters } = options || {}
  const result = await dialog.showSaveDialog({
    title: title || '保存文件',
    defaultPath: defaultPath || '',
    filters: filters || [{ name: '所有文件', extensions: ['*'] }]
  })
  if (result.canceled || !result.filePath) return null
  selectedDestinations.add(path.resolve(result.filePath))
  return result.filePath
})

// 选择文件对话框
handleNative('dialog:pick-file', async (event, options) => {
  const { title, filters } = options || {}
  const result = await dialog.showOpenDialog({
    title: title || '选择文件',
    properties: ['openFile'],
    filters: filters || [{ name: '所有文件', extensions: ['*'] }]
  })
  if (result.canceled || !result.filePaths || !result.filePaths.length) return null
  selectedSources.add(path.resolve(result.filePaths[0]))
  return result.filePaths[0]
})

// 选择目录对话框
handleNative('dialog:pick-directory', async (event, options) => {
  const { title } = options || {}
  const result = await dialog.showOpenDialog({
    title: title || '选择目录',
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled || !result.filePaths || !result.filePaths.length) return null
  return result.filePaths[0]
})

// 写入文件（用于音频下载等）
handleNative('fs:write-file', async (event, { filePath, data }) => {
  try {
    // data 是 Uint8Array 转成的普通数组，需要转回 Buffer
    if(typeof filePath!=='string'||!selectedDestinations.has(path.resolve(filePath)))throw new Error('请先通过保存对话框选择目标文件')
    if(!Array.isArray(data)||data.length>200*1024*1024||data.some(value=>!Number.isInteger(value)||value<0||value>255))throw new Error('文件数据无效或超过限制')
    const buffer = Buffer.from(data)
    fs.writeFileSync(filePath, buffer)
    selectedDestinations.delete(path.resolve(filePath))
    return { success: true }
  } catch (error) {
    console.error('写入文件失败:', error)
    return { success: false, error: error.message }
  }
})

// 复制文件（用于音频下载等）
handleNative('fs:copy-file', async (event, { sourcePath, destPath }) => {
  try {
    if(typeof sourcePath!=='string'||typeof destPath!=='string'||!selectedDestinations.has(path.resolve(destPath)))throw new Error('请先选择保存目标')
    if(!selectedSources.has(path.resolve(sourcePath))||!fs.statSync(sourcePath).isFile()||fs.statSync(sourcePath).size>200*1024*1024)throw new Error('源文件无效')
    fs.copyFileSync(sourcePath, destPath)
    selectedDestinations.delete(path.resolve(destPath))
    return { success: true }
  } catch (error) {
    console.error('复制文件失败:', error)
    return { success: false, error: error.message }
  }
})
