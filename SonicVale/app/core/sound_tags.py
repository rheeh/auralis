"""Small shared vocabulary for script-time tagging and deterministic sound retrieval."""
import re

SOURCES = {
    '抽屉':['抽屉','drawer'], '拉链':['拉链','zipper'], '火柴':['火柴','matchstick'],
    '微波炉':['微波炉','microwave'], '马桶':['马桶','toilet'], '水龙头':['水龙头','tap water'],
    '井盖':['井盖','manhole'], '吱呀':['吱呀','吱嘎','creak'],
    '雨声':['雨','rain'], '雷声':['雷','thunder'], '风声':['风','wind','气流','air'],
    '脚步':['脚步','走路','步行','footstep','步声'], '敲门':['敲门','叩门','knock'],
    '门铃':['门铃','doorbell'], '开关门':['推门','开门','关门','门开合','door','拉门'],
    '纸张':['纸','信封','翻书','书页','paper','book','翻页'], '钥匙':['钥匙','key jiggle','keys'],
    '锁具':['门锁','上锁','解锁','unlock','lock'], '键盘':['键盘','打字','keyboard','typing'],
    '电话铃':['电话铃','手机铃','来电铃','telephone','ringtone'], '振动':['振动','震动','vibrat'],
    '提示音':['提示音','电子音','beep','notification'], '警报':['警报','警笛','alarm','siren'],
    '钟表':['钟表','时钟','钟摆','秒针','clock','滴答'], '铃铛':['铃铛','铃声','bell'],
    '水声':['水','water','splash','波浪','海浪'], '火焰':['火焰','火堆','燃烧','fire','柴火'],
    '鸟鸣':['鸟','bird','chirp'], '虫鸣':['虫鸣','蟋蟀','蝉','cricket','insect'],
    '狗叫':['狗','犬','dog'], '猫叫':['猫','meow','cat'], '人群':['人群','交谈声','crowd','欢呼'],
    '交通':['交通','车流','公路','街道','traffic','highway'], '引擎':['引擎','发动机','engine'],
    '喇叭':['喇叭','horn'], '刹车':['刹车','brake','skid'], '机械':['机械','机器','machine'],
    '施工':['施工','工地','construction'], '玻璃':['玻璃','glass','瓶碎'],
    '碰撞':['撞击','碰撞','重击','hit','impact','砸','拍击'], '金属':['金属','metal','铁'],
    '木材':['木材','木块','wood'], '石块':['石块','石头','stone'],
    '开关':['开关','switch'], '衣物':['衣物','衣服','布料','cloth','拉链'],
    '心跳':['心跳','heartbeat'], '呼吸':['呼吸','喘息','breath','叹息'],
    '笑声':['笑声','轻笑','大笑','哄笑','哈哈','laughter','laugh','chuckle','giggle'],
    '枪声':['枪声','枪响','gunshot'], '爆炸':['爆炸','explosion'],
    '配乐':['配乐','音乐','bgm','music'], '环境底噪':['底噪','室内环境','room-tone','ambient'],
}
QUALIFIERS = {
    '一慢两快':['一慢两快'], '木质':['木质','木门','wooden'],
    '室内':['室内','房间','教室','公寓','indoor'], '室外':['室外','户外','outdoor'],
    '木地板':['木地板','木质地板','木板脚步','footstep_wood'], '湿地':['湿地','积水','wet'],
    '石地':['石地','水泥地','石板','gravel'], '远处':['远处','远方','distant'],
    '近处':['近处','近距离','close'], '循环':['循环','持续','loop'],
    '单次':['单次','一下','single'], '快速':['快速','急促','fast'], '缓慢':['缓慢','慢速','slow'],
    '悬疑':['悬疑','紧张','诡异','suspense'], '自然':['自然','森林','forest'],
}
VOCABULARY = {**SOURCES, **QUALIFIERS}

def normalize_tags(values):
    if isinstance(values,str): values=re.split(r'[,，、;；\s]+',values)
    result=[]
    for raw in values or []:
        word=str(raw).strip().lower()[:40]
        if not word: continue
        canonical=next((tag for tag,aliases in VOCABULARY.items() if word==tag or word in aliases),word)
        if canonical not in result: result.append(canonical)
    return result[:12]

def infer_tags(text):
    text=str(text or '').lower()
    # Do not turn explicit absence of a sound into a request for that sound.
    text=re.sub(r'(?:没有|不含|无|不要|无需|停止)[^，。；;\n]{0,20}', '', text)
    tags=[tag for tag,aliases in VOCABULARY.items() if tag in text or any(
        (re.search(r'(?<![a-z])'+re.escape(alias)+r'(?![a-z])',text) if alias.isascii() else alias in text)
        for alias in aliases)]
    if re.search(r'(?:门外|木门|房门|门板).{0,10}[敲叩]|[敲叩].{0,5}门', text) and '敲门' not in tags:
        tags.insert(0, '敲门')
    # More specific sources should not imply generic alternatives.
    if '敲门' in tags or '门铃' in tags:
        tags=[t for t in tags if t!='开关门']
    if '门铃' in tags or '电话铃' in tags: tags=[t for t in tags if t!='铃铛']
    if '施工' in tags: tags=[t for t in tags if t!='机械']
    return tags[:12]

def script_sound_tags(tags,text):
    return normalize_tags(tags) or infer_tags(text)

def rank_assets(assets,tags,limit=8):
    wanted=normalize_tags(tags)
    core=set(wanted)-set(QUALIFIERS)
    ranked=[]
    for asset in assets:
        available=set(normalize_tags(asset.get('tags')))
        matched=[t for t in wanted if t in available]
        if not matched or (core and not core.intersection(matched)): continue
        score=sum(3 if t in core else 1 for t in matched)
        ranked.append({**asset,'matched_tags':matched,'missing_tags':[t for t in wanted if t not in available],'score':score})
    ranked.sort(key=lambda a:(-a['score'],len(a['missing_tags']),a['name'],a['id']))
    return ranked[:limit]

def tagging_instruction():
    return '【素材检索标签】解析台本时为每条 sfx/bgm 同时生成 soundTags 数组（2–6个简短标签），包含真实声源、动作/材质和空间，不用整句。优先使用：'+ '、'.join(VOCABULARY)+'。特殊需求可加简短新标签，不得为了匹配库而改写剧情；没有声音不要虚构。对白没有音效时 soundTags=[]。'
