"""Single-instance startup recovery: never re-enqueue uncertain paid work."""
import os
from pathlib import Path
from sqlalchemy import select
from app.models.po import AudioTaskPO, ChatSessionPO, LinePO

class InstanceLock:
    def __init__(self, directory):
        self.file=open(Path(directory)/'.runtime.lock','a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('此配置目录已有 Auralis 实例运行')
    def close(self):
        self.file.close()


def recover_interrupted(db):
    count=0
    for task in db.scalars(select(AudioTaskPO).where(AudioTaskPO.status.in_(['queued','processing','completing']))):
        task.status='failed';task.error_code='PROCESS_INTERRUPTED'
        task.error_message='上次进程中断；未自动重发请求，请检查已有产物后显式重试'
        task.run_token=None
        line=db.get(LinePO,task.line_id)
        if line and line.status=='processing':line.status='pending';line.is_done=0
        count+=1
    for session in db.scalars(select(ChatSessionPO).where(ChatSessionPO.current_stage.in_(
            ['parsing','generating_script','reviewing_script','committing']))):
        stage=session.current_stage
        session.status='failed';session.current_stage='failed'
        session.pending_confirm_json={**(session.pending_confirm_json or {}),'type':'retry','retry_stage':stage}
        session.last_error_code='PROCESS_INTERRUPTED'
        session.last_error_message='上次进程中断，请从保存的步骤显式重试'
    for session in db.scalars(select(ChatSessionPO).where(ChatSessionPO.running_token.is_not(None))):
        session.running_token=None;session.lease_expires_at=None
    db.commit()
    return count
