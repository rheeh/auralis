"""Provider execution accepts ordinary data only. No Session, repository or service."""
import os
from app.core.tts_engine import EdgeTTSEngine, ConfigurableCloudTTSEngine, TTSEngine


def execute_prepared(request, observer=None):
    prepared=request['prepared']; provider=request['provider']; path=request['output_path']
    if prepared['route']=='edge':
        if observer:
            observer('request',{'driver':'edge','text':prepared['tts_text'],'voice':request['edge_voice'],**request['prosody']})
        audio=EdgeTTSEngine().synthesize(prepared['tts_text'],save_path=path,voice=request['edge_voice'],**request['prosody'])
        if observer:
            observer('response',{'response_kind':'audio','audio_bytes':len(audio)})
        return audio
    if provider['provider_type'] in {'fish','legacy','index_tts'}:
        engine=TTSEngine(provider['api_base_url'],api_key=provider['api_key'])
        engine.observer=observer
        reference=request['reference_path']
        if not reference or not os.path.isfile(reference):
            raise ValueError('参考音频不存在')
        if not engine.check_audio_exists(reference):
            result=engine.upload_audio(reference,reference)
            if result.get('code') and result['code']!=200:
                raise ValueError('参考音频上传失败')
        return engine.synthesize(prepared['tts_text'],reference,emo_vector=request['emo_vector'],save_path=path)
    engine=ConfigurableCloudTTSEngine(provider['api_base_url'],provider['api_key'],provider['model'],provider['custom_params'])
    engine.observer=observer
    return engine.synthesize(prepared['tts_text'],save_path=path,voice_name=request['voice_name'],
        reference_path=request['reference_path'],emo_vector=request['emo_vector'],instruction=prepared['instruction'])
