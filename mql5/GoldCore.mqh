#ifndef GOLD_CORE_MQH
#define GOLD_CORE_MQH
#define FEATURE_VERSION "sg-v1"
#define FEATURE_COUNT 20
// Generated feature hash is checked by Python contract tests.
#define FEATURE_HASH "1de86e48874f91f7e39e5e4631afb785bb7d5a81a22b90280d806960d57628df"
enum Regime { WAIT=0, TREND_UP=1, TREND_DOWN=2, RANGE=3, BREAKOUT=4 };
enum Strategy { NONE=0, TREND=1, REVERSAL=2, BREAK=3 };
struct Snapshot {
 datetime utc,m15;
 double o,h,l,c,prev,c3,ema,ema_prev,atr,rsi,adx,plus,minus,e20,e50,a15,a15mean;
 double support,resistance,percentile,h1ema,h1atr,spread;
};
struct Candidate {
 string id;
 datetime utc;
 Strategy strategy;
 int direction;
 double entry,sl,tp;
 double f[FEATURE_COUNT];
};
string StrategyName(Strategy s) {
 if(s==TREND) return "trend";
 if(s==REVERSAL) return "range";
 return "breakout";
}
Regime RawRegime(const Snapshot &s) {
 if(s.atr<=0 || s.a15<=0 || s.a15mean<=0 || s.h1atr<=0 || s.resistance<=s.support) return WAIT;
 if(s.adx>=25) {
  if(s.e20>s.e50 && s.plus>s.minus) return TREND_UP;
  if(s.e20<s.e50 && s.plus<s.minus) return TREND_DOWN;
  return WAIT;
 }
 if(s.adx<20 && s.resistance-s.support>=3*s.a15)
  return s.a15<=0.8*s.a15mean ? BREAKOUT : RANGE;
 return WAIT;
}
class RegimeDetector {
 private:
 Regime current,pending;
 int count;
 datetime last;
 public:
 RegimeDetector() {current=WAIT; pending=WAIT; count=0; last=0;}
 Regime Update(const Snapshot &s) {
  Regime r=RawRegime(s);
  if(r==WAIT) {current=WAIT;pending=WAIT;count=0;last=s.m15;return WAIT;}
  if(s.m15!=last) {
   count=(r==pending ? count+1 : 1); pending=r;last=s.m15;
   if(count>=2) current=r;
  }
  return current==r ? current : WAIT;
 }
};
void FillFeatures(const Snapshot &s,Regime regime,Candidate &c) {
 c.f[0]=(s.c-s.ema)/s.atr;c.f[1]=(s.ema-s.ema_prev)/s.atr;
 c.f[2]=s.adx;c.f[3]=s.plus-s.minus;c.f[4]=s.rsi;
 c.f[5]=MathAbs(s.c-s.o)/MathMax(s.h-s.l,1e-12);
 c.f[6]=s.c/s.prev-1;c.f[7]=s.c/s.c3-1;c.f[8]=s.percentile;
 c.f[9]=(s.c-s.support)/s.a15;c.f[10]=(s.resistance-s.c)/s.a15;
 c.f[11]=(s.resistance-s.support)/s.a15;c.f[12]=s.a15/s.a15mean;
 c.f[13]=MathMax(MathMax(s.c-s.resistance,s.support-s.c),0)/s.atr;
 c.f[14]=s.spread/s.atr;c.f[15]=MathAbs(c.tp-c.entry)/MathAbs(c.entry-c.sl);
 c.f[16]=(double)((s.utc/3600)%24);c.f[17]=(double)c.strategy;c.f[18]=(double)regime;
 c.f[19]=(s.c-s.h1ema)/s.h1atr;
}
bool Generate(const Snapshot &s,Regime regime,string symbol,Candidate &selected) {
 if(regime==WAIT) return false;
 bool found=false;
 for(int d=1;d>=-1;d-=2) {
  Candidate c; c.strategy=NONE;c.direction=d;c.utc=s.utc;
  c.entry=s.c+(d==1 ? s.spread : 0);c.sl=c.entry-d*1.5*s.atr;c.tp=c.entry+d*3*s.atr;
  if(regime==(d==1 ? TREND_UP : TREND_DOWN)) {
   if((d==1 ? s.l<=s.ema : s.h>=s.ema) && d*(s.c-s.ema)>0 && d*(s.c-s.o)>0 && d*(s.c-s.prev)>0) c.strategy=TREND;
  }
  if(regime==RANGE) {
   double bound=d==1 ? s.support : s.resistance;
   if(MathAbs(s.c-bound)<=0.25*s.a15 && (d==1 ? s.rsi<35 : s.rsi>65) && d*(s.c-s.o)>0) {
    c.strategy=REVERSAL;c.sl=bound-d*0.5*s.atr;c.tp=(s.support+s.resistance)/2;
   }
  }
  if(regime==BREAKOUT) {
   double bound=d==1 ? s.resistance : s.support;
   if(d*(s.c-bound)>=0.1*s.atr && d*(c.entry-bound)<=0.5*s.atr && d*(s.c-s.o)>0 && MathAbs(s.c-s.o)>=0.6*(s.h-s.l)) {
    c.strategy=BREAK;c.tp=c.entry+d*3.75*s.atr;
   }
  }
  if(c.strategy==NONE || d*(c.entry-c.sl)<=0 || d*(c.tp-c.entry)<=0 || MathAbs(c.tp-c.entry)/MathAbs(c.entry-c.sl)<1.5) continue;
  c.id=symbol+"-"+IntegerToString((long)s.utc)+"-"+IntegerToString((int)c.strategy)+"-"+IntegerToString(d);
  FillFeatures(s,regime,c);
  if(found && selected.direction!=d) return false;
  if(!found || c.strategy==BREAK) selected=c;
  found=true;
 }
 return found;
}
string FeatureNames[FEATURE_COUNT]={"ema_distance","ema_slope","adx","di_delta","rsi","body_ratio","return_1","return_3","atr_percentile","support_distance","resistance_distance","range_width","compression","breakout_distance","spread_atr","planned_rr","session","strategy","regime","h1_distance"};
#endif
