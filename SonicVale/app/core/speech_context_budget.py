import json


def instruction_weight(text):
    # Conservative local size guard, not a claim about the vendor tokenizer.
    return sum(2 if '\u3400' <= char <= '\u9fff' else 1 for char in text)


def compile_context_instruction(base, context, budget=2000):
    prefix = '\n以下是理解用上下文，不能朗读或追加到正文；后文只用于接话，不能提前表现角色尚未知晓的事。\n'
    suffix = '\n沿用人物声线。本句明确要求和项目风格优先于默认表达。只合成本句正文。'
    render = lambda value: base + prefix + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + suffix
    if instruction_weight(render({})) > budget:
        raise ValueError('本句声音指导过长，请缩短具体要求后再生成；完整上下文不能与长指导同时送入当前模型。')
    selected, omitted = {}, []
    # Preserve the current intent before optional neighbouring or future text.
    priority = ('当前人物', '共同表演基调', '作品背景', '整场表演', '场景', '声线', '题材',
                '前文', '上次本人发言', '改编要求', '后文')
    for key in priority:
        value = context.get(key)
        if value in (None, '', [], {}):
            continue
        if key == '整场表演':
            for name, item in value.items():
                candidate = {**selected, key: {**selected.get(key, {}), name: item}}
                if instruction_weight(render(candidate)) <= budget:
                    selected = candidate
                else:
                    omitted.append(f'{key}.{name}')
        elif instruction_weight(render({**selected, key: value})) <= budget:
            selected[key] = value
        else:
            omitted.append(key)
    return render(selected), omitted
