import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.models import po

class MigrationCopyTest(unittest.TestCase):
    def test_historical_copy_upgrade_preserves_source_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'old.sqlite3';target=root/'copy.sqlite3'
            engine=create_engine(f'sqlite:///{source}');Base.metadata.create_all(engine)
            audio=root/'saved.wav';audio.write_bytes(b'original take retained')
            with Session(engine) as db:
                db.add(po.ProjectPO(id=1,name='历史工程',project_root_path=tmp));db.flush()
                db.add(po.ChapterPO(id=1,project_id=1,title='保留章节'));db.flush()
                db.add(po.LinePO(id=1,chapter_id=1,text_content='历史句',audio_path=str(audio),status='done',is_done=1));db.commit()
                db.add(po.ChatSessionPO(id='old-session',project_id=1,chapter_id=1,current_stage='completed'));db.flush()
                db.add(po.ChatMessagePO(id='old-turn',session_id='old-session',role='user',client_request_id='old-request',
                    payload_json={'source':'production_assistant','pending_tool':{'tool':'update_line','arguments':{'line_id':1}}}))
                db.commit()
            engine.dispose()
            with sqlite3.connect(source) as db:
                db.execute('DROP INDEX uq_active_audio_task_line')
                for column in ['run_token','input_fingerprint','input_snapshot']:
                    db.execute(f'ALTER TABLE audio_tasks DROP COLUMN {column}')
                db.execute('ALTER TABLE voices DROP COLUMN provider_voice_id')
                db.execute('ALTER TABLE chat_messages DROP COLUMN turn_status')
                db.execute('ALTER TABLE chat_messages DROP COLUMN turn_token')
                db.execute('PRAGMA user_version=8')
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            script=Path(__file__).resolve().parents[2]/'scripts/migrate_copy.py'
            result=subprocess.run([sys.executable,str(script),str(source),str(target)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
            with sqlite3.connect(target) as db:
                self.assertEqual(db.execute('SELECT audio_path FROM lines WHERE id=1').fetchone()[0],str(audio))
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                status,payload=db.execute("SELECT turn_status,payload_json FROM chat_messages WHERE id='old-turn'").fetchone()
                self.assertEqual(status,'interrupted')
                self.assertIn('pending_tool',payload)
            self.assertEqual(audio.read_bytes(),b'original take retained')
