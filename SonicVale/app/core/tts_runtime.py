"""Bounded local executor. Only ordinary request data crosses the thread boundary."""
import asyncio
import logging
from app.core.ws_manager import manager
from app.db.database import SessionLocal
from app.models.po import ChatSessionPO, AudioTaskPO
from app.services.audio_task_service import AudioTaskService
from app.services.tts_trace_service import TTSTraceService, TTSRequestRecorder, redact
from app.integrations.tts.prepared import execute_prepared
from app.workflows.drama.events import WorkflowEventPublisher

TTS_TIMEOUT_SECONDS = 1200

def execution_health(app):
    active = list(getattr(app.state, 'tts_active_attempts', {}).values())
    return {'active_slots':len(active), 'blocked_slots':sum(
        item['state'] in {'running_after_timeout','unknown_after_shutdown'} for item in active)}


def _trace_ended(db, generation_id, **kwargs):
    if not generation_id:
        return
    try:
        db.rollback()
        TTSTraceService(db).execution_ended(generation_id, **kwargs)
    except Exception:
        db.rollback()
        logging.exception('Could not reconcile generation trace %s', generation_id)

def _record_failure(service,task_id,token,message,code='TTS_FAILED'):
    try:
        service.db.rollback()
        service.fail(task_id,token,message,code)
    except Exception:
        service.db.rollback()
        logging.exception('Could not persist failed task %s; startup recovery will reconcile it',task_id)


async def _notify(db, task, remaining):
    # Notifications are best effort after durable business completion. Failure
    # here must never turn a completed generation into failed or kill the loop.
    try:
        if task.session_id:
            session=db.get(ChatSessionPO,task.session_id)
            if session:
                WorkflowEventPublisher(db).publish(session,'tts_task_updated',{
                    'task_id':task.id,'line_id':task.line_id,'status':task.status,'attempt':task.attempt,
                    'error_message':task.error_message,'queue_size':remaining})
        await manager.broadcast({'event':'line_update','project_id':task.project_id,
            'session_id':task.session_id,'line_id':task.line_id,'task_id':task.id,
            'status':task.status,'progress':remaining})
    except Exception:
        db.rollback()
        logging.warning('Task notification failed for %s',task.id)

async def tts_worker(app):
    queue=app.state.tts_queue
    if not hasattr(app.state,'tts_active_attempts'):
        app.state.tts_active_attempts={}
    active=app.state.tts_active_attempts
    while True:
        item=await queue.get()
        db=SessionLocal()
        service=AudioTaskService(db)
        task_id=None;token=None
        generation_id=None
        future=None;secrets=();request={}
        try:
            if not isinstance(item,dict):raise ValueError('Invalid queue item')
            task_id=item.get('task_id');token=item.get('run_token')
            if not task_id or not service.claim(task_id,token):
                continue
            task=db.get(AudioTaskPO,task_id)
            await _notify(db,task,queue.qsize())
            request=item['request']
            secrets=(request['provider'].get('api_key') or '',)
            trace=TTSTraceService(db)
            generation_id=trace.begin(task.project_id,task.chapter_id,task.line_id,task.id,task.input_snapshot)
            recorder=TTSRequestRecorder(db.get_bind(),generation_id,secrets)
            db.commit()  # release read transaction before provider I/O
            active[token]={'task_id':task_id,'state':'running'}
            future=asyncio.get_running_loop().run_in_executor(app.state.tts_executor,execute_prepared,request,recorder)
            try:
                audio=await asyncio.wait_for(asyncio.shield(future),timeout=TTS_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                service.fail(task_id,token,'等待配音超时；底层请求可能仍在运行','TTS_TIMEOUT')
                active[token]['state']='running_after_timeout'
                _trace_ended(db,generation_id,status='timed_out',execution_state='running_after_timeout',
                    error='用户等待超时；底层仍运行并占用执行槽位',result={'orphan_path':request['output_path']},secrets=secrets)
                await _notify(db,task,queue.qsize())
                # Do not free a concurrency slot while its native thread is alive.
                # Late output remains isolated in its own attempt path.
                try:
                    late_audio=await asyncio.shield(future)
                    _trace_ended(db,generation_id,status='timed_out',execution_state='late_succeeded',
                        error='超时后的音频已隔离保留，未采用为当前结果',result={'orphan_path':request['output_path'],'audio':late_audio},secrets=secrets)
                except Exception as exc:
                    _trace_ended(db,generation_id,status='timed_out',execution_state='late_failed',
                        error=f'超时后底层请求结束：{exc}',secrets=secrets)
                    logging.warning('Timed-out provider terminated for %s',task_id)
                await _notify(db,task,queue.qsize())
                continue
            adopted=service.complete(task_id,token,request['output_path'])
            try:
                trace.finish(generation_id,audio=audio,version_id=token,secrets=secrets)
            except Exception:
                db.rollback();logging.warning('Trace completion failed for %s',task_id)
            await _notify(db,task,queue.qsize())
        except asyncio.CancelledError:
            if task_id:
                _record_failure(service,task_id,token,'进程关闭，请检查历史产物后显式重试','PROCESS_INTERRUPTED')
            if token in active:active[token]['state']='unknown_after_shutdown'
            _trace_ended(db,generation_id,status='interrupted',execution_state='unknown_after_shutdown',
                error='进程关闭；执行线程未被强制取消，结果可能未知',result={'orphan_path':request.get('output_path')},secrets=secrets)
            raise
        except Exception as exc:
            if task_id:
                _record_failure(service,task_id,token,redact(str(exc),locals().get('secrets',())))
            if generation_id:
                try:
                    TTSTraceService(db).finish(generation_id,error=exc,secrets=locals().get('secrets',()))
                except Exception:
                    db.rollback();logging.warning('Trace failure recording failed for %s',task_id)
            logging.warning('Audio attempt failed: %s',task_id)
            if task_id and (failed_task:=db.get(AudioTaskPO,task_id)):
                await _notify(db,failed_task,queue.qsize())
        finally:
            if future is not None and not future.done():
                # Cancellation of this coroutine does not cancel the native
                # thread. Keep the health slot until it actually terminates.
                def release_slot(done, key=token):
                    active.pop(key,None)
                    if not done.cancelled():done.exception()
                future.add_done_callback(release_slot)
            else:
                active.pop(token,None)
            db.close();queue.task_done()
