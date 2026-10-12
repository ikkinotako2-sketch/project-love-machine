"""No billing API calls. Require fresh explicit per-service remaining amounts."""
from .ledger import require
FIELDS=frozenset('workers_requests d1_rows_read d1_rows_written youtube_insert_calls youtube_other_units actions_minutes artifact_bytes'.split())
def budget_gate(observation,cost,now,*,offline_only=False):
    require(isinstance(observation,dict) and observation.get('plan')=='FREE' and observation.get('billing_cap_usd')==0,'FREE_PLAN_UNVERIFIED_STOP')
    basis=observation.get('basis');require(basis=='API_OBSERVATION' or offline_only is True and basis=='OFFLINE_FIXTURE','ACCOUNT_BUDGET_UNVERIFIED_STOP')
    require(type(observation.get('observed_at')) is int and 0<=now-observation['observed_at']<=300,'STALE_BUDGET_STOP')
    remaining=observation.get('remaining');require(isinstance(remaining,dict) and set(remaining)==set(cost)==FIELDS,'BUDGET_SET_STOP')
    require(all(type(remaining[k]) is int and remaining[k]>=0 and type(cost[k]) is int and cost[k]>=0 and cost[k]<=remaining[k] for k in FIELDS),'BUDGET_EXCEEDED_OR_UNKNOWN_STOP')
    return {'verified':True,'basis':basis,'actual_account_verified':basis=='API_OBSERVATION'}
