"""Offline SQLite durable reference. Not a D1/production storage adapter."""
import json
import re
import sqlite3
from pathlib import Path
ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
SHA=re.compile(r'^[a-f0-9]{64}$')
TERMINAL={'Done','Failed','UNKNOWN'}
class Stop(Exception): pass

def require(ok,reason):
    if not ok: raise Stop(reason)

class Ledger:
    offline_only=True
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('Pending','Processing','Done','Failed','UNKNOWN')),
 owner TEXT, epoch INTEGER NOT NULL DEFAULT 0, fence INTEGER NOT NULL DEFAULT 0,
 lease_until INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0 CHECK(sent IN (0,1)),
 identity TEXT UNIQUE, result TEXT, created_at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_job BEFORE UPDATE ON jobs
WHEN NEW.job_id!=OLD.job_id OR NEW.fingerprint!=OLD.fingerprint OR NEW.created_at!=OLD.created_at
 OR (OLD.sent=1 AND (NEW.sent!=1 OR NEW.identity IS NOT OLD.identity))
 OR (OLD.state IN ('Done','Failed','UNKNOWN') AND NEW.state!=OLD.state)
BEGIN SELECT RAISE(ABORT,'immutable_or_terminal'); END;
CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON jobs
BEGIN SELECT RAISE(ABORT,'tombstone_required'); END;
CREATE TABLE IF NOT EXISTS budgets(day TEXT PRIMARY KEY,jobs INTEGER NOT NULL,minutes INTEGER NOT NULL,units INTEGER NOT NULL,bytes INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(job_id TEXT PRIMARY KEY,reason TEXT NOT NULL);
''')
    def close(self):self.db.close()
    def add(self,job_id,fingerprint,now):
        require(isinstance(job_id,str) and ID.fullmatch(job_id) and SHA.fullmatch(fingerprint),'IDENTITY_STOP')
        require(type(now) is int and now>0,'CLOCK_STOP')
        try:self.db.execute('INSERT INTO jobs(job_id,fingerprint,state,created_at) VALUES (?, ?, ?, ?)',(job_id,fingerprint,'Pending',now));return True
        except sqlite3.IntegrityError:
            require(self.get(job_id)['fingerprint']==fingerprint,'CHANGED_DUPLICATE_STOP');return False
    def get(self,job_id):
        r=self.db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone();return dict(r) if r else None
    def claim(self,job_id,owner,now,ttl=300):
        require(isinstance(owner,str) and ID.fullmatch(owner) and type(ttl) is int and 0<ttl<=900 and type(now) is int,'LEASE_POLICY_STOP')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.get(job_id);require(row is not None,'JOB_MISSING_STOP')
            eligible=row['state']=='Pending' or (row['state']=='Processing' and row['sent']==0 and row['lease_until']<=now)
            require(eligible,'CLAIM_CONFLICT_STOP')
            self.db.execute("UPDATE jobs SET state='Processing',owner=?,epoch=epoch+1,fence=fence+1,lease_until=? WHERE job_id=?",(owner,now+ttl,job_id));out=self.get(job_id);self.db.execute('COMMIT');return out
        except Exception:self.db.execute('ROLLBACK');raise
    def consume(self,claim,identity,now):
        require(isinstance(identity,str) and ID.fullmatch(identity),'OPERATION_ID_STOP')
        # Compare-and-set persists the SENT tombstone before the first upload POST.
        cur=self.db.execute("UPDATE jobs SET sent=1,identity=? WHERE job_id=? AND state='Processing' AND sent=0 AND owner=? AND epoch=? AND fence=? AND lease_until>?",(identity,claim['job_id'],claim['owner'],claim['epoch'],claim['fence'],now))
        require(cur.rowcount==1,'CONSUMPTION_CONFLICT_STOP')
    def finish(self,claim,state,video_id=None,reason=None):
        require(state in TERMINAL and (video_id is None or re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id)),'RESULT_SHAPE_STOP')
        require(reason in {None,'RENDER_FAILED','AUTH_STOP','UPLOAD_UNKNOWN','EMERGENCY_STOP','BUDGET_STOP','CONFIG_STOP'},'REASON_STOP')
        result=json.dumps({'job_id':claim['job_id'],'state':state,'video_id':video_id,'reason_code':reason},sort_keys=True)
        cur=self.db.execute("UPDATE jobs SET state=?,result=? WHERE job_id=? AND state='Processing' AND owner=? AND epoch=? AND fence=?",(state,result,claim['job_id'],claim['owner'],claim['epoch'],claim['fence']))
        require(cur.rowcount==1,'STALE_RESULT_STOP')
        if state!='Done':self.db.execute('INSERT OR IGNORE INTO notifications VALUES (?,?)',(claim['job_id'],reason or 'UPLOAD_UNKNOWN'))
        return json.loads(result)
    def recover_crash(self,now):
        # Expired SENT jobs can only be quarantined; never reclaimed.
        self.db.execute("UPDATE jobs SET state='UNKNOWN',result=json_object('job_id',job_id,'state','UNKNOWN','reason_code','UPLOAD_UNKNOWN') WHERE state='Processing' AND sent=1 AND lease_until<=?",(now,))
        self.db.execute("INSERT OR IGNORE INTO notifications SELECT job_id,'UPLOAD_UNKNOWN' FROM jobs WHERE state='UNKNOWN'")
    def reserve_budget(self,day,cost,limits):
        require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) and set(cost)==set(limits)=={'jobs','minutes','units','bytes'},'BUDGET_CONFIG_STOP')
        require(all(type(x) is int and x>=0 for x in [*cost.values(),*limits.values()]),'BUDGET_CONFIG_STOP')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('INSERT OR IGNORE INTO budgets VALUES (?,0,0,0,0)',(day,))
            row=dict(self.db.execute('SELECT * FROM budgets WHERE day=?',(day,)).fetchone())
            require(all(row[k]+cost[k]<=limits[k] for k in cost),'BUDGET_STOP')
            self.db.execute('UPDATE budgets SET jobs=jobs+?,minutes=minutes+?,units=units+?,bytes=bytes+? WHERE day=?',(*[cost[k] for k in ['jobs','minutes','units','bytes']],day));self.db.execute('COMMIT')
        except Exception:self.db.execute('ROLLBACK');raise
    def notify(self,key,reason):
        require(ID.fullmatch(key) and reason in {'EMERGENCY_STOP','BUDGET_STOP','CONFIG_STOP','AUTH_STOP'},'NOTIFICATION_STOP')
        self.db.execute('INSERT OR IGNORE INTO notifications VALUES (?,?)',(key,reason))
    def progress(self):
        counts={s:0 for s in ['Pending','Processing','Done','Failed','UNKNOWN']}
        counts.update({r['state']:r['n'] for r in self.db.execute('SELECT state,count(*) n FROM jobs GROUP BY state')})
        completed=sum(counts[s] for s in TERMINAL)
        return {'counts':counts,'success_rate':counts['Done']/completed if completed else None,'stopped':counts['Failed']+counts['UNKNOWN']>0,'notifications':[dict(r) for r in self.db.execute('SELECT * FROM notifications')]}
