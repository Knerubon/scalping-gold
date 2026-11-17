#property strict
#property script_show_inputs
#include "GoldCore.mqh"
#include "GoldJson.mqh"
int failures=0;
void Check(bool value,string name) {if(!value) {failures++;Print("FAIL ",name);}}
void OnStart() {
 Snapshot base;
 base.utc=3600;base.m15=2700;base.o=99;base.h=102;base.l=98;base.c=101;base.prev=100;base.c3=99;
 base.ema=100;base.ema_prev=99.5;base.atr=2;base.rsi=50;base.adx=30;base.plus=25;base.minus=10;
 base.e20=101;base.e50=99;base.a15=3;base.a15mean=3;base.support=90;base.resistance=110;
 base.percentile=.5;base.h1ema=98;base.h1atr=5;base.spread=.1;
 RegimeDetector detector;Check(detector.Update(base)==WAIT,"first close waits");
 Check(detector.Update(base)==WAIT,"same close waits");
 Snapshot next=base;next.m15+=900;Check(detector.Update(next)==TREND_UP,"second close confirms");
 next.adx=22;Check(detector.Update(next)==WAIT,"unsafe resets");
 string header="signal_id,entry,sl,tp";for(int f=0;f<FEATURE_COUNT;f++) header+=","+FeatureNames[f];
 int file=FileOpen("GoldCoreTests.csv",FILE_WRITE|FILE_TXT|FILE_ANSI);
 if(file==INVALID_HANDLE) {Print("FAIL unable to open native fixture export");return;}
 FileWriteString(file,header+"\n");
 for(int i=0;i<6;i++) {
  Snapshot s=base;
  if(i==1) {s.o=102;s.c=99;s.e20=98;s.e50=102;s.plus=10;s.minus=25;}
  if(i==2) {s.adx=15;s.o=90;s.l=89;s.h=92;s.c=90.5;s.rsi=30;}
  if(i==3) {s.adx=15;s.o=110;s.h=111;s.l=108;s.c=109.5;s.rsi=70;}
  if(i==4) {s.adx=15;s.a15mean=5;s.o=109;s.l=109;s.h=111;s.c=110.5;s.spread=0;}
  if(i==5) {s.adx=15;s.a15mean=5;s.o=91;s.h=91;s.l=89;s.c=89.5;s.spread=0;}
  Candidate c;bool ok=Generate(s,RawRegime(s),"XAUUSD",c);
  Check(ok,"scenario "+IntegerToString(i));if(!ok) continue;
  Check(c.direction==(i%2==0 ? 1 : -1),"direction");
  Check((int)c.strategy==i/2+1,"strategy");
  string row=c.id+","+DoubleToString(c.entry,12)+","+DoubleToString(c.sl,12)+","+DoubleToString(c.tp,12);
  for(int f=0;f<FEATURE_COUNT;f++) row+=","+DoubleToString(c.f[f],12);
  FileWriteString(file,row+"\n");
 }
 FileClose(file);
 FlatJson j;Check(!j.Parse("{\"a\":1,\"a\":2}"),"reject duplicate JSON keys");
 Check(!j.Parse("{\"a\":1} trailing"),"reject JSON trailing data");
 Check(!j.Parse("{\"a\":NaN}"),"reject NaN");
 Check(!j.Parse("{\"a\":1e}"),"reject incomplete exponent");
 Check(j.Parse("{\"a\":1.0}") && !j.Integer("a"),"integer field refuses decimals");
 Print("GoldCoreTests failures=",failures," (no orders sent)");
}
