const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process')
function discover(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(item=>{const file=path.join(dir,item.name);return item.isDirectory()?discover(file):/\.test\.(?:mjs|cjs|js)$/.test(file)?[file]:[]})}
const files=['src','tests'].flatMap(discover).sort()
if(!files.length)throw new Error('No tests discovered')
console.log(`Discovered ${files.length} test files`)
const result=spawnSync(process.execPath,['--experimental-default-type=module','--test',...files],{stdio:'inherit'})
process.exit(result.status??1)
