import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';

/// Broker-only Order Flow. Demo/sample prices are rejected, never rendered.
class OrderFlowPage extends StatefulWidget {
  const OrderFlowPage({required this.signalBackendUrl, super.key});
  final String signalBackendUrl;
  @override
  State<OrderFlowPage> createState() => _OrderFlowPageState();
}

class _OrderFlowPageState extends State<OrderFlowPage> {
  static const green=Color(0xFF26C281), red=Color(0xFFEF4B5B), amber=Color(0xFFF0B429);
  static const symbols=['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX','BANKEX'];
  static const frames=<int,String>{1:'1m',3:'3m',5:'5m',15:'15m',30:'30m',60:'1h'};
  String symbol='NIFTY', status='CONNECTING', error='';
  int timeframe=1, zoom=0;
  WebSocket? socket;
  Timer? retry;
  bool disposed=false;
  List<Map<String,dynamic>> candles=[];
  double n(dynamic v)=>v is num?v.toDouble():double.tryParse(v.toString())??0;

  Uri get uri {
    final base=Uri.parse(widget.signalBackendUrl);
    return base.replace(scheme:base.scheme=='https'?'wss':'ws',path:'/ws',queryParameters:{'symbol':symbol});
  }

  @override
  void initState(){super.initState();connect();}

  Future<void> connect() async {
    retry?.cancel();
    final old=socket; socket=null; await old?.close();
    if(disposed)return;
    if(mounted)setState((){status='CONNECTING';error='';});
    try{
      final ws=await WebSocket.connect(uri.toString()).timeout(const Duration(seconds:8));
      if(disposed){await ws.close();return;}
      socket=ws;
      ws.listen((event){
        try{
          final raw=jsonDecode(event is String?event:utf8.decode(event as List<int>));
          if(raw is! Map)return;
          final mode=(raw['mode']??'WAIT').toString().toUpperCase();
          if(mode=='DEMO'||mode.contains('SAMPLE')){
            if(mounted)setState((){status='DEMO BLOCKED';error='Demo feed blocked. Connect Angel One for broker data.';candles=[];});
            return;
          }
          final next=List<Map<String,dynamic>>.from(candles);
          if(raw['type']=='snap'&&raw['candles'] is List){
            next..clear()..addAll((raw['candles'] as List).whereType<Map>().map((e)=>Map<String,dynamic>.from(e)));
          }else if(raw['candle'] is Map){
            final c=Map<String,dynamic>.from(raw['candle'] as Map);
            final i=next.indexWhere((e)=>e['t']==c['t']);
            if(i>=0){next[i]=c;}else{next.add(c);}
          }else if(raw['type']=='status'&&raw['candles'] is List){
            next..clear()..addAll((raw['candles'] as List).whereType<Map>().map((e)=>Map<String,dynamic>.from(e)));
          }
          next.sort((a,b)=>n(a['t']).compareTo(n(b['t'])));
          if(next.length>250)next.removeRange(0,next.length-250);
          if(mounted)setState((){
            candles=next;
            status=mode=='LIVE'&&raw['live']==true?'LIVE':mode;
            error=status=='LIVE'?'':(raw['message']??'Waiting for fresh broker timestamp.').toString();
          });
        }catch(_){if(mounted)setState((){status='DATA ERROR';error='Invalid backend message; no sample prices are shown.';});}
      },onDone:scheduleRetry,onError:(_){if(mounted)setState(()=>status='DISCONNECTED');scheduleRetry();});
    }catch(_){
      if(mounted)setState((){status='DISCONNECTED';error='WebSocket /ws unavailable. Check signal backend and Angel One feed.';});
      scheduleRetry();
    }
  }

  void scheduleRetry(){if(disposed)return;retry?.cancel();retry=Timer(const Duration(seconds:3),connect);}

  List<Map<String,dynamic>> get visibleCandles {
    if(timeframe==1)return candles;
    final groups=<int,Map<String,dynamic>>{};
    for(final c in candles){
      final t=n(c['t']).toInt(); if(t<=0)continue;
      final key=t~/(timeframe*60)*(timeframe*60);
      final a=groups.putIfAbsent(key,()=>{'t':key,'o':n(c['o']),'h':n(c['h']),'l':n(c['l']),'c':n(c['c']),'v':0.0,'d':0.0,'bo':0,'so':0,'lv':<String,List<double>>{}});
      a['h']=[n(a['h']),n(c['h'])].reduce((x,y)=>x>y?x:y);
      a['l']=[n(a['l']),n(c['l'])].reduce((x,y)=>x<y?x:y);
      a['c']=n(c['c']); a['v']=n(a['v'])+n(c['v']); a['d']=n(a['d'])+n(c['d']);
      a['bo']=n(c['bo']).toInt();a['so']=n(c['so']).toInt();
      final lv=c['lv'];
      if(lv is Map){
        final merged=Map<String,List<double>>.from(a['lv'] as Map);
        for(final e in lv.entries){final pair=e.value;if(pair is List&&pair.length>=2){final p=merged[e.key.toString()]??<double>[0,0];merged[e.key.toString()]=[p[0]+n(pair[0]),p[1]+n(pair[1])];}}
        a['lv']=merged;
      }
    }
    return groups.values.toList()..sort((a,b)=>n(a['t']).compareTo(n(b['t'])));
  }

  @override
  void dispose(){disposed=true;retry?.cancel();socket?.close();super.dispose();}

  @override
  Widget build(BuildContext context){
    final data=visibleCandles, last=data.isEmpty?null:data.last, live=status=='LIVE';
    return Scaffold(backgroundColor:const Color(0xFF0B0F14),body:SafeArea(child:Column(children:[
      Padding(padding:const EdgeInsets.fromLTRB(8,5,8,5),child:Row(children:[
        Expanded(child:DropdownButtonHideUnderline(child:DropdownButton<String>(isExpanded:true,value:symbol,dropdownColor:const Color(0xFF121821),items:symbols.map((s)=>DropdownMenuItem(value:s,child:Text(s))).toList(),onChanged:(v){if(v!=null)setState((){symbol=v;candles=[];});connect();}))),
        DropdownButtonHideUnderline(child:DropdownButton<int>(value:timeframe,dropdownColor:const Color(0xFF121821),items:frames.entries.map((e)=>DropdownMenuItem(value:e.key,child:Text(e.value))).toList(),onChanged:(v){if(v!=null)setState(()=>timeframe=v);})),
        IconButton(tooltip:'Zoom out',onPressed:()=>setState(()=>zoom=(zoom-1).clamp(-4,8)),icon:const Icon(Icons.remove)),
        IconButton(tooltip:'Zoom in',onPressed:()=>setState(()=>zoom=(zoom+1).clamp(-4,8)),icon:const Icon(Icons.add)),
        IconButton(tooltip:'Live / reconnect',onPressed:connect,icon:const Icon(Icons.refresh)),
        IconButton(tooltip:'Manual',onPressed:()=>showDialog<void>(context:context,builder:(c)=>AlertDialog(title:const Text('Order Flow / Footprint'),content:const SingleChildScrollView(child:Text('Cell = Sell × Buy. Green means bid/ask buy quantity is higher; red means sell quantity is higher. Yellow outline marks POC; bold cells require 3× imbalance. Delta = Buy − Sell. Live status requires a fresh broker timestamp. If the backend sends aggregate top-five depth only, price-level cells cannot be computed and are intentionally not fabricated.')),actions:[TextButton(onPressed:()=>Navigator.pop(c),child:const Text('Close'))])),icon:const Icon(Icons.help_outline)),
        Container(padding:const EdgeInsets.symmetric(horizontal:7,vertical:4),decoration:BoxDecoration(color:live?const Color(0xFF12432E):const Color(0xFF333333),borderRadius:BorderRadius.circular(16)),child:Text(status,style:TextStyle(fontSize:9,fontWeight:FontWeight.bold,color:live?green:Colors.orangeAccent))),
      ])),
      Container(width:double.infinity,padding:const EdgeInsets.symmetric(horizontal:8,vertical:5),decoration:const BoxDecoration(border:Border(bottom:BorderSide(color:Color(0xFF1F2733)))),child:SingleChildScrollView(scrollDirection:Axis.horizontal,child:Row(children:[
        _stat('LTP',last==null?'—':n(last['c']).toStringAsFixed(2)),
        _stat('Δ',last==null?'—':n(last['d']).toStringAsFixed(0),last==null?Colors.white:n(last['d'])>=0?green:red),
        _stat('Vol',last==null?'—':n(last['v']).toStringAsFixed(0)),
        _stat('Buy ord',last==null?'—':n(last['bo']).toInt().toString(),green),
        _stat('Sell ord',last==null?'—':n(last['so']).toInt().toString(),red),
        _stat('TF',frames[timeframe]!),
      ]))),
      if(error.isNotEmpty)Padding(padding:const EdgeInsets.symmetric(horizontal:8,vertical:3),child:Text(error,style:const TextStyle(color:Colors.orangeAccent,fontSize:10),maxLines:2,overflow:TextOverflow.ellipsis)),
      Expanded(child:Container(margin:const EdgeInsets.all(4),decoration:BoxDecoration(color:const Color(0xFF121821),border:Border.all(color:const Color(0xFF1F2733))),child:data.isEmpty?const Center(child:Text('Waiting for fresh Angel One snapshots.\nNo demo prices or synthetic footprint cells.',textAlign:TextAlign.center,style:TextStyle(color:Color(0xFF7D8896)))):CustomPaint(painter:FootprintPainter(data,zoom:zoom),child:const SizedBox.expand()))),
      const Padding(padding:EdgeInsets.fromLTRB(8,2,8,8),child:Text('Depth/delta are bid/ask book quantities, not classified exchange aggressor volume. Real price-level cells require depth levels in the backend payload.',style:TextStyle(color:Color(0xFF7D8896),fontSize:10))),
    ])));
  }

  Widget _stat(String label,String value,[Color color=Colors.white])=>Padding(padding:const EdgeInsets.only(right:13),child:RichText(text:TextSpan(style:const TextStyle(fontSize:11,color:Color(0xFF7D8896)),children:[TextSpan(text:label+' '),TextSpan(text:value,style:TextStyle(color:color,fontWeight:FontWeight.bold))])));
}

class FootprintPainter extends CustomPainter {
  FootprintPainter(this.candles,{required this.zoom});
  final List<Map<String,dynamic>> candles; final int zoom;
  double n(dynamic v)=>v is num?v.toDouble():double.tryParse(v.toString())??0;
  String fmt(double x){final a=x.abs();if(a>=1e7)return (x/1e7).toStringAsFixed(2)+'Cr';if(a>=1e5)return (x/1e5).toStringAsFixed(1)+'L';if(a>=1e3)return (x/1e3).toStringAsFixed(1)+'k';return x.round().toString();}
  @override
  void paint(Canvas canvas,Size size){
    if(candles.isEmpty||size.width<=0||size.height<=0)return;
    final hasLevels=candles.any((c)=>c['lv'] is Map&&(c['lv'] as Map).isNotEmpty);
    final double cw=(100.0+zoom*8).clamp(64.0,180.0).toDouble(); final int count=(size.width/cw).floor().clamp(1,60).toInt();
    final vis=candles.length>count?candles.sublist(candles.length-count):candles;
    final lo=vis.map((c)=>n(c['l'])).reduce((a,b)=>a<b?a:b), hi=vis.map((c)=>n(c['h'])).reduce((a,b)=>a>b?a:b);
    final step=vis.map((c)=>n(c['step'])).firstWhere((v)=>v>0,orElse:()=>1.0);
    final low=(lo/step).floor()*step-step, high=(hi/step).ceil()*step+step;
    const top=20.0,bottom=54.0;final plot=(size.height-top-bottom).clamp(1.0,size.height).toDouble();
    final int rows=((high-low)/step).ceil().clamp(1,500).toInt(); final double rh=plot/rows;
    final maxVol=vis.fold<double>(1,(m,c){final lv=c['lv'];if(lv is Map){for(final v in lv.values){if(v is List&&v.length>=2){final total=n(v[0])+n(v[1]);if(total>m)m=total;}}}return m;});
    final grid=Paint()..color=const Color(0xFF26313E)..strokeWidth=.5;
    for(var r=0;r<=rows;r++){final y=top+r*rh;canvas.drawLine(Offset(0,y),Offset(size.width-45,y),grid);}
    final axis=TextPainter(textDirection:TextDirection.ltr);
    final int skip=(rows/12).ceil().clamp(1,100).toInt();
    for(var r=0;r<=rows;r+=skip){final p=high-r*step;axis.text=TextSpan(text:p.toStringAsFixed(p.abs()<100?2:0),style:const TextStyle(color:Color(0xFF7D8896),fontSize:9));axis.layout();axis.paint(canvas,Offset(size.width-42,top+r*rh));}
    for(var i=0;i<vis.length;i++){
      final c=vis[i], x=i*cw+8, w=cw-12, lv=c['lv'];double y(double p)=>top+(high-p)/step*rh;
      final keys=lv is Map?lv.keys.map((k)=>double.tryParse(k.toString())).whereType<double>().toList() : <double>[];
      keys.sort((a,b)=>b.compareTo(a));double poc=-1,pocVol=-1;
      for(final p in keys){
        final pair=(lv as Map)[p.toString()]??(lv as Map)[p.toStringAsFixed(2)]??(lv as Map)[p.toStringAsFixed(1)];
        if(pair is! List||pair.length<2)continue;
        final sell=n(pair[0]),buy=n(pair[1]),total=sell+buy;if(total>pocVol){pocVol=total;poc=p;}
        final yy=y(p);if(yy<top-rh||yy>top+plot)continue;
        canvas.drawRect(Rect.fromLTWH(x,yy,w,rh.clamp(1.0,100.0)),Paint()..color=(buy>=sell?green:red).withValues(alpha:(.12+.65*total/maxVol).clamp(.12,.77)));
        if(rh>=10&&cw>=76){
          final st=TextPainter(textDirection:TextDirection.ltr)..text=TextSpan(text:fmt(sell),style:TextStyle(color:red,fontSize:9,fontWeight:sell>=3*_neighbor(lv,p+step,1)?FontWeight.bold:FontWeight.normal));
          st.layout(maxWidth:w/2);st.paint(canvas,Offset(x+1,yy+1));
          final bt=TextPainter(textDirection:TextDirection.ltr)..text=TextSpan(text:fmt(buy),style:TextStyle(color:green,fontSize:9,fontWeight:buy>=3*_neighbor(lv,p-step,0)?FontWeight.bold:FontWeight.normal));
          bt.layout(maxWidth:w/2);bt.paint(canvas,Offset(x+w/2+2,yy+1));
        }
      }
      final o=n(c['o']),h=n(c['h']),l=n(c['l']),cl=n(c['c']),col=cl>=o?green:red;
      final cp=Paint()..color=col;canvas.drawLine(Offset(x-3,y(h)),Offset(x-3,y(l)),cp..strokeWidth=1.2);
      canvas.drawRect(Rect.fromLTRB(x-6,y(o)<y(cl)?y(o):y(cl),x+1,(y(o)-y(cl)).abs()<2?(y(o)<y(cl)?y(o):y(cl))+2:(y(o)>y(cl)?y(o):y(cl))),cp);
      if(poc>=0){final yy=y(poc);canvas.drawRect(Rect.fromLTWH(x,yy,w,rh.clamp(1.0,100.0)),Paint()..color=const Color(0xFFF0B429).withValues(alpha:.18));canvas.drawRect(Rect.fromLTWH(x,yy,w,rh.clamp(1.0,100.0)),Paint()..color=const Color(0xFFF0B429)..style=PaintingStyle.stroke);}
      final t=DateTime.fromMillisecondsSinceEpoch((n(c['t'])*1000).toInt(),isUtc:true).add(const Duration(hours:5,minutes:30));
      final tp=TextPainter(textDirection:TextDirection.ltr)..text=TextSpan(text:t.hour.toString().padLeft(2,'0')+':'+t.minute.toString().padLeft(2,'0'),style:const TextStyle(color:Color(0xFF7D8896),fontSize:9));
      tp.layout();tp.paint(canvas,Offset(x,4));
      final delta=n(c['d']),vol=n(c['v']);
      final stats=TextPainter(textDirection:TextDirection.ltr)..text=TextSpan(text:'Δ '+fmt(delta)+'\nVol '+fmt(vol),style:TextStyle(color:delta>=0?green:red,fontSize:9));
      stats.layout(maxWidth:cw);stats.paint(canvas,Offset(x,top+plot+3));
    }
    if(!hasLevels){final tp=TextPainter(textDirection:TextDirection.ltr)..text=const TextSpan(text:'PRICE-LEVEL DEPTH UNAVAILABLE\nBackend currently sends aggregate bid/ask depth only.\nFootprint cells/POC/imbalance are not fabricated.',style:TextStyle(color:Color(0xFFF0B429),fontSize:11,height:1.5));tp.layout(maxWidth:size.width-24);tp.paint(canvas,Offset(12,size.height*.42));}
    final last=vis.last, ltp=n(last['c']), yy=top+(high-ltp)/step*rh;
    if(ltp>=low&&ltp<=high){canvas.drawLine(Offset(0,yy),Offset(size.width-45,yy),Paint()..color=const Color(0xFFF0B429)..strokeWidth=1);canvas.drawRect(Rect.fromLTWH(size.width-45,yy-8,45,16),Paint()..color=const Color(0xFFF0B429));final p=TextPainter(textDirection:TextDirection.ltr)..text=TextSpan(text:ltp.toStringAsFixed(2),style:const TextStyle(color:Colors.black,fontSize:9));p.layout();p.paint(canvas,Offset(size.width-43,yy-5));}
  }
  double _neighbor(dynamic lv,double p,int side){if(lv is! Map)return 0;final pair=lv[p.toString()]??lv[p.toStringAsFixed(2)]??lv[p.toStringAsFixed(1)];return pair is List&&pair.length>side?n(pair[side]):0;}
  @override
  bool shouldRepaint(covariant FootprintPainter old)=>old.candles!=candles||old.zoom!=zoom;
}
