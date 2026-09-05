from __future__ import annotations
import json
import os
import shutil
import tempfile
import zipfile
from typing import List, Tuple

from sqlalchemy import Sequence

from app.core.config import getConfigPath
from app.core.audio_engin import AudioProcessor
from app.core.tts_engine import ConfigurableCloudTTSEngine, EdgeTTSEngine
from app.dto.voice_dto import VoiceAudioProcessDTO
from app.entity.voice_entity import VoiceEntity
from app.models.po import VoicePO
from app.repositories.multi_emotion_voice_repository import MultiEmotionVoiceRepository
from app.repositories.voice_repository import VoiceRepository


class VoiceService:

    COMMON_COSYVOICE_V1_PRESETS = [
        {"name": "青年女声·龙婉", "voice": "longwan", "tags": ["预置", "CosyVoice-v1", "女", "青年", "自然"], "sample": "我已经把线索整理好了，我们从第一句话重新听。"},
        {"name": "青年男声·龙橙", "voice": "longcheng", "tags": ["预置", "CosyVoice-v1", "男", "青年", "清爽"], "sample": "别担心，我会在天亮之前找到答案。"},
        {"name": "活泼女声·龙华", "voice": "longhua", "tags": ["预置", "CosyVoice-v1", "女", "青年", "活泼"], "sample": "快一点，他们马上就要追上来了！"},
        {"name": "知性女声·龙小淳", "voice": "longxiaochun", "tags": ["预置", "CosyVoice-v1", "女", "成年", "知性"], "sample": "有些真相，需要安静下来才能听见。"},
        {"name": "沉稳女声·龙小夏", "voice": "longxiaoxia", "tags": ["预置", "CosyVoice-v1", "女", "成年", "沉稳"], "sample": "现在不要回头，按我们约定的路线离开。"},
        {"name": "磁性男声·龙小诚", "voice": "longxiaocheng", "tags": ["预置", "CosyVoice-v1", "男", "成年", "磁性"], "sample": "这扇门后面，藏着他不愿提起的过去。"},
        {"name": "有声书女声·龙小白", "voice": "longxiaobai", "tags": ["预置", "CosyVoice-v1", "女", "成年", "旁白"], "sample": "雨落在旧城的屋檐上，故事也从这一夜开始。"},
        {"name": "东北男声·龙老铁", "voice": "longlaotie", "tags": ["预置", "CosyVoice-v1", "男", "成年", "东北口音"], "sample": "这事儿可没你想得那么简单，先听我说完。"},
        {"name": "新闻男声·龙书", "voice": "longshu", "tags": ["预置", "CosyVoice-v1", "男", "成年", "稳重", "旁白"], "sample": "凌晨两点，城市北区发生了一起离奇失踪案。"},
        {"name": "干练男声·龙硕", "voice": "longshuo", "tags": ["预置", "CosyVoice-v1", "男", "成年", "干练"], "sample": "时间不多了，所有人立刻检查装备。"},
        {"name": "播音女声·龙婧", "voice": "longjing", "tags": ["预置", "CosyVoice-v1", "女", "成年", "播音"], "sample": "欢迎收听今晚的特别节目，消失的第七码头。"},
        {"name": "故事女声·龙妙", "voice": "longmiao", "tags": ["预置", "CosyVoice-v1", "女", "成年", "有声书"], "sample": "她推开窗，发现雪地里多了一串陌生脚印。"},
        {"name": "温暖女声·龙悦", "voice": "longyue", "tags": ["预置", "CosyVoice-v1", "女", "成年", "温暖"], "sample": "没关系，你可以慢慢说，我一直都在听。"},
        {"name": "治愈女声·龙媛", "voice": "longyuan", "tags": ["预置", "CosyVoice-v1", "女", "成年", "治愈"], "sample": "等春天来的时候，我们再一起回到这里。"},
        {"name": "热血男声·龙飞", "voice": "longfei", "tags": ["预置", "CosyVoice-v1", "男", "青年", "热血"], "sample": "只要还有一个人没有撤离，我就不会离开！"},
        {"name": "成熟男声·龙祥", "voice": "longxiang", "tags": ["预置", "CosyVoice-v1", "男", "中年", "成熟"], "sample": "二十年前的账，今天也该有个了结了。"},
    ]

    COMMON_COSYVOICE_V3_INSTRUCT_PRESETS = [
        {"name": "阳光男声·龙安洋", "voice": "longanyang", "tags": ["预置", "CosyVoice-v3", "男", "青年", "Instruct"], "sample": "别急，我们把刚才发生的事从头梳理一遍。", "instruction": "你说话的情感是neutral。"},
        {"name": "元气女声·龙安欢", "voice": "longanhuan", "tags": ["预置", "CosyVoice-v3", "女", "青年", "Instruct"], "sample": "快看，我就知道这条线索一定有用！", "instruction": "你说话的情感是happy。"},
        {"name": "故事女童·龙呼呼", "voice": "longhuhu_v3", "tags": ["预置", "CosyVoice-v3", "女", "儿童", "Instruct"], "sample": "姐姐，你有没有听见阁楼上传来的声音？", "instruction": "你说话的情感是fearful。"},
    ]

    # These adult voices complement the three emotion-controlled presets. They
    # accept base prosody controls only; never label them as Instruct voices.
    SUSPENSE_COSYVOICE_V3_PRESETS = [
        {"name": "理智男声·龙天", "voice": "longtian_v3", "tags": ["预置", "CosyVoice-v3", "男", "成年", "基础韵律", "都市对白"], "sample": "别出声。离门远一点。", "instruction": "低声、克制，语速稍慢。"},
        {"name": "细腻女声·龙婉君", "voice": "longwanjun_v3", "tags": ["预置", "CosyVoice-v3", "女", "成年", "基础韵律", "都市对白"], "sample": "你不是说，那个号码三年前就停了吗？", "instruction": "轻声，克制。"},
        {"name": "质感旁白·龙三叔", "voice": "longsanshu_v3", "tags": ["预置", "CosyVoice-v3", "男", "成年", "基础韵律", "旁白"], "sample": "晚上十一点十七分，林澈的公寓。", "instruction": "语速稍慢，低声讲述。"},
    ]

    COMMON_EDGE_VOICE_PRESETS = [
        {
            "name": "旁白-温柔女声",
            "edge_voice": "zh-CN-XiaoxiaoNeural",
            "tags": ["预设", "Edge-TTS", "女", "旁白", "温柔"],
            "sample": "夜色落在城市边缘，风穿过旧巷，把故事轻轻推向下一幕。",
        },
        {
            "name": "旁白-稳重男声",
            "edge_voice": "zh-CN-YunyangNeural",
            "tags": ["预设", "Edge-TTS", "男", "旁白", "稳重"],
            "sample": "他站在雨后的天台上，终于意识到，所有线索都指向同一个答案。",
        },
        {
            "name": "青年男主",
            "edge_voice": "zh-CN-YunjianNeural",
            "tags": ["预设", "Edge-TTS", "男", "青年", "主角"],
            "sample": "别怕，我既然答应过你，就一定会把这件事查到底。",
        },
        {
            "name": "少年男声",
            "edge_voice": "zh-CN-YunxiNeural",
            "tags": ["预设", "Edge-TTS", "男", "少年", "活泼"],
            "sample": "等等我，我刚才真的看见那扇门自己打开了。",
        },
        {
            "name": "儿童男声",
            "edge_voice": "zh-CN-YunxiaNeural",
            "tags": ["预设", "Edge-TTS", "男", "儿童", "清亮"],
            "sample": "姐姐，你听，窗外好像有人在叫我们的名字。",
        },
        {
            "name": "青年女主",
            "edge_voice": "zh-CN-XiaoyiNeural",
            "tags": ["预设", "Edge-TTS", "女", "青年", "主角"],
            "sample": "我不是害怕真相，我只是想知道，他为什么要骗我。",
        },
        {
            "name": "成熟女声",
            "edge_voice": "zh-CN-XiaoxuanNeural",
            "tags": ["预设", "Edge-TTS", "女", "成熟", "冷静"],
            "sample": "现在不是争论的时候，先把录音备份，然后离开这里。",
        },
        {
            "name": "冷淡女声",
            "edge_voice": "zh-CN-liaoning-XiaobeiNeural",
            "tags": ["预设", "Edge-TTS", "女", "冷淡", "配角", "东北普通话"],
            "sample": "你问得太晚了，答案早就在你面前，只是你一直不肯看。",
        },
        {
            "name": "情绪女声",
            "edge_voice": "zh-CN-shaanxi-XiaoniNeural",
            "tags": ["预设", "Edge-TTS", "女", "情绪", "关键对白", "陕西普通话"],
            "sample": "如果这就是你想要的结局，那我宁愿从来没有相信过你。",
        },
        {
            "name": "儿童女声",
            "edge_voice": "zh-CN-XiaoxiaoNeural",
            "tags": ["预设", "Edge-TTS", "女", "儿童", "清亮"],
            "sample": "妈妈说，不能一个人走进那片树林，可我听见小猫在里面哭。",
        },
    ]

    def __init__(self, repository: VoiceRepository,multi_emotion_voice_repository: MultiEmotionVoiceRepository):
        """注入 repository"""
        self.repository = repository
        self.multi_emotion_voice_repository = multi_emotion_voice_repository

    def create_voice(self,  entity: VoiceEntity):
        """创建新音色
        - 检查同名音色是否存在
        - 如果存在，抛出异常或返回错误
        - 调用 repository.create 插入数据库
        """

        voice = self.repository.get_by_name(entity.name, entity.tts_provider_id)
        if voice:
            return None
        # 手动将entity转化为po
        po = VoicePO(**entity.__dict__)
        res = self.repository.create(po)

        # res(po) --> entity
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        entity = VoiceEntity(**data)

        # 将po转化为entity
        return entity


    def get_voice(self, voice_id: int) -> VoiceEntity | None:
        """根据 ID 查询音色"""
        po = self.repository.get_by_id(voice_id)
        if not po:
            return None
        data = {k: v for k, v in po.__dict__.items() if not k.startswith("_")}
        res = VoiceEntity(**data)
        return res

    def get_all_voices(self,tts_provider_id: int) -> Sequence[VoiceEntity]:
        """获取所有音色列表"""
        pos = self.repository.get_all(tts_provider_id)
        # pos -> entities

        entities = [
            VoiceEntity(**{k: v for k, v in po.__dict__.items() if not k.startswith("_")})
            for po in pos
        ]
        return entities

    def update_voice(self, voice_id: int, data:dict) -> bool:
        """更新音色
        - 可以只更新部分字段
        - 检查同名冲突
        - 检查project_id不能改变
        """
        name = data["name"]
        tts_provider_id = data["tts_provider_id"]
        if self.repository.get_by_name(name, tts_provider_id) and self.repository.get_by_name(name,tts_provider_id).id != voice_id:
            return False
        po = self.repository.get_by_id(voice_id)
        # 防止改变project_id
        if po.tts_provider_id != tts_provider_id:
            return False
        self.repository.update(voice_id, data)
        return True

    def delete_voice(self, voice_id: int) -> bool:
        """删除音色,需要保证事务
        """

        res = self.repository.delete(voice_id)
        self.multi_emotion_voice_repository.delete_multi_emotion_voice_by_voice_id(voice_id)
        return res

    def export_voices(self, tts_provider_id: int, export_path: str, ids: List[int] | None = None) -> str:
        """导出音色库到zip文件
        - 获取所有音色
        - 将音色信息和对应的音频文件打包到zip
        - 返回zip文件路径
        """
        if ids is None:
            voices = self.get_all_voices(tts_provider_id)
        else:
            pos = self.repository.get_by_ids(tts_provider_id, ids)
            voices = [
                VoiceEntity(**{k: v for k, v in po.__dict__.items() if not k.startswith("_")})
                for po in pos
            ]
        if not voices:
            return None

        # 确保导出目录存在
        os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else ".", exist_ok=True)

        # 创建zip文件
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 准备音色元数据
            voices_metadata = []
            
            for voice in voices:
                voice_data = {
                    "name": voice.name,
                    "description": voice.description,
                    "is_multi_emotion": voice.is_multi_emotion,
                    "reference_file": None
                }
                
                # 如果有参考音频文件，添加到zip
                if voice.reference_path and os.path.exists(voice.reference_path):
                    # 保持原文件名
                    file_name = os.path.basename(voice.reference_path)
                    # 使用音色名称作为子目录，避免文件名冲突
                    archive_path = f"voices/{voice.name}/{file_name}"
                    zipf.write(voice.reference_path, archive_path)
                    voice_data["reference_file"] = archive_path
                
                voices_metadata.append(voice_data)
            
            # 写入元数据文件
            metadata_json = json.dumps(voices_metadata, ensure_ascii=False, indent=2)
            zipf.writestr("voices_metadata.json", metadata_json)
        
        return export_path

    def import_voices(self, tts_provider_id: int, zip_path: str, target_dir: str) -> Tuple[int, int, List[str]]:
        """从zip文件导入音色库
        - 解压zip文件
        - 将音频文件复制到指定目录
        - 添加音色到数据库（跳过重名的）
        - 返回: (成功数量, 跳过数量, 跳过的音色名称列表)
        """
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"zip文件不存在: {zip_path}")
        
        # 确保目标目录存在
        os.makedirs(target_dir, exist_ok=True)
        
        success_count = 0
        skipped_count = 0
        skipped_names = []
        
        # 创建临时目录解压
        with tempfile.TemporaryDirectory() as temp_dir:
            # 解压zip文件
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # 读取元数据
            metadata_path = os.path.join(temp_dir, "voices_metadata.json")
            if not os.path.exists(metadata_path):
                raise ValueError("无效的音色库文件：缺少voices_metadata.json")
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                voices_metadata = json.load(f)
            
            for voice_data in voices_metadata:
                voice_name = voice_data["name"]
                
                # 检查是否已存在同名音色
                existing = self.repository.get_by_name(voice_name, tts_provider_id)
                if existing:
                    skipped_count += 1
                    skipped_names.append(voice_name)
                    continue
                
                reference_path = None
                
                # 如果有参考音频文件，复制到目标目录
                if voice_data.get("reference_file"):
                    source_file = os.path.join(temp_dir, voice_data["reference_file"])
                    if os.path.exists(source_file):
                        # 使用音色名称作为文件名，保留原扩展名
                        file_ext = os.path.splitext(source_file)[1]
                        file_name = f"{voice_name}{file_ext}"
                        dest_file = os.path.join(target_dir, file_name)
                        shutil.copy2(source_file, dest_file)
                        reference_path = dest_file
                
                # 创建音色实体
                entity = VoiceEntity(
                    name=voice_name,
                    tts_provider_id=tts_provider_id,
                    reference_path=reference_path,
                    description=voice_data.get("description"),
                    is_multi_emotion=voice_data.get("is_multi_emotion", 0)
                )
                
                # 保存到数据库
                po = VoicePO(**entity.__dict__)
                self.repository.create(po)
                success_count += 1
        
        return success_count, skipped_count, skipped_names

    def seed_common_edge_voices(
        self,
        tts_provider_id: int,
        target_dir: str | None = None,
        overwrite: bool = False,
    ) -> tuple[int, int, int, list[str], list[str], str]:
        """Generate common Chinese voice samples with Edge-TTS and register them."""
        target_dir = target_dir or os.path.join(getConfigPath(), "voices", "edge-presets")
        target_dir = os.path.abspath(os.path.expanduser(target_dir))
        os.makedirs(target_dir, exist_ok=True)

        success_count = 0
        skipped_names: list[str] = []
        failed_names: list[str] = []
        engine = EdgeTTSEngine()

        for preset in self.COMMON_EDGE_VOICE_PRESETS:
            voice_name = preset["name"]
            existing = self.repository.get_by_name(voice_name, tts_provider_id)
            if existing and not overwrite:
                skipped_names.append(voice_name)
                continue

            safe_name = self._safe_filename(voice_name)
            audio_path = os.path.join(target_dir, f"{safe_name}.mp3")
            try:
                engine.synthesize(
                    preset["sample"],
                    save_path=audio_path,
                    voice=preset["edge_voice"],
                )
                description = ",".join([*preset["tags"], f"edge_voice:{preset['edge_voice']}"])
                data = {
                    "name": voice_name,
                    "tts_provider_id": tts_provider_id,
                    "reference_path": audio_path,
                    "description": description,
                    "is_multi_emotion": 0,
                }

                if existing and overwrite:
                    self.repository.update(existing.id, data)
                else:
                    self.repository.create(VoicePO(**data))
                success_count += 1
            except Exception:
                failed_names.append(voice_name)

        return success_count, len(skipped_names), len(failed_names), skipped_names, failed_names, target_dir

    def seed_common_cosyvoice_voices(
        self,
        tts_provider,
        target_dir: str | None = None,
        overwrite: bool = False,
    ) -> tuple[int, int, int, list[str], list[str], str]:
        """Generate model-compatible CosyVoice system-voice previews."""
        model = (getattr(tts_provider, "model", None) or "").strip().lower()
        if not model.startswith("cosyvoice"):
            raise ValueError("当前 TTS 引擎不是 CosyVoice，请先选择对应模型")

        if model.startswith(("cosyvoice-v3-flash", "cosyvoice-v3-plus")):
            presets = list(self.COMMON_COSYVOICE_V3_INSTRUCT_PRESETS)
            if model.startswith("cosyvoice-v3-flash"):
                presets += self.SUSPENSE_COSYVOICE_V3_PRESETS
            preset_family = "cosyvoice-v3-instruct"
        elif model.startswith("cosyvoice-v1"):
            presets = self.COMMON_COSYVOICE_V1_PRESETS
            preset_family = "cosyvoice-base"
        elif model.startswith("cosyvoice-v2"):
            raise ValueError("CosyVoice-v2 不能复用 v1 音色编号，请按官方 v2 音色列表手动导入")
        else:
            raise ValueError("该 CosyVoice 模型没有可安全复用的系统音色预设；声音复刻/设计音色请手动导入")

        target_dir = target_dir or os.path.join(getConfigPath(), "voices", f"{preset_family}-presets")
        target_dir = os.path.abspath(os.path.expanduser(target_dir))
        os.makedirs(target_dir, exist_ok=True)
        engine = ConfigurableCloudTTSEngine(
            getattr(tts_provider, "api_base_url", None),
            api_key=getattr(tts_provider, "api_key", None),
            model=getattr(tts_provider, "model", None),
            custom_params=getattr(tts_provider, "custom_params", None),
        )
        success_count = 0
        skipped_names: list[str] = []
        failed_names: list[str] = []
        for preset in presets:
            voice_name = preset["name"]
            existing = self.repository.get_by_name(voice_name, tts_provider.id)
            if existing and not overwrite:
                skipped_names.append(voice_name)
                continue
            audio_path = os.path.join(target_dir, f"{self._safe_filename(voice_name)}.mp3")
            try:
                engine.synthesize(
                    preset["sample"], save_path=audio_path, voice_name=preset["voice"],
                    instruction=preset.get("instruction"),
                )
                description = ",".join([*preset["tags"], "无需参考音频", f"cosyvoice_voice:{preset['voice']}"])
                data = {
                    "name": voice_name,
                    "tts_provider_id": tts_provider.id,
                    "reference_path": audio_path,
                    "description": description,
                    "is_multi_emotion": 0,
                }
                if existing and overwrite:
                    self.repository.update(existing.id, data)
                else:
                    self.repository.create(VoicePO(**data))
                success_count += 1
            except Exception:
                failed_names.append(voice_name)

        return success_count, len(skipped_names), len(failed_names), skipped_names, failed_names, target_dir

    def _safe_filename(self, value: str) -> str:
        keep = []
        for char in value:
            if char.isalnum() or char in {"-", "_"}:
                keep.append(char)
            else:
                keep.append("_")
        return "".join(keep).strip("_") or "voice"

    def process_audio(self, dto: VoiceAudioProcessDTO) -> bool:
        """处理音色参考音频
        - 变速、音量调整
        - 裁剪/删除区间
        - 添加/裁剪末尾静音
        - 指定位置插入静音
        """
        audio_path = dto.audio_path
        if not os.path.exists(audio_path):
            raise FileNotFoundError(audio_path)
        
        processor = AudioProcessor(audio_path)
        
        start_ms = dto.start_ms
        end_ms = dto.end_ms
        speed = dto.speed
        volume = dto.volume
        current_ms = dto.current_ms
        silence_sec = dto.silence_sec
        
        # ---------- (1) 优先裁剪 ----------
        if start_ms is not None and end_ms is not None and end_ms > start_ms:
            processor.cut(start_ms, end_ms)
        
        # ---------- (2) 插入静音 ----------
        elif current_ms is not None and silence_sec is not None and silence_sec != 0:
            processor.insert_silence(current_ms, silence_sec)
        
        # ---------- (3) 末尾静音/裁剪 ----------
        elif current_ms is None and silence_sec is not None and silence_sec != 0:
            processor.append_silence(silence_sec)
        
        # ---------- (4) 音量 + 变速 ----------
        if speed != 1.0:
            processor.change_speed(speed)
        if volume != 1.0:
            processor.change_volume(volume)
        
        return True

    def copy_voice(self, source_voice_id: int, new_name: str, target_dir: str = None) -> VoiceEntity:
        """复制音色
        - 获取源音色信息
        - 复制音频文件到目标目录
        - 创建新音色记录
        - 返回新音色实体
        """
        # 获取源音色
        source_voice = self.get_voice(source_voice_id)
        if not source_voice:
            raise ValueError("源音色不存在")
        
        # 检查新名称是否已存在
        existing = self.repository.get_by_name(new_name, source_voice.tts_provider_id)
        if existing:
            raise ValueError(f"音色名称 '{new_name}' 已存在")
        
        new_reference_path = None
        
        # 处理音频文件复制
        if source_voice.reference_path and os.path.exists(source_voice.reference_path):
            # 确定目标目录
            if target_dir and target_dir.strip():
                dest_dir = target_dir.strip()
            else:
                # 使用源音频所在目录
                dest_dir = os.path.dirname(source_voice.reference_path)
            
            # 确保目标目录存在
            os.makedirs(dest_dir, exist_ok=True)
            
            # 获取源文件扩展名
            file_ext = os.path.splitext(source_voice.reference_path)[1]
            # 使用新音色名作为文件名
            new_file_name = f"{new_name}{file_ext}"
            new_reference_path = os.path.join(dest_dir, new_file_name)
            
            # 复制文件
            shutil.copy2(source_voice.reference_path, new_reference_path)
        
        # 创建新音色实体
        new_entity = VoiceEntity(
            name=new_name,
            tts_provider_id=source_voice.tts_provider_id,
            reference_path=new_reference_path,
            description=source_voice.description,
            is_multi_emotion=source_voice.is_multi_emotion
        )
        
        # 保存到数据库
        po = VoicePO(**new_entity.__dict__)
        res = self.repository.create(po)
        
        # 返回新建的音色实体
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        return VoiceEntity(**data)
