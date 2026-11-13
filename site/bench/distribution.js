"use strict";
/* The histogram and Gaussian KDE have the same probability-density units. */
const BenchDistribution = (() => {
  const finite = value => typeof value==="number"&&Number.isFinite(value);
  function quantile(sorted, fraction) {
    const index=(sorted.length-1)*fraction;
    const lo=Math.floor(index), hi=Math.ceil(index);
    return sorted[lo]+(sorted[hi]-sorted[lo])*(index-lo);
  }
  function model(numbers) {
    const values=numbers.filter(finite).slice().sort((a,b)=>a-b);
    const n=values.length;
    if(!n)return {n:0,bins:[],curve:[],bandwidth:null,range:null};
    const low=values[0],high=values[n-1],span=high-low;
    const mean=values.reduce((total,v)=>total+v,0)/n;
    const variance=values.reduce((total,v)=>total+(v-mean)**2,0)/n;
    const sd=Math.sqrt(variance);
    const iqr=quantile(values,.75)-quantile(values,.25);
    const sigma=iqr>0?Math.min(sd,iqr/1.349):sd;
    const bandwidth=span>0&&sigma>0
      ?.9*sigma*Math.pow(n,-.2):null;
    const fallback=Math.max(1,Math.abs(mean)*.1);
    const margin=bandwidth?Math.min(3*bandwidth,2*span):fallback;
    const min=low-margin,max=high+margin;
    const width=max-min;
    const fd=iqr>0?2*iqr/Math.cbrt(n):0;
    const count=span>0?Math.max(3,Math.min(32,
      Math.ceil(span/(fd>0?fd:span/Math.max(3,Math.sqrt(n)))))):1;
    const binWidth=width/count;
    const counts=Array(count).fill(0);
    for(const value of values) {
      const index=Math.min(count-1,Math.max(0,
        Math.floor((value-min)/binWidth)));
      counts[index]++;
    }
    const bins=counts.map((total,index)=>({
      from:min+index*binWidth,to:min+(index+1)*binWidth,
      count:total,density:total/(n*binWidth)
    }));
    const curve=[];
    if(bandwidth&&Number.isFinite(bandwidth)) {
      const factor=1/(n*bandwidth*Math.sqrt(2*Math.PI));
      for(let k=0;k<=160;k++) {
        const x=min+k/160*width;
        let sum=0;
        for(const value of values) {
          const z=(x-value)/bandwidth;
          sum+=Math.exp(-.5*z*z);
        }
        curve.push({x,y:factor*sum});
      }
    }
    return {n,bins,curve,bandwidth,range:[min,max],
      min:low,max:high,mean};
  }
  return {model};
})();
if(typeof module!=="undefined")module.exports=BenchDistribution;
