// Candidate only. Injected DB; no deployed handler or automatic migration.
const need=(ok)=>{if(!ok)throw Error('SHARED_ADMISSION_STOP');};
export class D1JobAdmission{
 constructor(db){need(db?.withSession);this.s=db.withSession('first-primary');this.unknown=false;}
 async reserve(job,day,units){
  need(!this.unknown&&/^[A-Za-z0-9_-]{1,64}$/.test(job)&&/^\d{4}-\d{2}-\d{2}$/.test(day)&&Number.isInteger(units)&&units>0&&units<=1000);
  this.unknown=true;
  const prior=await this.s.prepare('SELECT day,units FROM plm_auto_v1_reservation WHERE job_id=?').bind(job).first();
  if(prior){need(prior.day===day&&prior.units===units);this.unknown=false;return 'DUPLICATE_NO_CHARGE';}
  const out=await this.s.batch([this.s.prepare('INSERT OR IGNORE INTO plm_auto_v1_budget(day) VALUES (?)').bind(day),this.s.prepare('INSERT OR IGNORE INTO plm_auto_v1_reservation(job_id,day,units) VALUES (?,?,?)').bind(job,day,units)]);
  need(Array.isArray(out)&&out.length===2&&out.every(x=>x.success===true));
  const actual=await this.s.prepare('SELECT day,units FROM plm_auto_v1_reservation WHERE job_id=?').bind(job).first();need(actual?.day===day&&actual.units===units);
  this.unknown=false;return out[1].meta?.changes===1?'RESERVED':'DUPLICATE_NO_CHARGE';
 }
 async notice(job,reason){need(!this.unknown&&['UNKNOWN','AUTH_STOP','BUDGET_STOP','CONFIG_STOP'].includes(reason));this.unknown=true;const out=await this.s.batch([this.s.prepare('INSERT OR IGNORE INTO plm_auto_v1_notice(job_id,reason) VALUES (?,?)').bind(job,reason)]);need(out?.length===1&&out[0].success===true);this.unknown=false;}
}
