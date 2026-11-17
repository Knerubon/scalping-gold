#property strict
#property version "1.00"
#property description "Scalping Gold V1. DEMO ONLY. Disabled by default. Research software."
#include "GoldCore.mqh"
#include "GoldJson.mqh"
input bool AUTO_TRADING=false;
input bool EmergencyStop=false;
input string TradeSymbol="XAUUSD";
input ulong Magic=16012026;
input int BrokerUtcOffsetMinutes=0; // REQUIRED: verify broker offset, including DST
input int MaxSpreadPoints=50;
input int MaxDeviationPoints=10;
input double CostAllowancePrice=0.20; // conservative BE allowance; broker calibration required
input string InferenceURL="http://127.0.0.1:8000/score";
input int InferenceTimeoutMs=2000;
input string ApprovedModelVersion="";
input string ApprovedModelHash="";
input bool ExportCandidates=true;
input string ReplayFile=""; // tester-only JSONL; matching signals, UTC-valid decisions

enum ExecutionState { IDLE, CANDIDATE_READY, ML_WAIT, APPROVED, SUBMITTING, OPEN, LOCKED };
ExecutionState state=IDLE;
RegimeDetector detector;
int ema5,atr5,rsi5,ema15,slow15,adx15,atr15,emaH1,atrH1;
datetime lastBar=0,decisionExpiry=0;
string prefix,dayPrefix;
bool recoveryBlocked=false,historyOK=false;
int activeRiskDay=0;

void Log(string event,string reason,string signal="") {
 string row="{\"event\":\""+event+"\",\"reason\":\""+reason+"\",\"signal_id\":\""+signal+"\",\"server_time\":"+IntegerToString((long)TimeCurrent())+",\"state\":"+IntegerToString((int)state)+"}";
 Print(row);
 int f=FileOpen("scalping-gold-events.jsonl",FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
 if(f!=INVALID_HANDLE) {FileSeek(f,0,SEEK_END);FileWriteString(f,row+"\n");FileClose(f);}
}
string StatePrefix() {
 string identity=IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))+"|"+AccountInfoString(ACCOUNT_SERVER)+"|"+TradeSymbol;
 uchar data[],key[],digest[];int n=StringToCharArray(identity,data,0,WHOLE_ARRAY,CP_UTF8);ArrayResize(data,n-1);
 if(CryptEncode(CRYPT_HASH_SHA256,data,key,digest)!=32) return "";
 string hash="";for(int i=0;i<12;i++) hash+=StringFormat("%02x",digest[i]);
 return "SG."+hash+".";
}
bool SafeToken(string value,bool hash=false) {
 for(int i=0;i<StringLen(value);i++) {
  ushort c=StringGetCharacter(value,i);
  if(hash) {if(!((c>=48 && c<=57) || (c>=97 && c<=102))) return false;}
  else if(!((c>=48 && c<=57) || (c>=65 && c<=90) || (c>=97 && c<=122) || c==45 || c==46 || c==95)) return false;
 }
 return true;
}
bool Demo() {return AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO;}
double TickSize() {return SymbolInfoDouble(TradeSymbol,SYMBOL_TRADE_TICK_SIZE);}
double RoundPrice(double price,int direction) {
 double tick=TickSize();if(tick<=0) return 0;
 return NormalizeDouble((direction>0 ? MathFloor(price/tick) : MathCeil(price/tick))*tick,(int)SymbolInfoInteger(TradeSymbol,SYMBOL_DIGITS));
}
string PK(ulong identifier) {return prefix+"p"+IntegerToString((long)identifier)+".";}
bool GV(string key,double value) {return GlobalVariableSet(key,value)!=0;}
double Get(string key) {return GlobalVariableCheck(key) ? GlobalVariableGet(key) : 0;}
int Day(datetime t) {MqlDateTime d;TimeToStruct(t,d);return d.year*10000+d.mon*100+d.day;}
datetime Midnight(datetime t) {MqlDateTime d;TimeToStruct(t,d);d.hour=0;d.min=0;d.sec=0;return StructToTime(d);}
bool HasSymbolExposure() {
 for(int i=PositionsTotal()-1;i>=0;i--) if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==TradeSymbol) return true;
 for(int i=OrdersTotal()-1;i>=0;i--) if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==TradeSymbol) return true;
 return false;
}
bool IsOwned() {return PositionGetString(POSITION_SYMBOL)==TradeSymbol && (ulong)PositionGetInteger(POSITION_MAGIC)==Magic;}
bool PositionStillOpen(ulong identifier) {
 for(int i=PositionsTotal()-1;i>=0;i--) if(PositionGetTicket(i)>0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER)==identifier) return true;
 return false;
}
// Full history reconciles partial exits and includes entry commissions in each result.
bool DailyGuard() {
 datetime now=TimeCurrent(),start=Midnight(now);
 dayPrefix=prefix+"d"+IntegerToString(Day(now))+".";
 if(!HistorySelect(0,now)) {historyOK=false;return false;}
 historyOK=true;
 int count=0,losses=0;bool streakHit=false;
 double dayCash=0;
 ulong opened[],closed[];
 int n=HistoryDealsTotal();
 for(int i=0;i<n;i++) {
  ulong deal=HistoryDealGetTicket(i);
  if(deal==0) return false;
  datetime t=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
  if(t>=start) dayCash+=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_FEE);
  if(HistoryDealGetString(deal,DEAL_SYMBOL)!=TradeSymbol) continue;
  // Account-wide symbol cap, including manually opened trades.
  ulong id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
  long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
  if(t>=start && (entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)) {
   bool seen=false;for(int j=0;j<ArraySize(opened);j++) if(opened[j]==id) seen=true;
   if(!seen) {int k=ArraySize(opened);ArrayResize(opened,k+1);opened[k]=id;count++;}
  }
  if(t<start || (entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY) || PositionStillOpen(id)) continue;
  bool seen=false;for(int j=0;j<ArraySize(closed);j++) if(closed[j]==id) seen=true;
  if(seen) continue;
  // Process only the last exit of each fully closed position, in chronological order.
  bool later=false;
  for(int j=i+1;j<n;j++) {ulong x=HistoryDealGetTicket(j);if((ulong)HistoryDealGetInteger(x,DEAL_POSITION_ID)==id && HistoryDealGetInteger(x,DEAL_ENTRY)!=DEAL_ENTRY_IN) later=true;}
  if(later) continue;
  double net=0;
  for(int j=0;j<n;j++) {ulong x=HistoryDealGetTicket(j);if((ulong)HistoryDealGetInteger(x,DEAL_POSITION_ID)==id) net+=HistoryDealGetDouble(x,DEAL_PROFIT)+HistoryDealGetDouble(x,DEAL_COMMISSION)+HistoryDealGetDouble(x,DEAL_SWAP)+HistoryDealGetDouble(x,DEAL_FEE);}
  losses=net<0 ? losses+1 : 0;if(losses>=3) streakHit=true;
  int k=ArraySize(closed);ArrayResize(closed,k+1);closed[k]=id;
 }
 if(!GlobalVariableCheck(dayPrefix+"equity")) {
  // On first attach mid-day, reconstruct cash balance at midnight only when flat.
  // A carried position's midnight floating PnL cannot be recovered from deal history.
  if(activeRiskDay==0 && PositionsTotal()>0) {GV(dayPrefix+"locked",1);GlobalVariablesFlush();Log("guard","missing_daily_equity_with_exposure");return false;}
  double baseline=activeRiskDay!=0 ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE)-dayCash;
  if(baseline<=0 || !GV(dayPrefix+"equity",baseline)) return false;
 }
 activeRiskDay=Day(now);
 double baseline=Get(dayPrefix+"equity");
 bool locked=Get(dayPrefix+"locked")>0;
 if(AccountInfoDouble(ACCOUNT_EQUITY)<=baseline*.98 || streakHit || count>=5) {
  if(!GV(dayPrefix+"locked",1)) return false;
  locked=true;GlobalVariablesFlush();
 }
 return !locked && baseline>0;
}
bool ConnectedTrade() {
 return Demo() && TerminalInfoInteger(TERMINAL_CONNECTED) && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
}
ENUM_ORDER_TYPE_FILLING Filling() {
 long flags=SymbolInfoInteger(TradeSymbol,SYMBOL_FILLING_MODE);
 if((flags&SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
 if((flags&SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
 return ORDER_FILLING_RETURN;
}
bool StopsValid(int direction,double entry,double sl,double tp,bool modify=false) {
 MqlTick quote;if(!SymbolInfoTick(TradeSymbol,quote)) return false;
 double point=SymbolInfoDouble(TradeSymbol,SYMBOL_POINT);
 double level=SymbolInfoInteger(TradeSymbol,SYMBOL_TRADE_STOPS_LEVEL)*point;
 level=MathMax(level,SymbolInfoInteger(TradeSymbol,SYMBOL_TRADE_FREEZE_LEVEL)*point);
 level=MathMax(level,TickSize());
 double exit=direction==1 ? quote.bid : quote.ask;
 return sl>0 && tp>0 && direction*(entry-sl)>0 && direction*(tp-entry)>0 && direction*(exit-sl)>=level && direction*(tp-exit)>=level;
}
// Recovery uses write-ahead initial SL and strategy. Never derive initial R from
// a trailed SL. Missing journal blocks entries and leaves broker stops untouched.
bool RecoverSelected() {
 ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
 string key=PK(id);
 if(Get(key+"r")>0 && Get(key+"strategy")>=1 && Get(key+"strategy")<=3)
  return MathAbs(Get(key+"entry")-PositionGetDouble(POSITION_PRICE_OPEN))<TickSize()*.5;
 // Finalize immutable R only after every entry order has a terminal history state.
 // This avoids freezing R at an intermediate average during multiple/partial fills.
 if(!HistorySelectByPosition(id)) return false;
 for(int i=0;i<HistoryDealsTotal();i++) {
  ulong deal=HistoryDealGetTicket(i);
  if(HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
  ulong order=(ulong)HistoryDealGetInteger(deal,DEAL_ORDER);
  if(!HistoryOrderSelect(order)) return false;
  long orderState=HistoryOrderGetInteger(order,ORDER_STATE);
  if(orderState!=ORDER_STATE_FILLED && orderState!=ORDER_STATE_CANCELED && orderState!=ORDER_STATE_EXPIRED) return false;
 }
 if(!GlobalVariableCheck(prefix+"pending_time") || Get(prefix+"pending_time")<=0) return false;
 if((datetime)PositionGetInteger(POSITION_TIME)<(datetime)Get(prefix+"pending_time")-5) return false;
 double entry=PositionGetDouble(POSITION_PRICE_OPEN),initialSL=Get(prefix+"pending_sl");
 int d=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1;
 if(initialSL<=0 || d*(entry-initialSL)<=0) return false;
 bool ok=GV(key+"entry",entry) && GV(key+"strategy",Get(prefix+"pending_strategy")) && GV(key+"initial_sl",initialSL) && GV(key+"r",MathAbs(entry-initialSL));
 GlobalVariablesFlush();return ok;
}
void ManagePositions() {
 recoveryBlocked=false;
 for(int i=PositionsTotal()-1;i>=0;i--) {
  ulong ticket=PositionGetTicket(i);if(ticket==0 || !IsOwned()) continue;
  state=OPEN;
  bool recovered=RecoverSelected();
  if(recovered && Get(prefix+"uncertain")>0) {GV(prefix+"uncertain",0);GlobalVariablesFlush();}
  if(!recovered) {recoveryBlocked=true;Log("recovery","missing_immutable_state");}
  ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);string key=PK(id);
  int d=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1;
  Strategy strategy=recovered ? (Strategy)(int)Get(key+"strategy") : NONE;
  double entry=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),r=Get(key+"r");
  datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
  MqlTick q;if(!SymbolInfoTick(TradeSymbol,q)) continue;
  double price=d==1 ? q.bid : q.ask;
  // No new request on a non-demo account, including exits/modifications.
  if(!ConnectedTrade()) continue;
  MqlTradeRequest req={};MqlTradeResult result={};
  if(sl<=0 || tp<=0 || TimeCurrent()-opened>=(strategy==BREAK ? 90 : 60)*60) {
   if(sl<=0 || tp<=0) recoveryBlocked=true;
   req.action=TRADE_ACTION_DEAL;req.symbol=TradeSymbol;req.magic=Magic;req.position=ticket;
   req.type=d==1 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;req.volume=PositionGetDouble(POSITION_VOLUME);
   req.price=price;req.deviation=MaxDeviationPoints;req.type_filling=Filling();req.comment="SG time exit";
   if(!Demo()) continue;
   bool sent=OrderSend(req,result);
   Log(sl<=0 || tp<=0 ? "protection_emergency_exit" : "time_exit",IntegerToString((long)result.retcode)+(sent ? "_sent" : "_failed"));continue;
  }
  if(!recovered) continue; // broker protection and conservative 60-minute exit remain active
  double a[];if(CopyBuffer(atr5,0,1,1,a)!=1 || a[0]<=0) continue;
  double proposed=sl,profit=d*(price-entry);
  double targetTP=strategy==REVERSAL ? tp : RoundPrice(entry+d*r*(strategy==BREAK ? 2.5 : 2),-d);
  bool targetChanged=MathAbs(targetTP-tp)>=TickSize()*.5;
  if(profit>=(strategy==REVERSAL ? .8 : 1)*r) {
   double be=entry+d*CostAllowancePrice;
   proposed=d==1 ? MathMax(proposed,be) : (proposed<=0 ? be : MathMin(proposed,be));
  }
  if(strategy!=REVERSAL && profit>=1.5*r) {
   double trail=price-d*a[0]*(strategy==BREAK ? 1.2 : 1);
   proposed=d==1 ? MathMax(proposed,trail) : (proposed<=0 ? trail : MathMin(proposed,trail));
  }
  proposed=RoundPrice(proposed,d);
  if(sl<=0 || tp<=0) {recoveryBlocked=true;Log("guard","missing_broker_protection");}
  bool stopChanged=d*(proposed-sl)>=MathMax(.2*a[0],TickSize());
  if(!stopChanged) proposed=sl;
  if(!stopChanged && !targetChanged) continue;
  // Modifications may pass actual entry after BE; validate against current quote.
  double level=MathMax(SymbolInfoInteger(TradeSymbol,SYMBOL_TRADE_STOPS_LEVEL),SymbolInfoInteger(TradeSymbol,SYMBOL_TRADE_FREEZE_LEVEL))*SymbolInfoDouble(TradeSymbol,SYMBOL_POINT);
  if(d*(price-proposed)<MathMax(level,TickSize()) || targetTP<=0 || d*(targetTP-price)<level) continue;
  req.action=TRADE_ACTION_SLTP;req.symbol=TradeSymbol;req.magic=Magic;req.position=ticket;req.sl=proposed;req.tp=targetTP;
  if(!Demo()) continue;
  bool sent=OrderSend(req,result);
  Log("stop_update",IntegerToString((long)result.retcode)+(sent ? "_sent" : "_failed"));
 }
}
bool Value(int handle,int buffer,int shift,double &value) {
 double a[];if(CopyBuffer(handle,buffer,shift,1,a)!=1 || !MathIsValidNumber(a[0]) || a[0]==EMPTY_VALUE) return false;
 value=a[0];return true;
}
bool LoadSnapshot(Snapshot &s) {
 if(Bars(TradeSymbol,PERIOD_M5)<251 || Bars(TradeSymbol,PERIOD_M15)<251 || Bars(TradeSymbol,PERIOD_H1)<251) return false;
 if(!SeriesInfoInteger(TradeSymbol,PERIOD_M5,SERIES_SYNCHRONIZED) || !SeriesInfoInteger(TradeSymbol,PERIOD_M15,SERIES_SYNCHRONIZED) || !SeriesInfoInteger(TradeSymbol,PERIOD_H1,SERIES_SYNCHRONIZED)) return false;
 MqlRates bars[];ArraySetAsSeries(bars,true);
 if(CopyRates(TradeSymbol,PERIOD_M5,1,4,bars)!=4) return false;
 datetime close=bars[0].time+300;
 s.utc=close-BrokerUtcOffsetMinutes*60;
 int m=iBarShift(TradeSymbol,PERIOD_M15,close-900,false);
 int h=iBarShift(TradeSymbol,PERIOD_H1,close-3600,false);
 if(m<1 || h<1 || iTime(TradeSymbol,PERIOD_M15,m)+900>close || iTime(TradeSymbol,PERIOD_H1,h)+3600>close) return false;
 if(close-(iTime(TradeSymbol,PERIOD_M15,m)+900)>=900 || close-(iTime(TradeSymbol,PERIOD_H1,h)+3600)>=3600) return false;
 s.m15=iTime(TradeSymbol,PERIOD_M15,m)+900;
 s.o=bars[0].open;s.h=bars[0].high;s.l=bars[0].low;s.c=bars[0].close;s.prev=bars[1].close;s.c3=bars[3].close;
 s.spread=bars[0].spread*SymbolInfoDouble(TradeSymbol,SYMBOL_POINT);
 if(!Value(ema5,0,1,s.ema) || !Value(ema5,0,2,s.ema_prev) || !Value(atr5,0,1,s.atr) || !Value(rsi5,0,1,s.rsi) || !Value(ema15,0,m,s.e20) || !Value(slow15,0,m,s.e50) || !Value(adx15,0,m,s.adx) || !Value(adx15,1,m,s.plus) || !Value(adx15,2,m,s.minus) || !Value(atr15,0,m,s.a15) || !Value(emaH1,0,h,s.h1ema) || !Value(atrH1,0,h,s.h1atr)) return false;
 double values[];if(CopyBuffer(atr15,0,m+1,50,values)!=50) return false;
 s.a15mean=0;for(int i=0;i<50;i++) s.a15mean+=values[i]/50;
 if(CopyBuffer(atr5,0,2,100,values)!=100) return false;
 s.percentile=0;for(int i=0;i<100;i++) if(values[i]<=s.atr) s.percentile+=.01;
 MqlRates range[];
 // Exclude M15 bar containing the signal; range ends at or before M5 open.
 int rangeShift=iBarShift(TradeSymbol,PERIOD_M15,bars[0].time-900,false);
 if(rangeShift<1 || CopyRates(TradeSymbol,PERIOD_M15,rangeShift,20,range)!=20) return false;
 s.support=DBL_MAX;s.resistance=-DBL_MAX;
 for(int i=0;i<20;i++) {s.support=MathMin(s.support,range[i].low);s.resistance=MathMax(s.resistance,range[i].high);}
 return s.atr>0 && s.a15>0 && s.a15mean>0 && s.h1atr>0 && s.prev>0 && s.c3>0;
}
string RequestJSON(const Candidate &c) {
 string f="{";
 for(int i=0;i<FEATURE_COUNT;i++) {if(i>0) f+=",";f+="\""+FeatureNames[i]+"\":"+DoubleToString(c.f[i],12);}
 f+="}";
 return "{\"schema_version\":\"1\",\"signal_id\":\""+c.id+"\",\"symbol\":\""+TradeSymbol+"\",\"strategy_id\":\""+StrategyName(c.strategy)+"\",\"direction\":"+IntegerToString(c.direction)+",\"closed_bar_utc\":"+IntegerToString((long)c.utc)+",\"feature_version\":\""+FEATURE_VERSION+"\",\"feature_hash\":\""+FEATURE_HASH+"\",\"model_version\":\""+ApprovedModelVersion+"\",\"model_hash\":\""+ApprovedModelHash+"\",\"timestamp\":"+IntegerToString((long)(TimeCurrent()-BrokerUtcOffsetMinutes*60))+",\"expires_at\":"+IntegerToString((long)(c.utc+300))+",\"features\":"+f+"}";
}
void Export(const Candidate &c,string request) {
 if(!ExportCandidates) return;
 int f=FileOpen("scalping-gold-candidates.jsonl",FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
 if(f==INVALID_HANDLE) {Log("export","file_open_failed",c.id);return;}
 FileSeek(f,0,SEEK_END);FileWriteString(f,request+"\n");FileClose(f);
 int plans=FileOpen("scalping-gold-plans.jsonl",FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
 if(plans==INVALID_HANDLE) {Log("export","plan_open_failed",c.id);return;}
 string plan="{\"signal_id\":\""+c.id+"\",\"entry\":"+DoubleToString(c.entry,12)+",\"sl\":"+DoubleToString(c.sl,12)+",\"tp\":"+DoubleToString(c.tp,12)+",\"request\":"+request+"}";
 FileSeek(plans,0,SEEK_END);FileWriteString(plans,plan+"\n");FileClose(plans);
}
bool ValidateResponse(string body,const Candidate &c,datetime now) {
 FlatJson j;if(!j.Parse(body) || j.Count()!=18) return false;
 if(!j.Integer("direction") || !j.Integer("closed_bar_utc") || !j.Integer("timestamp") || !j.Integer("expires_at")) return false;
 if(j.Text("schema_version")!="1" || j.Text("signal_id")!=c.id || j.Text("symbol")!=TradeSymbol || j.Text("strategy_id")!=StrategyName(c.strategy) || j.Number("direction")!=c.direction || j.Number("closed_bar_utc")!=(double)c.utc) return false;
 if(j.Text("feature_version")!=FEATURE_VERSION || j.Text("feature_hash")!=FEATURE_HASH || j.Text("model_version")!=ApprovedModelVersion || j.Text("model_hash")!=ApprovedModelHash) return false;
 double timestamp=j.Number("timestamp"),expiry=j.Number("expires_at");
 if(timestamp>now+2 || timestamp<now-5 || expiry<=now || expiry>c.utc+300 || expiry<=timestamp) return false;
 double win=j.Number("p_win"),loss=j.Number("p_loss"),timeout=j.Number("p_timeout"),er=j.Number("estimated_net_r");
 if(!MathIsValidNumber(win) || !MathIsValidNumber(loss) || !MathIsValidNumber(timeout) || !MathIsValidNumber(er) || MathAbs(er)>100 || win<0 || loss<0 || timeout<0 || win>1 || loss>1 || timeout>1 || MathAbs(win+loss+timeout-1)>1e-6) return false;
 string reason=j.Text("reason_code");if(reason=="") return false;
 for(int i=0;i<StringLen(reason);i++) {
  ushort ch=StringGetCharacter(reason,i);
  if(!((ch>=97 && ch<=122) || (ch>=48 && ch<=57) || ch==95)) return false;
 }
 if(j.Text("decision")!="APPROVE") return false;
 decisionExpiry=(datetime)expiry;return true;
}
bool Score(const Candidate &c,string request) {
 decisionExpiry=0;
 if(ApprovedModelVersion=="" || StringLen(ApprovedModelHash)!=64) return false;
 datetime now=TimeCurrent()-BrokerUtcOffsetMinutes*60;
 if(MQLInfoInteger(MQL_TESTER)) {
  if(ReplayFile=="") return false;
  int f=FileOpen(ReplayFile,FILE_READ|FILE_TXT|FILE_ANSI);
  if(f==INVALID_HANDLE) return false;
  bool approved=false;
  while(!FileIsEnding(f)) {string line=FileReadString(f);FlatJson j;if(j.Parse(line) && j.Text("signal_id")==c.id) {approved=ValidateResponse(line,c,now);break;}}
  FileClose(f);return approved;
 }
 char data[],response[];string headers;
 int bytes=StringToCharArray(request,data,0,WHOLE_ARRAY,CP_UTF8);ArrayResize(data,bytes-1);
 ulong started=GetTickCount64();
 int status=WebRequest("POST",InferenceURL,"Content-Type: application/json\r\n",InferenceTimeoutMs,data,response,headers);
 if(status!=200 || GetTickCount64()-started>(ulong)InferenceTimeoutMs) {Log("inference","http_timeout_or_error",c.id);return false;}
 return ValidateResponse(CharArrayToString(response,0,-1,CP_UTF8),c,TimeCurrent()-BrokerUtcOffsetMinutes*60);
}
void Execute(Candidate &c) {
 if(!AUTO_TRADING || EmergencyStop || !ConnectedTrade() || recoveryBlocked || !DailyGuard() || HasSymbolExposure()) {state=LOCKED;Log("guard","entry_blocked",c.id);return;}
 MqlTick q;if(!SymbolInfoTick(TradeSymbol,q) || q.ask<=q.bid || TimeCurrent()-q.time>5) return;
 double point=SymbolInfoDouble(TradeSymbol,SYMBOL_POINT);
 if((q.ask-q.bid)/point>MaxSpreadPoints) return;
 if(SymbolInfoInteger(TradeSymbol,SYMBOL_TRADE_MODE)!=SYMBOL_TRADE_MODE_FULL) return;
 long modes=SymbolInfoInteger(TradeSymbol,SYMBOL_ORDER_MODE);
 if((modes&SYMBOL_ORDER_SL)==0 || (modes&SYMBOL_ORDER_TP)==0 || (modes&SYMBOL_ORDER_MARKET)==0) return;
 double entry=c.direction==1 ? q.ask : q.bid;
 // Revalidate current quote after ML latency; never chase the approved candidate.
 double atr[];if(CopyBuffer(atr5,0,1,1,atr)!=1 || MathAbs(entry-c.entry)>.5*atr[0]) return;
 if(c.strategy==BREAK && c.direction*(entry-c.boundary)>.5*atr[0]) return;
 c.sl=RoundPrice(c.sl,c.direction);
 if(c.strategy!=REVERSAL) c.tp=entry+c.direction*MathAbs(entry-c.sl)*(c.strategy==BREAK ? 2.5 : 2);
 c.tp=RoundPrice(c.tp,-c.direction);
 if(!StopsValid(c.direction,entry,c.sl,c.tp) || MathAbs(c.tp-entry)/MathAbs(entry-c.sl)<1.5) return;
 ENUM_ORDER_TYPE type=c.direction==1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
 double loss=0;
 if(!OrderCalcProfit(type,TradeSymbol,1,entry,c.sl,loss) || loss>=0) return;
 double step=SymbolInfoDouble(TradeSymbol,SYMBOL_VOLUME_STEP),minimum=SymbolInfoDouble(TradeSymbol,SYMBOL_VOLUME_MIN);
 if(step<=0 || minimum<=0) return;
 double volume=MathFloor(MathMin(AccountInfoDouble(ACCOUNT_EQUITY)*.005/MathAbs(loss),SymbolInfoDouble(TradeSymbol,SYMBOL_VOLUME_MAX))/step)*step;
 volume=NormalizeDouble(volume,8);if(volume<minimum) return;
 double margin=0;if(!OrderCalcMargin(type,TradeSymbol,volume,entry,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*.9) return;
 MqlTradeRequest req={};MqlTradeResult result={};MqlTradeCheckResult check={};
 req.action=TRADE_ACTION_DEAL;req.magic=Magic;req.symbol=TradeSymbol;req.volume=volume;req.type=type;req.price=entry;
 req.sl=c.sl;req.tp=c.tp;req.deviation=MaxDeviationPoints;req.type_filling=Filling();req.comment="SG-"+IntegerToString((int)c.strategy);
 if(!OrderCheck(req,check) || (check.retcode!=0 && check.retcode!=TRADE_RETCODE_DONE)) {Log("check",IntegerToString(check.retcode),c.id);return;}
 // Write-ahead journal plus per-symbol account mutex. A crash/ambiguous response
 // burns this bar rather than risking duplicate submission.
 string mutex=prefix+"mutex";
 if(!GlobalVariableSetOnCondition(mutex,(double)TimeCurrent(),0)) return;
 if(Get(prefix+"uncertain")>0 || HasSymbolExposure() || Get(prefix+"last_signal")>=(double)c.utc) {GlobalVariableSet(mutex,0);return;}
 bool persisted=GV(prefix+"pending_sl",c.sl) && GV(prefix+"pending_strategy",(double)c.strategy) && GV(prefix+"pending_time",(double)TimeCurrent()) && GV(prefix+"last_signal",(double)c.utc);
 GlobalVariablesFlush();
 if(!persisted || !Demo() || !DailyGuard() || TimeCurrent()-BrokerUtcOffsetMinutes*60>=decisionExpiry) {GlobalVariableSet(mutex,0);return;}
 state=SUBMITTING;
 if(!GV(prefix+"uncertain",1)) {GlobalVariableSet(mutex,0);return;}
 GlobalVariablesFlush();
 bool sent=OrderSend(req,result);
 Log("order",IntegerToString((long)result.retcode)+(sent ? "_sent" : "_failed"),c.id);
 // DONE_PARTIAL/PLACED are reconciled as exposure; never resubmit remaining volume.
 // Ambiguous timeout/connection status permanently locks new entries for operator reconciliation.
 if(sent && (result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_DONE_PARTIAL)) GV(prefix+"uncertain",0);
 if(result.retcode!=TRADE_RETCODE_DONE && result.retcode!=TRADE_RETCODE_DONE_PARTIAL && result.retcode!=TRADE_RETCODE_PLACED) state=LOCKED;
 ManagePositions();GlobalVariableSet(mutex,0);GlobalVariablesFlush();
}
int OnInit() {
 if(!Demo()) {Print("DEMO account required; REAL and CONTEST are rejected");return INIT_FAILED;}
 if(_Symbol!=TradeSymbol || _Period!=PERIOD_M5 || StringFind(TradeSymbol,"XAUUSD")!=0 || !SymbolSelect(TradeSymbol,true) || MaxSpreadPoints<=0 || MaxDeviationPoints<0 || CostAllowancePrice<0 || InferenceTimeoutMs<1 || InferenceTimeoutMs>2000 || MathAbs(BrokerUtcOffsetMinutes)>840) return INIT_PARAMETERS_INCORRECT;
 if(StringFind(InferenceURL,"http://127.0.0.1:")!=0) return INIT_PARAMETERS_INCORRECT;
 if(!SafeToken(TradeSymbol) || !SafeToken(ApprovedModelVersion) || !SafeToken(ApprovedModelHash,true)) return INIT_PARAMETERS_INCORRECT;
 prefix=StatePrefix();if(prefix=="") return INIT_FAILED;
 // Atomic create-if-absent; temp mutex is not overwritten by another chart.
 if(!GlobalVariableTemp(prefix+"mutex")) return INIT_FAILED;
 // Never clear a stale mutex automatically: operator must reconcile terminal,
 // broker positions/orders and journal before reset. Position management continues.
 ema5=iMA(TradeSymbol,PERIOD_M5,20,0,MODE_EMA,PRICE_CLOSE);atr5=iATR(TradeSymbol,PERIOD_M5,14);rsi5=iRSI(TradeSymbol,PERIOD_M5,14,PRICE_CLOSE);
 ema15=iMA(TradeSymbol,PERIOD_M15,20,0,MODE_EMA,PRICE_CLOSE);slow15=iMA(TradeSymbol,PERIOD_M15,50,0,MODE_EMA,PRICE_CLOSE);
 adx15=iADXWilder(TradeSymbol,PERIOD_M15,14);atr15=iATR(TradeSymbol,PERIOD_M15,14);
 emaH1=iMA(TradeSymbol,PERIOD_H1,20,0,MODE_EMA,PRICE_CLOSE);atrH1=iATR(TradeSymbol,PERIOD_H1,14);
 if(ema5==INVALID_HANDLE || atr5==INVALID_HANDLE || rsi5==INVALID_HANDLE || ema15==INVALID_HANDLE || slow15==INVALID_HANDLE || adx15==INVALID_HANDLE || atr15==INVALID_HANDLE || emaH1==INVALID_HANDLE || atrH1==INVALID_HANDLE) return INIT_FAILED;
 DailyGuard();ManagePositions();Log("startup",AUTO_TRADING ? "demo_execution_configured" : "shadow_disabled");return INIT_SUCCEEDED;
}
void OnTick() {
 if(!Demo()) {state=LOCKED;return;}
 ManagePositions(); // independent of inference and entry enable switch
 DailyGuard(); // observe floating drawdown even while a position is open
 bool exposed=HasSymbolExposure() || recoveryBlocked;
 datetime bar=iTime(TradeSymbol,PERIOD_M5,0);if(bar<=0 || bar==lastBar) return;
 Snapshot s;if(!LoadSnapshot(s)) {Log("data","not_ready");return;}
 lastBar=bar;
 Candidate c;Regime regime=detector.Update(s);if(!Generate(s,regime,TradeSymbol,c)) return;
 if(Get(prefix+"last_signal")>=(double)c.utc) return;
 state=CANDIDATE_READY;string request=RequestJSON(c);Export(c,request);
 if(exposed) {state=OPEN;return;} // keep regime/candidate history live, never submit while exposed
 state=ML_WAIT;
 if(!Score(c,request)) {state=IDLE;Log("inference","abstain_or_reject",c.id);return;}
 state=APPROVED;Execute(c);if(!HasSymbolExposure() && state!=LOCKED) state=IDLE;
}
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result) {
 if(!Demo()) return;
 ManagePositions();DailyGuard();
}
void OnDeinit(const int reason) {
 IndicatorRelease(ema5);IndicatorRelease(atr5);IndicatorRelease(rsi5);IndicatorRelease(ema15);IndicatorRelease(slow15);IndicatorRelease(adx15);IndicatorRelease(atr15);IndicatorRelease(emaH1);IndicatorRelease(atrH1);
 GlobalVariablesFlush();
}
