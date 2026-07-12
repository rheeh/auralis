# 根据小说内容生成

import textwrap


def get_audio_drama_adaptation_rules() -> str:
    """小说转广播剧的共享声音优先规范，供新旧三条生成链路复用。"""
    return textwrap.dedent(
        """
        【广播剧改编总则：声音先行，不是朗读小说】
        本总则是最高优先级；如果后续项目自定义提示词要求“全文保留”或“所有非台词都变成旁白”，以本总则为准。
        1. 先逐句判断原文功能，只能归入：对话、动作、环境、心理、背景信息、转场、视觉描写。
        2. 再决定声音策略：
           - 对话：保留角色意图，允许口语化、打断、停顿和潜台词；不要让角色生硬地讲解双方都知道的信息。
           - 动作：优先用动作音效、人物呼吸/反应或一句自然对白呈现；能听见就不要旁白解释。
           - 环境：只保留能建立空间、危险或情绪的关键环境声，其余删除。
           - 心理：优先转成角色选择、犹豫、言外之意或声音表演；不要连续朗读内心独白。
           - 背景信息：拆入冲突和行动中的自然对白；无法自然转化且不影响理解时删除。
           - 转场：优先用代表性声音、音乐桥或静默完成。
           - 视觉描写：没有剧情功能的直接删除；有剧情功能的改成可听见的证据或角色反应。
        3. 按以下顺序删旁白：视觉无效信息 → 环境描写 → 动作描写 → 转场 → 背景信息 → 心理描写。
        4. 只有三种情况允许保留旁白：
           - 无法用声音或台词替代，删掉会让听众无法理解的必要信息；
           - 作者核心金句或有独立听觉价值的文学性比喻；
           - 视角发生大幅跳转，需要一句极短提示。
        5. 每条旁白只承担一个信息点，通常不超过45个汉字；不得连续出现两条旁白。旁白与人物可朗读文本的字数占比目标不超过15%。
        6. 每场必须以可听见的声音锚点进入，用对白、动作声和人物反应推进冲突，以声音、音乐或短暂停顿完成转折/离场。
        7. dialogue/narration 的朗读文本必须是可直接送入 TTS 的纯文本，严禁出现 ()、（）、[]、【】以及括号内的音效、停顿、情绪或表演提示。停顿、重音、语速和语气放入 productionNote；音效、环境音、BGM、混响和静音放入 audioEvents。
        8. 保留剧情因果、人物动机和关键事实，不要求逐字保留小说叙述。输出前自检：删掉旁白后场景是否仍能听懂；若能，就删掉该旁白。
        """
    ).strip()


def get_context2lines_prompt(possible_characters, novel_content,possible_emotions,possible_strengths) -> str:

    prompt = f"""
你的任务是把给定小说内容改编成以人物对话为主的广播剧可朗读台词，并输出包含<result>标签的结构化JSON结果。

{get_audio_drama_adaptation_rules()}

划分规则：

台词识别:
识别所有角色说话的内容，包括带引号、破折号、叹号等常见台词标记的文本。
如果角色在给定角色列表中，使用该角色名；
如果角色未在列表中出现，根据上下文合理归纳角色名。
重要规则：相邻台词之间如果角色相同，可以适当合并，但是一段内容最多不超过150字。如果单段内容超过150字，请将内容拆分为多条。


旁白识别:
不能把所有非台词内容自动归为旁白。严格按照广播剧改编总则删减和声音化，仅保留三类获准旁白。
旁白应短促、单一信息点，通常不超过45个汉字；不得出现连续两条旁白。

情绪以及情绪强弱识别:
根据上下文场景，识别出每条台词所对应的情绪以及情绪强度。情绪和情绪强度的内容必须来自情绪列表possible_emotions和情绪强度列表possible_strengths。
旁白的情绪和情绪强度统一为一样的，统一为‘平静’情绪，强度为‘中等’。

特殊情况处理:
多角色对话连续出现时，每条台词对应正确角色。
混合旁白和台词的段落可拆分为旁白和台词两条记录。
避免重复；允许删除无听觉价值的小说叙述，但不得破坏剧情因果和人物动机。

输出格式:
输出严格遵循包含<result>标签的JSON数组形式

示例：
<result>
[
{"role_name": "张三", "text_content": "你到底在干什么！", "emotion_name": "生气", "strength_name": "强烈"},
{"role_name": "旁白", "text_content": "此时，张三愤怒站着", "emotion_name": "平静", "strength_name": "中等"},
{"role_name": "李四", "text_content": "这可不管我的事儿", "emotion_name": "害怕", "strength_name": "微弱"}
]
</result>

注意事项:
保持文本顺序与逻辑一致。
允许为广播剧表演节奏口语化台词；旁白必须经过删减，不要求逐字保留小说叙述。
所有划分结果必须完整输出在 <result> 标签内。

输入内容：
可能包含的角色列表：
<possible_characters>
{possible_characters}
</possible_characters>

可能包含的情绪列表：
<possible_emotions>
{possible_emotions}
</possible_emotions>

可能包含的情绪强弱列表：
<possible_strengths>
{possible_strengths}
</possible_strengths>

小说原文：
<novel_content>
{novel_content}
</novel_content>


"""
    return textwrap.dedent(prompt)

def get_prompt_str():
    prompt = """
    你的任务是把给定小说内容改编为以对白和声音行动推进的广播剧台词，并输出为结构化JSON结果。

    {audio_drama_rules}

    台词识别规则：
    1. 保留剧情因果、人物动机、关键事实和有表现力的原文对白；允许口语化并删除无听觉价值的叙述。
    2. 识别带引号（“”）、破折号（——）、感叹号（！）、冒号（：）等标记的角色对话；其余内容先分类和声音化，不能直接归为旁白。
    3. 若角色在已知角色列表<possible_characters>中，则直接使用该角色名；若不在列表中，则根据上下文合理判断角色身份。
    4. 相邻台词如属同一角色，可合并为一条，但单条台词长度不得超过150字。
    5. 若单条台词超过150字，需按语义和表演节奏拆分，避免大段说明性发言。
    
    旁白识别规则：
    1. 不得把所有非台词叙述自动标记为旁白，必须先完成七类句子判断和声音替代。
    2. 严格按“视觉无效信息→环境→动作→转场→背景→心理”的顺序删旁白。
    3. 只保留无法声音化但影响理解的信息、核心文学金句、视角大幅跳转提示三类旁白。
    4. 旁白通常不超过45个汉字，不得连续出现，目标字数占比不超过人物可朗读文本的15%。
    
    情绪与情绪强度识别规则：
    1. 根据上下文语境、语气及场景变化，为每条台词识别情绪和情绪强度。
    2. 情绪与强度必须严格从提供的情绪列表（possible_emotions）与强度列表（possible_strengths）中选择。
    3. “旁白”内容的情绪与强度统一为：情绪“平静”，强度“中等”。
    4. 情绪识别不得影响或改写原文内容，仅用于标注。
    
    特殊情况处理：
    1. 多角色连续对话时，确保每条台词对应正确角色，避免角色错配。
    2. 当段落中混合出现旁白与台词时，应拆分为独立记录：旁白一条、台词一条。
    3. 输出不得重复剧情信息；同一信息已经由对白或声音表达时，不再用旁白复述。
    4. 输出前进行声音审计：如果删掉某条旁白仍能听懂，就删除它。
    
    输出格式:
    严格输出为 json数组。
    
    示例：
    小说原文：
    <novel_content>
    一名靠前的灰衣少年似乎与石台上的少年颇为熟悉，他听得大伙的窃窃私语，不由得得意一笑，压低声音道：“牧哥可是被选拔出来参加过“灵路”的人，我们整个北灵境中，可就牧哥一人有名额，你们应该也知道参加“灵路”的都是些什么变态吧？当年我们这北灵境可是因为此事沸腾了好一阵的，从那里出来的人，最后基本全部都是被“五大院”给预定了的。”
    </novel_content>
    输出：
    [
      {"role_name": "学员甲", "text_content": "牧哥真参加过灵路？咱们北灵境可就他一个！", "emotion_name": "惊讶", "strength_name": "较强"},
      {"role_name": "灰衣少年", "text_content": "当然。从灵路出来的人，五大院抢着要。", "emotion_name": "高兴", "strength_name": "中等"}
    ]
    
    
    输入内容：
    可能包含的角色列表：
    <possible_characters>
    {possible_characters}
    </possible_characters>
    
    可能包含的情绪列表：
    <possible_emotions>
    {possible_emotions}
    </possible_emotions>
    
    可能包含的情绪强弱列表：
    <possible_strengths>
    {possible_strengths}
    </possible_strengths>
    
    小说原文：
    <novel_content>
    {novel_content}
    </novel_content>

    """
    return textwrap.dedent(prompt).replace("{audio_drama_rules}", get_audio_drama_adaptation_rules())




def get_auto_fix_json_prompt(json_str: str) -> str:
    prompt = f"""
    你将收到一段可能出错的 JSON 字符串（它可能是 LLM 生成的结果），其中可能存在以下问题：
        多余或缺失的逗号
        缺少引号或多余引号
        键值格式错误
        JSON 外含无关说明文字
        非法转义符
    你的任务是：
    仅输出一个严格合法、可被 json.loads 解析的 JSON。
    保持原有数据结构和内容不变（除非必须修正格式）。
    不要在 JSON 外输出任何解释、额外文字或注释。
    输出必须完整输出在 <result> </result>标签内。
    输入内容：
    <json_str>
    {json_str}
    </json_str>w
    """
    return textwrap.dedent(prompt)


def get_add_smart_role_and_voice(original_text: str, role_name, voice_names):
    prompt = f"""
    你是“角色音色匹配助手”。你的任务是：根据小说原文中的角色表现，为每个在<role_name>中出现的角色匹配最符合其语气与性格的音色。

    原文内容：
    <original_text>
    {original_text}
    </original_text>

    角色列表信息：
    <role_name>
    {role_name}
    </role_name>

    音色列表信息：
    <voice>
    {voice_names}
    </voice>

    匹配规则（必须严格遵守）：
    1. 仅根据【原文内容】判断哪些角色实际出现；未在原文中出现的角色一律忽略，不输出。
    2. 对于每个实际出现的角色，根据原文中体现的性格特征、语气风格、情绪倾向、年龄感等信息，推断该角色适合的音色类型。
    3. 再根据音色库中每个音色的名称或描述，为角色挑选最匹配的音色。
    4. 每个角色必须使用不同音色，voice_name 不得重复；必须为输入角色列表中的每个角色输出一条匹配结果。
    5. 若原文线索不足，仍需结合角色身份和音色标签选择一个尚未使用的合理音色，不得省略角色。
    6. 不得臆造原文中不存在的角色特征或音色特征。
    7. 最终输出必须是一个标准 JSON 数组，且数组中的每个对象必须包含：
       - "role_name": 角色名
       - "voice_name": 匹配的音色名

    输出格式要求：
    - 严格输出 JSON 数组。
    - 不得输出任何解释说明、自然语言、注释或多余内容。

    示例输出（格式示例）：
    [
      {{ "role_name": "灰衣少年", "voice_name": "小王" }},
      {{ "role_name": "白衣少年", "voice_name": "小正" }}
    ]
    """

    return textwrap.dedent(prompt)


def get_subtitle_correction_prompt(original_text: str, subtitle_lines: list) -> str:
    """
    生成字幕矫正的prompt
    original_text: 原始正确文本
    subtitle_lines: ASR识别的字幕行列表，格式为 [{"index": 1, "text": "..."}]
    """
    subtitle_json = "\n".join([f'  {{"index": {item["index"]}, "text": "{item["text"]}"}}' for item in subtitle_lines])
    
    prompt = f"""
你是一个专业的字幕校对助手。你的任务是根据原文内容，修正ASR自动识别产生的字幕错误。

## 任务说明
ASR（自动语音识别）生成的字幕可能存在以下问题：
1. 同音字错误（如"他"与"她"、"的"与"得"）
2. 近音字错误
3. 词语分割错误
4. 标点符号错误或缺失

你需要参考原文，将每条字幕修正为正确的文本。

## 重要规则
1. 严格保持字幕条目数量不变（输入多少条，输出多少条）
2. 尽量保持每条字幕的长度相近，不要大幅改变字幕的切分位置
3. 仅修正错误，不要改写原意或增删内容
4. 如果某条字幕已经正确，原样保留
5. 输出格式必须是JSON数组

## 原文内容
<original_text>
{original_text}
</original_text>

## 待矫正的字幕
<subtitle_lines>
[
{subtitle_json}
]
</subtitle_lines>

## 输出格式
严格输出JSON数组，每个元素包含index和corrected_text字段：
<result>
[
  {{"index": 1, "corrected_text": "修正后的文本"}},
  {{"index": 2, "corrected_text": "修正后的文本"}}
]
</result>

请开始矫正：
"""
    return textwrap.dedent(prompt)
