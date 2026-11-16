#ifndef GOLD_JSON_MQH
#define GOLD_JSON_MQH
// Strict flat JSON response parser: no duplicate keys, nested values, escapes or
// trailing bytes. The service response intentionally contains scalar fields only.
class FlatJson {
 private:
 string keys[],values[];
 bool strings[];
 void Space(string s,int &p) {while(p<StringLen(s)) {ushort c=StringGetCharacter(s,p);if(c!=32 && c!=9 && c!=10 && c!=13) break;p++;}}
 bool Quoted(string s,int &p,string &v) {
  if(StringGetCharacter(s,p)!=34) return false;
  p++;v="";
  while(p<StringLen(s)) {
   ushort c=StringGetCharacter(s,p++);
   if(c==34) return true;
   if(c<32 || c==92) return false;
   v+=ShortToString(c);
  }
  return false;
 }
 bool Numeric(string v) {
  int p=0,n=StringLen(v);if(n==0) return false;
  if(StringGetCharacter(v,p)==45) p++;
  if(p>=n) return false;
  ushort ch=StringGetCharacter(v,p);
  if(ch==48) p++;
  else {
   if(ch<49 || ch>57) return false;
   while(p<n && StringGetCharacter(v,p)>=48 && StringGetCharacter(v,p)<=57) p++;
  }
  if(p<n && StringGetCharacter(v,p)==46) {
   p++;int start=p;
   while(p<n && StringGetCharacter(v,p)>=48 && StringGetCharacter(v,p)<=57) p++;
   if(p==start) return false;
  }
  if(p<n && (StringGetCharacter(v,p)==101 || StringGetCharacter(v,p)==69)) {
   p++;if(p<n && (StringGetCharacter(v,p)==43 || StringGetCharacter(v,p)==45)) p++;
   int start=p;
   while(p<n && StringGetCharacter(v,p)>=48 && StringGetCharacter(v,p)<=57) p++;
   if(p==start) return false;
  }
  return p==n && MathIsValidNumber(StringToDouble(v));
 }
 public:
 bool Parse(string s) {
  ArrayResize(keys,0);ArrayResize(values,0);ArrayResize(strings,0);
  int p=0;Space(s,p);if(StringGetCharacter(s,p++)!=123) return false;
  while(p<StringLen(s)) {
   Space(s,p);string key,val;
   if(!Quoted(s,p,key) || Has(key)) return false;
   Space(s,p);if(StringGetCharacter(s,p++)!=58) return false;Space(s,p);
   bool quoted=StringGetCharacter(s,p)==34;
   if(quoted) {if(!Quoted(s,p,val)) return false;}
   else {
    int start=p;
    while(p<StringLen(s) && StringGetCharacter(s,p)!=44 && StringGetCharacter(s,p)!=125) p++;
    val=StringSubstr(s,start,p-start);StringTrimRight(val);
    if(val=="") return false;
    if(!Numeric(val)) return false;
   }
   int n=ArraySize(keys);ArrayResize(keys,n+1);ArrayResize(values,n+1);ArrayResize(strings,n+1);
   keys[n]=key;values[n]=val;strings[n]=quoted;
   Space(s,p);ushort next=StringGetCharacter(s,p++);
   if(next==125) {Space(s,p);return p==StringLen(s);}
   if(next!=44) return false;
  }
  return false;
 }
 bool Has(string key) {for(int i=0;i<ArraySize(keys);i++) if(keys[i]==key) return true;return false;}
 string Text(string key) {for(int i=0;i<ArraySize(keys);i++) if(keys[i]==key && strings[i]) return values[i];return "";}
 double Number(string key) {for(int i=0;i<ArraySize(keys);i++) if(keys[i]==key && !strings[i]) return StringToDouble(values[i]);return EMPTY_VALUE;}
 bool Integer(string key) {
  for(int i=0;i<ArraySize(keys);i++) if(keys[i]==key && !strings[i])
   return StringFind(values[i],".")<0 && StringFind(values[i],"e")<0 && StringFind(values[i],"E")<0;
  return false;
 }
 int Count() {return ArraySize(keys);}
};
#endif
