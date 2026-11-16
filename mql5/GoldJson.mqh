#ifndef GOLD_JSON_MQH
#define GOLD_JSON_MQH
// Strict flat JSON response parser: no duplicate keys, nested values, escapes or
// trailing bytes. The service response intentionally contains scalar fields only.
class FlatJson {
 private:
 string keys[],values[];
 bool strings[];
 void Space(string s,int &p) {while(p<StringLen(s) && StringGetCharacter(s,p)<=32) p++;}
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
    // Only canonical JSON numbers accepted, finite checks in Number().
    bool digit=false;
    for(int k=0;k<StringLen(val);k++) {
     ushort ch=StringGetCharacter(val,k);
     if(ch>=48 && ch<=57) digit=true;
     else if(ch!=45 && ch!=43 && ch!=46 && ch!=101 && ch!=69) return false;
    }
    if(!digit) return false;
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
 int Count() {return ArraySize(keys);}
};
#endif
