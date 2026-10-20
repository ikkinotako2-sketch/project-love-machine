"""Schema invariants and real thread/connection races; no Cloudflare calls."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

SCHEMA = (Path(__file__).resolve().parents[1] / 'serverless/schema.sql').read_text()

class ServerlessSchemaTests(unittest.TestCase):
    def test_publish_key_and_id_immutable(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript(SCHEMA)
            values=('tiktok','tiktok_game_001','test-claim','a'*64,'worker-001','initialized',1,'persist_publish_id','mock-publish',1,1)
            db.execute('INSERT INTO publish_claims VALUES (?,?,?,?,?,?,?,?,?,?,?)',values)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO publish_claims VALUES (?,?,?,?,?,?,?,?,?,?,?)',values)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE publish_claims SET publish_id='other'")

    def test_real_concurrent_connections_unique_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db'
            with sqlite3.connect(path) as db: db.executescript(SCHEMA)
            barrier=threading.Barrier(4);wins=[];errors=[]
            def claim(i):
                try:
                    with sqlite3.connect(path,timeout=5) as db:
                        barrier.wait(timeout=5)
                        cursor=db.execute("INSERT INTO test_jobs VALUES ('test','test_reference_001','test-race',?,?, 'ready',1,'claim',NULL,1,1) ON CONFLICT(platform,account_id,job_id) DO NOTHING",('a'*64,f'worker-{i}'))
                        wins.append(cursor.rowcount)
                except Exception as exc: errors.append(type(exc).__name__)
            threads=[threading.Thread(target=claim,args=(i,)) for i in range(4)]
            for t in threads:t.start()
            for t in threads:t.join(timeout=10)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertEqual(errors,[]);self.assertEqual(sum(wins),1)
