/* Separate, authenticated comparator-first benchmark progress. No polling. */
(() => {
  "use strict";
  const ORDER=["iva","haploflow","megahit","abyss","spades","velvet"];
  const NAMES={iva:"IVA",haploflow:"Haploflow",megahit:"MEGAHIT",
    abyss:"ABySS",spades:"SPAdes",velvet:"Velvet"};
  const place=document.getElementById("comparatorProgress");
  if (!place) return;
  const text=(tag,value,cls) => {
    const node=document.createElement(tag);
    node.textContent=value;
    if(cls) node.className=cls;
    return node;
  };
  function value(record) {
    const count=record.completed+"/"+record.expected;
    const tail=record.failed ? " · "+record.failed+" failed" : "";
    return count+tail;
  }
  function mean(record) {
    if(!record.successful) return "Not measured yet";
    return record.mean_alignment.toLocaleString(undefined,{
      maximumFractionDigits:1})+" points · "+
      record.mean_seconds.toFixed(1)+" s";
  }
  function render(report) {
    if(report.schema!=="ivanka.assembler-bench.comparators-first-progress.v1" ||
       report.ivanka!=="deliberately_deferred" || !report.tools ||
       ORDER.some(name=>!report.tools[name])) {
      throw new Error("Unexpected comparator progress source");
    }
    place.replaceChildren();
    const title=text("h2","Comparator-first rerun · updating");
    place.append(title);
    place.append(text("p",
      "Six assembler images are being measured first on the frozen MiCall "+
      "inputs. Ivanka is intentionally deferred for later requalification. "+
      "This is partial data, not a benchmark pass. Synthetic scores " +
      "use the single generating truth; physical scores use the 33-reference " +
      "panel, so averages across cohorts are not directly comparable.","subtle"));
    const table=document.createElement("table");
    const head=document.createElement("thead");
    const hr=document.createElement("tr");
    ["Assembler","Synthetic (of 400)","Physical (of 198)",
      "Synthetic mean score · runtime","Physical mean score · runtime"].forEach(label =>
      hr.append(text("th",label)));
    head.append(hr);table.append(head);
    const body=document.createElement("tbody");
    ORDER.forEach(name => {
      const row=document.createElement("tr");
      row.append(text("th",NAMES[name]));
      row.append(text("td",value(report.tools[name].synthetic)));
      row.append(text("td",value(report.tools[name].real)));
      row.append(text("td",mean(report.tools[name].synthetic)));
      row.append(text("td",mean(report.tools[name].real)));
      body.append(row);
    });
    table.append(body);
    const wrap=document.createElement("div");
    wrap.className="table-scroll";
    wrap.append(table);
    place.append(wrap);
    const stamp=report.updated_utc ?
      new Date(report.updated_utc).toLocaleString() : "Awaiting first update";
    place.append(text("p","Last verified update: "+stamp+
      " · Refresh the page to see newly published results.","subtle"));
  }
  fetch("./data/comparator-progress.json",{cache:"no-store"})
    .then(response => {
      if(!response.ok) throw new Error("Progress not yet published");
      return response.json();
    }).then(render).catch(error => {
      place.textContent="Comparator-first progress will appear when "+
        "the first verified checkpoint is published. "+error.message;
    });
})();
