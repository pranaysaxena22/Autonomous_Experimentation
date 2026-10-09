"""
Synthetic tablet-formulation experiment generator.  *** NOT REAL DATA ***
Built to test data ingestion, validation and model selection before real client data exists.

Complexities deliberately injected (so a model-selection harness has something to find):
  - ingredients that must sum to 100 (filler is the balance)
  - interactions between ingredients and with process settings
  - batch effects and supplier effects (categorical inputs)
  - instrument drift on one of two dissolution testers
  - replicate measurements, heteroscedastic noise
  - failed runs, missing values, a mixed-unit column, below-detection values
  - historical bias: most experiments cluster near a few favourite recipes

Difficulty levels (--difficulty): easy (default) or hard.
  hard = stronger interactions and non-linearity, more noise, bigger batch/supplier effects, larger drift plus a
         recalibration step, poorer coverage (85% of experiments clustered), more failures, more missing values,
         more mixed units, and occasional wild outliers.

Usage:  python make_mock_data.py --n 3000 --seed 42 --difficulty easy --out mock.csv [--truth truth.csv]
"""
import argparse, numpy as np, pandas as pd

LIM = dict(drug=(10,30), binder=(2,6), disint=(1,8), lube=(0.25,2), force=(5,20), blend=(5,30))
PROFILE = {
  'easy': dict(noise=1.0,batch=1.0,supp=1.0,drift=3.0,step=0.0,inter=1.0,nonlin=0.0,cluster=0.60,fail=0.04,miss=1.0,unit=0.015,outlier=0.0),
  'hard': dict(noise=1.8,batch=2.0,supp=1.5,drift=6.0,step=-4.0,inter=2.2,nonlin=1.0,cluster=0.85,fail=0.08,miss=3.0,unit=0.03,outlier=0.01),
}
SUPPLIER_EFFECT = {'A':(0.0,0.0), 'B':(-3.0,0.35), 'C':(1.5,-0.20)}      # (dissolution, hardness)
GRADE_EFFECT    = {'MCC-101':(0.0,0.0), 'MCC-102':(1.0,0.30)}

def truth(drug,filler,binder,dis,lube,force,blend,inter=1.0,nonlin=0.0):
    d=(drug-10)/20; b=(binder-2)/4; s=(dis-1)/7; l=(lube-0.25)/1.75
    f=(filler-54)/(86.75-54); fo=(force-5)/15; bt=(blend-5)/25
    diss = (70 + 26*s**0.65 - 12*b - 10*l - 8*d**2 + 6*np.exp(-((f-0.55)/0.30)**2)
            + inter*6*s*(1-b) - 6*fo + 2*bt - inter*4*fo*b)
    if nonlin: diss = diss + nonlin*(4*np.sin(2.5*np.pi*s)*b + 3*np.cos(2.0*np.pi*fo)*(1-l))
    hard = (5.2 + 4.6*b + 2.0*f - 3.2*s - 1.8*l - 1.0*d + inter*1.8*b*f + 3.5*fo - inter*0.8*bt*fo)
    if nonlin: hard = hard + nonlin*(0.9*np.sin(2.0*np.pi*b)*fo + 0.6*np.cos(2.5*np.pi*d)*s)
    return diss, hard

def generate(n=3000, seed=42, noise=1.0, difficulty='easy'):
    P=PROFILE[difficulty]; noise=noise*P['noise']
    rng=np.random.default_rng(seed)
    n_batches=max(4,n//50)
    days=pd.bdate_range('2025-01-06',periods=int(n_batches*1.6))
    batch_days=np.sort(rng.choice(len(days),n_batches,replace=False))
    batch_date=[days[i] for i in batch_days]
    b_diss=rng.normal(0,1.5*P['batch'],n_batches); b_hard=rng.normal(0,0.25*P['batch'],n_batches)
    b_supplier=rng.choice(list(SUPPLIER_EFFECT),n_batches,p=[.5,.3,.2])
    b_grade=rng.choice(list(GRADE_EFFECT),n_batches,p=[.7,.3])
    b_inst=np.where(np.arange(n_batches)%2==0,'DT-1','DT-2')
    # recipes: 60% near three favourite recipes, 40% exploratory
    fav=np.array([[.30,.55,.60,.25,.25],[.50,.40,.55,.35,.45],[.35,.65,.45,.20,.55]])  # drug,binder,disint,lube,force (normalised)
    rows=[]
    for e in range(n):
        bi=e*n_batches//n
        if rng.random()<P['cluster']:
            c=fav[rng.integers(3)]; u=np.clip(c+rng.normal(0,0.09,5),0,1)
        else: u=rng.random(5)
        drug=LIM['drug'][0]+u[0]*20; binder=LIM['binder'][0]+u[1]*4; dis=LIM['disint'][0]+u[2]*7; lube=LIM['lube'][0]+u[3]*1.75
        force=LIM['force'][0]+u[4]*15; blend=rng.uniform(*LIM['blend'])
        filler=100-drug-binder-dis-lube
        d0,h0=truth(drug,filler,binder,dis,lube,force,blend,P['inter'],P['nonlin'])
        sd,sh=SUPPLIER_EFFECT[b_supplier[bi]]; sd,sh=sd*P['supp'],sh*P['supp']; gd,gh=GRADE_EFFECT[b_grade[bi]]
        day_frac=batch_days[bi]/len(days)
        drift=(P['drift']*day_frac+(P['step'] if day_frac>0.6 else 0.0)) if b_inst[bi]=='DT-2' else 0.0
        td=d0+sd+gd+b_diss[bi]; th=h0+sh+gh+b_hard[bi]
        reps=1 if rng.random()>0.15 else int(rng.integers(2,4))
        failed=rng.random()<P['fail']
        reason=rng.choice(['press jam','dispenser clog','sample lost']) if failed else ''
        for r in range(1,reps+1):
            diss=td+drift+rng.normal(0,1.2*noise*(1+0.5*(td<70)))
            hard=th+rng.normal(0,0.25*noise)
            fri=max(0.0,1.4-0.14*th+rng.normal(0,0.05*noise))
            row=dict(experiment_id=f'E{e+1:05d}',replicate_no=r,date=batch_date[bi].date().isoformat(),batch_id=f'B{bi+1:03d}',
                     drug_pct=round(drug,2),filler_pct=round(filler,2),binder_pct=round(binder,2),disintegrant_pct=round(dis,2),lubricant_pct=round(lube,2),
                     binder_supplier=b_supplier[bi],filler_grade=b_grade[bi],compression_force_kN=round(force,1),blend_time_min=round(blend,0),
                     dissolution_instrument=b_inst[bi],dissolution_30min_pct=min(100.0,round(diss,1)),hardness=round(hard,2),hardness_unit='kP',
                     friability_pct=round(fri,2),friability_note='',status='ok',failure_reason='',_true_diss=round(td,2),_true_hard=round(th,2))
            if failed:
                row.update(dissolution_30min_pct=np.nan,hardness=np.nan,friability_pct=np.nan,status='failed',failure_reason=reason)
            else:
                if rng.random()<P['unit']: row['hardness']=round(row['hardness']*9.807,1); row['hardness_unit']='N'     # mixed units
                if rng.random()<0.010*P['miss']: row['dissolution_30min_pct']=np.nan                                  # missing
                if rng.random()<0.020*P['miss']: row['friability_pct']=np.nan
                if P['outlier'] and rng.random()<P['outlier']: row['dissolution_30min_pct']=round(float(rng.uniform(20,100)),1)   # wild outlier
                if (not np.isnan(row['friability_pct'])) and row['friability_pct']<0.05: row['friability_pct']=0.05; row['friability_note']='<0.05'
            rows.append(row)
    df=pd.DataFrame(rows)
    return df

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--n',type=int,default=3000); ap.add_argument('--seed',type=int,default=42)
    ap.add_argument('--noise',type=float,default=1.0); ap.add_argument('--difficulty',choices=['easy','hard'],default='easy'); ap.add_argument('--out',default='mock_formulation_experiments.csv'); ap.add_argument('--truth',default=None)
    a=ap.parse_args(); df=generate(a.n,a.seed,a.noise,a.difficulty)
    if a.truth: df[['experiment_id','replicate_no','_true_diss','_true_hard']].to_csv(a.truth,index=False)
    df.drop(columns=[c for c in df.columns if c.startswith('_')]).to_csv(a.out,index=False)
    print(len(df),'rows written to',a.out)
