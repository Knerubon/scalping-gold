#property strict
#property script_show_inputs
// Read-only history export. Never submits orders or changes terminal settings.
input string ExportSymbol="XAUUSD";
input datetime FromServer=D'2024.01.01 00:00';
input datetime ToServer=D'2025.01.01 00:00';
input int BrokerUtcOffsetMinutes=0; // split exports at DST offset changes
void OnStart() {
 MqlRates bars[];
 int count=CopyRates(ExportSymbol,PERIOD_M5,FromServer,ToServer,bars);
 if(count<=0) {Print("No history available; download M5 history first");return;}
 double point=SymbolInfoDouble(ExportSymbol,SYMBOL_POINT);
 int digits=(int)SymbolInfoInteger(ExportSymbol,SYMBOL_DIGITS);
 int f=FileOpen("gold-m5.csv",FILE_WRITE|FILE_TXT|FILE_ANSI);
 if(f==INVALID_HANDLE) {Print("Cannot create export");return;}
 FileWriteString(f,"time,open,high,low,close,spread\n");
 for(int i=0;i<count;i++) {
  if(bars[i].time+300>TimeCurrent()) continue;
  datetime utc=bars[i].time-BrokerUtcOffsetMinutes*60;
  string iso=TimeToString(utc,TIME_DATE|TIME_SECONDS);StringReplace(iso,".","-");StringReplace(iso," ","T");
  string row=iso+"Z,"+DoubleToString(bars[i].open,digits)+","+DoubleToString(bars[i].high,digits)+","+DoubleToString(bars[i].low,digits)+","+DoubleToString(bars[i].close,digits)+","+DoubleToString(bars[i].spread*point,digits);
  FileWriteString(f,row+"\n");
 }
 FileClose(f);Print("Exported closed bars to MQL5/Files/gold-m5.csv; verify UTC offsets");
}
