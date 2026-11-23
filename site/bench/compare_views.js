"use strict";
/* Render comparable metric values and densities without imputing missing evidence. */
const BenchViews = (() => {
  const ranks=typeof BenchRanks!=="undefined"?BenchRanks:require("./rankings.js");
  const density=typeof BenchDistribution!=="undefined"
    ?BenchDistribution:require("./distribution.js");
  const safe=value=>String(value??"").replace(/[&<>"']/g,c=>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const NAMES={iva:"IVA",megahit:"MEGAHIT",haploflow:"Haploflow",
    abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
  const label=tool=>NAMES[tool]||String(tool??"")
    .replace(/[_-]+/g," ").replace(/\b[a-z]/g,c=>c.toUpperCase());
  const value=x=>Number.isFinite(x)?x.toLocaleString("en",{
    maximumSignificantDigits:8}):"—";
  const keyFor=key=>key==="alignment"?"score":key==="runtime"?"seconds":key;
  function measured(run,snapshot,key,tool) {
    return ranks.measurements(run,snapshot,keyFor(key),tool);
  }
  function sampleGroups(run,snapshot,alias,a,b) {
    const catalog=snapshot?.metric_catalog||{};
    const groups=new Map();
    for(const key of ["score","seconds",...Object.keys(catalog).sort()]) {
      const info=ranks.definition(key,catalog);
      if(!info)continue;
      const first=measured(run,snapshot,key,a).find(x=>x.id===alias);
      const second=measured(run,snapshot,key,b).find(x=>x.id===alias);
      const stage=key==="score"||key==="seconds"?"Core measurements":info.stage;
      if(!groups.has(stage))groups.set(stage,[]);
      groups.get(stage).push({key,info,first:first?.value??null,
        second:second?.value??null});
    }
    return [...groups].map(([stage,rows])=>({stage,rows}));
  }
  function sampleTable(run,snapshot,alias,a,b) {
    const groups=sampleGroups(run,snapshot,alias,a,b);
    const known=groups.flatMap(g=>g.rows).filter(r=>r.first!==null||
      r.second!==null).length;
    return '<p class="subtle">'+known+' of '+
      groups.reduce((n,g)=>n+g.rows.length,0)+
      ' metrics have at least one recorded value. — means unavailable, not zero.</p>'+
      groups.map(g=>'<section class="sample-metric-group"><h3>'+safe(g.stage)+
        '</h3><table class="sample-metric-table"><thead><tr>'+
        '<th>Metric and calculation</th><th>'+safe(label(a))+
        '</th><th>'+safe(label(b))+'</th></tr></thead><tbody>'+
        g.rows.map(row=>'<tr><td><details><summary>'+safe(row.info.label)+
          '</summary><p>'+safe(row.info.description)+'</p><p><strong>Basis:</strong> '+
          safe(row.info.denominator)+'</p></details><small>'+safe(row.info.unit)+
          '</small></td><td class="number">'+value(row.first)+'</td>'+
          '<td class="number">'+value(row.second)+'</td></tr>').join("")+
        '</tbody></table></section>').join("");
  }
  function plotMetric(run,snapshot,subject,a,b) {
    const key=keyFor(subject.key);
    const info=ranks.definition(key,snapshot?.metric_catalog);
    if(!info)return '<p>Metric definition unavailable: '+safe(subject.key)+'</p>';
    const first=measured(run,snapshot,key,a),second=measured(run,snapshot,key,b);
    const expand=rows=>rows.flatMap(row=>Array.from({length:Math.min(
      400,row.weight)},()=>row.value));
    const comparison=density.compare(expand(first),expand(second));
    const title='<h4>'+safe(info.label)+' <small>('+safe(info.unit)+')</small></h4>';
    const nA=comparison.first.n,nB=comparison.second.n;
    const common=new Set(first.map(x=>x.id));
    const shared=second.filter(x=>common.has(x.id)).length;
    const legend='<p class="distribution-legend"><span class="series-key series-a">'+
      safe(label(a))+'</span> · '+nA+' measured; '+
      '<span class="series-key series-b">'+safe(label(b))+'</span> · '+nB+
      ' measured. '+shared+' matched case IDs; missing runs are excluded individually.</p>';
    if(!comparison.pooled.n)return '<article class="matrix-plot">'+title+
      '<p class="hint">No recorded values for either assembler.</p>'+legend+'</article>';
    const left=64,right=700,top=13,bottom=208;
    const [low,high]=comparison.pooled.range;
    const x=v=>left+(v-low)/(high-low)*(right-left);
    const peak=Math.max(1e-12,...comparison.first.bins.map(b=>b.density),
      ...comparison.second.bins.map(b=>b.density),
      ...comparison.first.curve.map(p=>p.y),
      ...comparison.second.curve.map(p=>p.y))*1.12;
    const y=v=>bottom-v/peak*(bottom-top);
    // Bars share their complete bin interval; render taller bars behind shorter.
    const bins=comparison.first.bins.length
      ?comparison.first.bins:comparison.second.bins;
    const bars=bins.map((sourceBin,index)=>{
      const empty={...sourceBin,count:0,density:0};
      const firstBin=comparison.first.bins[index]||empty;
      const secondBin=comparison.second.bins[index]||empty;
      const draw=(bin,series,tool)=>'<rect class="distribution-bin '+series+
        '" x="'+(x(bin.from)+.5).toFixed(2)+'" y="'+
        y(bin.density).toFixed(2)+'" width="'+
        Math.max(0,x(bin.to)-x(bin.from)-1).toFixed(2)+
        '" height="'+Math.max(0,bottom-y(bin.density)).toFixed(2)+
        '"><title>'+safe(label(tool))+': '+bin.count+' values, '+
        value(bin.from)+' to '+value(bin.to)+'</title></rect>';
      const first=draw(firstBin,"series-a",a);
      const second=draw(secondBin,"series-b",b);
      return firstBin.density>=secondBin.density?first+second:second+first;
    }).join("");
    const curve=(model,series)=>model.curve.length
      ?'<path class="distribution-kde '+series+'" d="'+model.curve.map((p,i)=>
        (i?"L":"M")+x(p.x).toFixed(2)+","+y(p.y).toFixed(2)).join(" ")+'"></path>'
      :"";
    const ticks=[low,(low+high)/2,high].map(t=>
      '<text x="'+x(t).toFixed(2)+'" y="230" text-anchor="middle">'+
      safe(value(t))+'</text>').join("");
    const summary='<p class="distribution-legend">Histograms: overlaid relative frequency '+
      'per unit, with identical bin edges and axes; taller bars behind shorter bars. Curves: Gaussian KDE '+
      '(absent for constant or single-value series). Values are independently '+
      'normalized within each assembler.</p>';
    return '<article class="matrix-plot">'+title+
      '<svg viewBox="0 0 735 245" role="img" aria-label="'+
      safe(info.label+', '+label(a)+' and '+label(b)+' histogram and KDE')+'">'+
      '<line class="distribution-axis" x1="'+left+'" x2="'+right+
      '" y1="'+bottom+'" y2="'+bottom+'"></line>'+
      bars+
      curve(comparison.first,"series-a")+curve(comparison.second,"series-b")+
      ticks+'</svg>'+legend+summary+'</article>';
  }
  function matrixPlots(run,snapshot,subjects,a,b) {
    return '<section class="matrix-distributions" aria-label="Per-metric comparison plots">'+
      '<h3>Distributions · '+safe(label(a))+' versus '+safe(label(b))+'</h3>'+
      '<p class="hint">Each selected metric has its own axis and units. '+
      'These distributions describe available observations; Ψ dominance is '+
      'computed separately from paired differences.</p>'+
      subjects.map(s=>plotMetric(run,snapshot,s,a,b)).join("")+'</section>';
  }
  return {sampleGroups,sampleTable,plotMetric,matrixPlots};
})();
if(typeof module!=="undefined")module.exports=BenchViews;
