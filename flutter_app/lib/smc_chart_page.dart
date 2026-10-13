import 'package:flutter/material.dart';
import 'api.dart';

const _smcIndexes = ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','SENSEX','BANKEX'];
const _smcCommodities = ['CRUDEOIL','CRUDEOILM','NATURALGAS','NATGASMINI','GOLD','GOLDM','SILVER','SILVERM','COPPER','ZINC','ALUMINIUM','LEAD','NICKEL'];
const _smcUnderlyings = [..._smcIndexes, ..._smcCommodities];

/// Multi-timeframe SMC/ICT chart tab. Consumes the same backend market and
/// signal snapshots as the rest of the app; no synthetic candle fallback.
class SmcChartPage extends StatefulWidget {
  const SmcChartPage({required this.index, required this.market, required this.signal, required this.ai, required this.onIndexChanged, required this.onOpenAiChat, super.key});
  final String index;
  final Map<String,dynamic> market, signal, ai;
  final ValueChanged<String> onIndexChanged;
  final VoidCallback onOpenAiChat;
  @override State<SmcChartPage> createState()=>_SmcChartPageState();
}
class _SmcChartPageState extends State<SmcChartPage> {
  String tf='15m';
  bool showOb=true, showFvg=true, showLiquidity=true, _engineBusy=false;
  Map<String,dynamic> _engineResult=const {};
  String? _engineError;
  bool get _liveFeed => widget.market['live']==true || widget.market['feed_mode']=='LIVE';
  Future<void> _runEngine() async {
    final htf = _bars('1D'), mtf = _bars('1H'), ltf = _bars('15m');
    if (!_liveFeed) {
      setState(() { _engineError='Live backend feed is not confirmed. Demo/synthetic data is disabled.'; _engineResult=const {}; });
      return;
    }
    if (htf.length < 5 || mtf.length < 5 || ltf.length < 5) {
      setState(() { _engineError='Insufficient real candles: at least 5 candles are required for 1D, 1H and 15m. No demo data will be generated.'; _engineResult=const {}; });
      return;
    }
    setState(() { _engineBusy=true; _engineError=null; _engineResult=const {}; });
    try {
      final response=await FreshApi().postJson('/v1/smc/analyze', {
        'instrument':widget.index,
        'htf_candles':htf,
        'mtf_candles':mtf,
        'ltf_candles':ltf,
        'in_killzone':true,
      }, timeout:const Duration(seconds:20));
      if(mounted)setState(()=>_engineResult=response);
    } catch(e) { if(mounted)setState(()=>_engineError=e.toString()); }
    finally { if(mounted)setState(()=>_engineBusy=false); }
  }
  List<Map<String,dynamic>> _bars(String timeframe) {
    final all=Map<String,dynamic>.from(widget.market['timeframes'] as Map? ?? const{});
    return (all[timeframe] as List? ?? const[]).whereType<Map>().map((x)=>Map<String,dynamic>.from(x)).where((x)=>['open','high','low','close'].every((k)=>x[k] is num)).toList();
  }
  List<Map<String,dynamic>> get bars => _bars(tf);
  double? get _last => bars.isEmpty ? null : (bars.last['close'] as num).toDouble();
  Map<String,dynamic> _analyze(List<Map<String,dynamic>> c) {
    if(c.length<5) return {'bias':'NO CLEAR BIAS','signal':'NO TRADE','reason':'Waiting for real candle history','bos':false,'choch':false,'ob':<Map<String,dynamic>>[],'fvg':<Map<String,dynamic>>[],'bsl':<double>[],'ssl':<double>[]};
    final highs=<double>[], lows=<double>[];
    for(var i=1;i<c.length-1;i++){
      final h=(c[i]['high'] as num).toDouble(), l=(c[i]['low'] as num).toDouble();
      if(h>(c[i-1]['high'] as num).toDouble()&&h>(c[i+1]['high'] as num).toDouble())highs.add(h);
      if(l<(c[i-1]['low'] as num).toDouble()&&l<(c[i+1]['low'] as num).toDouble())lows.add(l);
    }
    final last=(c.last['close'] as num).toDouble();
    final bosUp=highs.isNotEmpty&&last>highs.last, bosDown=lows.isNotEmpty&&last<lows.last;
    final bias=bosUp?'BULLISH':bosDown?'BEARISH':(highs.length>=2&&lows.length>=2&&highs.last>highs[highs.length-2]&&lows.last>lows[lows.length-2]?'BULLISH':highs.length>=2&&lows.length>=2&&highs.last<highs[highs.length-2]&&lows.last<lows[lows.length-2]?'BEARISH':'NO CLEAR BIAS');
    final ob=<Map<String,dynamic>>[], fvg=<Map<String,dynamic>>[];
    for(var i=1;i<c.length;i++){
      final p=c[i-1],n=c[i];
      if((p['close'] as num)<(p['open'] as num)&&(n['close'] as num)>(p['high'] as num))ob.add({'type':'bullish','top':p['high'],'bottom':p['low']});
      if((p['close'] as num)>(p['open'] as num)&&(n['close'] as num)<(p['low'] as num))ob.add({'type':'bearish','top':p['high'],'bottom':p['low']});
    }
    for(var i=2;i<c.length;i++){final a=c[i-2],z=c[i];if((a['high'] as num)<(z['low'] as num))fvg.add({'type':'bullish','top':z['low'],'bottom':a['high']});if((a['low'] as num)>(z['high'] as num))fvg.add({'type':'bearish','top':a['low'],'bottom':z['high']});}
    final tol=(last.abs()*.00015).clamp(.05,1000000).toDouble(),bsl=<double>[],ssl=<double>[];
    for(var i=0;i<highs.length;i++){for(var j=i+1;j<highs.length;j++){if((highs[i]-highs[j]).abs()<=tol)bsl.add(highs[i]>highs[j]?highs[i]:highs[j]);}}
    for(var i=0;i<lows.length;i++){for(var j=i+1;j<lows.length;j++){if((lows[i]-lows[j]).abs()<=tol)ssl.add(lows[i]<lows[j]?lows[i]:lows[j]);}}
    final wanted=bias=='BULLISH'?'bullish':'bearish', zones=[...ob,...fvg].where((z)=>z['type']==wanted).toList();
    final poi=zones.isEmpty?null:zones.last;
    final structure=bosUp||bosDown;
    final liq=bias=='BULLISH'?ssl.isNotEmpty:bsl.isNotEmpty;
    final ready=bias!='NO CLEAR BIAS'&&poi!=null&&structure&&liq;
    final reason=ready?'HTF bias + POI + structure + liquidity aligned':[
      if(bias=='NO CLEAR BIAS')'No clear bias',
      if(poi==null)'No directional OB/FVG',
      if(!structure)'Waiting for BOS/CHoCH',
      if(!liq)'Waiting for equal-high/low liquidity'
    ].join(' • ');
    return {'bias':bias,'signal':ready?(bias=='BULLISH'?'LONG':'SHORT'):'NO TRADE','reason':reason,'bos':structure,'choch':false,'ob':ob,'fvg':fvg,'bsl':bsl,'ssl':ssl,'poi':poi,'tol':tol};
  }
  @override Widget build(BuildContext context){
    final a=_analyze(bars);
    final live=_liveFeed && bars.length>=2;
    final aiText=(widget.ai['summary']??widget.ai['status']??widget.signal['ai_validation']??'AI context not returned by backend').toString();
    return ListView(padding:const EdgeInsets.all(12),children:[
      Row(children:[const Expanded(child:Text('SMC / ICT PRO CHART',style:TextStyle(fontWeight:FontWeight.w900,fontSize:18))),Chip(label:Text(live?'LIVE FEED':'WAITING FOR LIVE',style:const TextStyle(fontSize:10)),backgroundColor:live?Colors.green.withOpacity(.18):Colors.orange.withOpacity(.15))]),
      const SizedBox(height:8),
      DropdownButtonFormField<String>(initialValue:widget.index,decoration:const InputDecoration(labelText:'Indian Index / MCX'),items:_smcUnderlyings.map((s)=>DropdownMenuItem(value:s,child:Text(_smcCommodities.contains(s)?'MCX • $s':s))).toList(),onChanged:(v){if(v!=null)widget.onIndexChanged(v);}),
      const SizedBox(height:8),
      Wrap(spacing:6,runSpacing:4,children:[for(final period in const ['1m','3m','5m','15m','30m','1H','2H','4H','1D','1W','1M']) ChoiceChip(label:Text(period),selected:tf==period,onSelected:(_)=>setState(()=>tf=period))]),
      const SizedBox(height:8),
      Card(child:Padding(padding:const EdgeInsets.all(10),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Row(children:[Expanded(child:Text(widget.index,style:const TextStyle(fontWeight:FontWeight.w800,fontSize:15))),Text(_last?.toStringAsFixed(2)??'—',style:const TextStyle(fontWeight:FontWeight.w900,fontSize:18))]),
        const SizedBox(height:8),
        SizedBox(height:270,width:double.infinity,child:bars.length<2?const Center(child:Text('No real candles received — demo data is disabled.')):CustomPaint(painter:SmcCandlePainter(bars:bars,orderBlocks:showOb?(a['ob'] as List<Map<String,dynamic>>):const[],fvgs:showFvg?(a['fvg'] as List<Map<String,dynamic>>):const[]))),
        Wrap(spacing:6,children:[FilterChip(label:const Text('Order Blocks'),selected:showOb,onSelected:(v)=>setState(()=>showOb=v)),FilterChip(label:const Text('FVG'),selected:showFvg,onSelected:(v)=>setState(()=>showFvg=v)),FilterChip(label:const Text('Liquidity'),selected:showLiquidity,onSelected:(v)=>setState(()=>showLiquidity=v))]),
        Text('Source: backend candle snapshots. Overlay calculations are chart-side and do not replace server validation.',style:TextStyle(fontSize:11,color:Colors.white.withOpacity(.6))),
      ]))),
      Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Text('DETERMINISTIC SMC ENGINE',style:TextStyle(fontWeight:FontWeight.w900,letterSpacing:1)),
        const SizedBox(height:8),
        Row(children:[Expanded(child:Text('Bias\n${a['bias']}',style:const TextStyle(fontWeight:FontWeight.w800))),Expanded(child:Text('Setup\n${a['signal']}',style:TextStyle(fontWeight:FontWeight.w900,color:a['signal']=='NO TRADE'?Colors.orangeAccent:a['signal']=='LONG'?Colors.greenAccent:Colors.redAccent)))]),
        const SizedBox(height:8),Text((a['reason']??'').toString()),
        const SizedBox(height:8),Text('BOS: ${a['bos']} • Liquidity tolerance: ${a['tol']??'waiting for candles'}'),
        if(a['poi'] is Map) Text('POI: ${(a['poi'] as Map)['bottom']} – ${(a['poi'] as Map)['top']}'),
        const Text('Order placement remains disabled from this page. Confirmed live data, risk limits and the central engine must approve independently.',style:TextStyle(fontSize:11,color:Colors.white60)),
      ]))),
      Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Text('BACKEND SMC ENGINE • LIVE DATA ONLY',style:TextStyle(fontWeight:FontWeight.w900)),
        const SizedBox(height:8),
        FilledButton.icon(onPressed:_engineBusy?null:_runEngine,icon:Icon(_engineBusy?Icons.hourglass_top:Icons.hub),label:Text(_engineBusy?'ANALYZING…':'RUN MULTI-TIMEFRAME SMC ENGINE')),
        if(_engineResult.isNotEmpty) ...[
          Text('Server decision: ${_engineResult['signal']??'NO TRADE'} • Bias: ${_engineResult['bias']??'UNKNOWN'}',style:const TextStyle(fontWeight:FontWeight.w900)),
          Text('Reason: ${(_engineResult['reasons'] as List? ?? const[]).join(' • ')}'),
          Text('Execution allowed: ${_engineResult['execution_allowed']??false}'),
        ],
        if(_engineError!=null) Text('Backend analysis error: $_engineError',style:const TextStyle(color:Colors.redAccent)),
        const Text('The server result is separate from the visual overlay. Missing timeframes, stale/missing candles or unconfirmed structure must remain NO TRADE.',style:TextStyle(fontSize:11,color:Colors.white60)),
      ]))),
      Card(child:ListTile(leading:const Icon(Icons.psychology_alt),title:const Text('AI validation context'),subtitle:Text(aiText,maxLines:4,overflow:TextOverflow.ellipsis),trailing:const Icon(Icons.open_in_new),onTap:widget.onOpenAiChat)),
      if(showLiquidity) Card(child:Padding(padding:const EdgeInsets.all(12),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Text('LIQUIDITY MAP',style:TextStyle(fontWeight:FontWeight.w900)),
        Text('BSL (equal highs): ${(a['bsl'] as List).map((v)=>(v as num).toStringAsFixed(2)).join(', ')}'),
        Text('SSL (equal lows): ${(a['ssl'] as List).map((v)=>(v as num).toStringAsFixed(2)).join(', ')}'),
      ]))),
      FilledButton.icon(onPressed:widget.onOpenAiChat,icon:const Icon(Icons.psychology),label:const Text('Open AI Chat with current instrument selected')),
    ]);
  }
}

class SmcCandlePainter extends CustomPainter {
  SmcCandlePainter({required this.bars,required this.orderBlocks,required this.fvgs});
  final List<Map<String,dynamic>> bars;
  final List<Map<String,dynamic>> orderBlocks,fvgs;
  @override void paint(Canvas canvas,Size size){
    final shown=bars.length>70?bars.sublist(bars.length-70):bars;
    final nums=<double>[];for(final b in shown){nums.addAll([(b['high'] as num).toDouble(),(b['low'] as num).toDouble()]);}
    if(nums.isEmpty)return;
    var mn=nums.reduce((a,b)=>a<b?a:b),mx=nums.reduce((a,b)=>a>b?a:b);if(mx-mn<.000001){mn-=1;mx+=1;}
    const left=8.0,right=50.0,top=10.0,bottom=10.0;final pw=size.width-left-right,ph=size.height-top-bottom;
    double y(double p)=>top+(mx-p)/(mx-mn)*ph;
    final grid=Paint()..color=Colors.white.withOpacity(.08);
    for(var i=0;i<5;i++){final yy=top+i*ph/4;canvas.drawLine(Offset(left,yy),Offset(left+pw,yy),grid);}
    void zones(List<Map<String,dynamic>> zs,Color color){for(final z in zs){final hi=(z['top'] as num).toDouble(),lo=(z['bottom'] as num).toDouble();final paint=Paint()..color=color.withOpacity(.14);canvas.drawRect(Rect.fromLTRB(left,y(hi),left+pw,y(lo)),paint);}}
    zones(fvgs,Colors.purpleAccent);zones(orderBlocks,Colors.orangeAccent);
    final step=pw/shown.length,body=(step*.55).clamp(1.5,9.0).toDouble();
    for(var i=0;i<shown.length;i++){final b=shown[i],o=(b['open'] as num).toDouble(),h=(b['high'] as num).toDouble(),l=(b['low'] as num).toDouble(),c=(b['close'] as num).toDouble(),x=left+i*step+step/2,up=c>=o;final color=up?Colors.greenAccent:Colors.redAccent;final p=Paint()..color=color..strokeWidth=1;canvas.drawLine(Offset(x,y(h)),Offset(x,y(l)),p);final yy=y(o>c?o:c),yb=y(o<c?o:c);canvas.drawRect(Rect.fromLTRB(x-body/2,yy,x+body/2,(yb-yy).abs()<2?yy+2:yb),p);}
    final style=TextStyle(color:Colors.white.withOpacity(.65),fontSize:9);for(var i=0;i<5;i++){final p=mx-i*(mx-mn)/4;final tp=TextPainter(text:TextSpan(text:p.toStringAsFixed(2),style:style),textDirection:TextDirection.ltr)..layout(maxWidth:right-3);tp.paint(canvas,Offset(left+pw+3,top+i*ph/4-5));}
  }
  @override bool shouldRepaint(covariant SmcCandlePainter old)=>old.bars!=bars||old.orderBlocks!=orderBlocks||old.fvgs!=fvgs;
}
