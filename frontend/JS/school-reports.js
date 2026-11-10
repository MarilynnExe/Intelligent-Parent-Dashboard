/* Administrator-only reports; never calculate or mutate source records. */
document.addEventListener("DOMContentLoaded",()=> {
    const el=id=>document.getElementById(id),esc=value=>escapeHtml(String(value??""));
    if(!el("report-filters") || Auth.getUser()?.role!=="ADMIN")return;
    const period=currentAcademicPeriod();el("report-year").value=period.academic_year;el("report-term").value=period.term;
    let generation=0,classes=[],current=null,currentQuery=null,offset=0,started=false;
    const number=value=>value==null ? "—" : Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
    const percent=value=>value==null ? "No data" : `${number(value)}%`;
    const table=(headers,rows)=>rows.length ? `<table class="data-table"><thead><tr>${headers.map(h=>`<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(value=>`<td>${esc(value)}</td>`).join("")}</tr>`).join("")}</tbody></table>` : '<p class="state-box">No recorded data for these filters.</p>';
    function streamOptions(){
        const prior=el("report-stream").value;
        const values=[...new Set(classes.filter(c=>!el("report-grade").value || c.grade_level===el("report-grade").value).map(c=>c.stream))].sort();
        el("report-stream").replaceChildren(new Option("All streams",""),...values.map(value=>new Option(value||"No stream",JSON.stringify(value))));
        if(values.some(value=>JSON.stringify(value)===prior))el("report-stream").value=prior;
    }
    async function options(){
        try {
            const response=await apiFetch("/admin/reports/options");if(!response.ok)throw new Error("Filter options unavailable. Refresh the page to retry.");
            classes=(await response.json()).classes;
            el("report-grade").replaceChildren(new Option("All grades",""),...[...new Set(classes.map(c=>c.grade_level))].sort().map(value=>new Option(value,value)));
            streamOptions();
        }catch(error){el("report-status").textContent=error.message;}
    }
    function query(){
        const q=new URLSearchParams({term:el("report-term").value,academic_year:String(Number(el("report-year").value)).padStart(4,"0"),compare_previous:el("report-compare").checked,issue:el("report-issue").value,limit:50,offset});
        if(el("report-grade").value)q.set("grade_level",el("report-grade").value);
        if(el("report-stream").value)q.set("stream",JSON.parse(el("report-stream").value));
        return q;
    }
    const card=(title,value,detail,progress=null)=>`<article class="report-card"><h4>${esc(title)}</h4><strong>${esc(value)}</strong><p>${esc(detail)}</p>${progress==null ? "" : `<progress max="100" value="${progress}" aria-label="${esc(title)}"></progress>`}</article>`;
    function render(data){
        const s=data.summary;
        el("report-generated").textContent=`${data.term} ${data.academic_year} · ${data.filters.grade_level||"All grades"} · ${data.filters.stream===null ? "All streams" : data.filters.stream||"No stream"} · As of ${data.as_of} (Africa/Nairobi) · Generated ${new Date(data.generated_at+"Z").toLocaleString()}`;
        el("report-summary").innerHTML=card("Active learners",number(s.learner_count),`${s.assessed_learners} assessed; ${s.unassessed_learners} without assessments`,s.academic_coverage_pct)+
            card("Academic mean",s.academic_average==null ? "No data" : `${number(s.academic_average)}%`,`${s.assessment_count} assessment records; equal weight per assessed learner`)+
            card("Recorded attendance rate",percent(s.attendance_rate_pct),`${s.attendance_counts.Present} Present · ${s.attendance_counts.Late} Late · ${s.attendance_counts.Absent} Absent · ${s.attendance_counts.Excused} Excused; ${s.learners_with_attendance} learners with records`,s.attendance_rate_pct)+
            card("Assignment completion",percent(s.assignment_completion_pct),`${s.completed_due_count}/${s.due_count} due recipient records complete; ${s.assignment_counts.MISSING} missing; ${s.learners_with_assignments} learners assigned`,s.assignment_completion_pct)+
            card("Competency evidence coverage",percent(s.competency_coverage_pct),`${s.assessed_competency_slots}/${s.competency_slots} learner-skill slots assessed; ${s.competency_counts.NOT_ASSESSED} unassessed`,s.competency_coverage_pct)+
            card("Current analytics",percent(s.analytics_coverage_pct),`${s.freshness_counts.current}/${s.learner_count} learners have current, valid stored indicators`,s.analytics_coverage_pct);
        el("report-freshness").innerHTML=Object.entries(s.freshness_counts).map(([key,count])=>`<span class="report-count">${esc(key)}: <strong>${count}</strong></span>`).join("")+Object.entries(s.support_counts).map(([key,count])=>`<span class="report-count">${esc(key)}: <strong>${count}</strong></span>`).join("");
        const groupRows=(groups,includeStream)=>groups.map(row=>[row.grade_level,...(includeStream ? [row.stream||"No stream"] : []),row.learner_count,`${row.assessed_learners}/${row.learner_count}`,row.academic_average==null ? "No data" : `${number(row.academic_average)}%`,percent(row.attendance_rate_pct),percent(row.assignment_completion_pct),percent(row.competency_coverage_pct),`${row.freshness_counts.current}/${row.learner_count}`]);
        const headers=["Grade","Learners","Assessed","Academic mean","Recorded attendance","Assignments complete","Competency evidence","Current analytics"];
        el("report-grades").innerHTML=table(headers,groupRows(data.grades,false));
        el("report-classes").innerHTML=table(["Grade","Stream",...headers.slice(1)],groupRows(data.classes,true));
        el("report-subjects").innerHTML=table(["Subject","Assessed learners","Assessment records","Mean of learner subject means"],data.subjects.map(row=>[row.subject_name,row.assessed_learners,row.assessment_count,`${number(row.academic_average)}%`]));
        el("report-attendance").innerHTML=table(["Month","Present","Late","Absent","Excused","Recorded attendance rate"],data.attendance_trend.map(row=>[row.month,row.counts.Present,row.counts.Late,row.counts.Absent,row.counts.Excused,percent(row.attendance_rate_pct)]));
        const page=data.learners;
        el("report-learners-count").textContent=page.total ? `${page.offset+1}–${Math.min(page.offset+page.limit,page.total)} of ${page.total} matching learners` : "No matching learners.";
        el("report-learners").innerHTML=table(["Learner","Admission","Class","Assessment mean","Attendance","Missing work","Unassessed skills","Analytics","Current advisory status","Last calculation"],page.items.map(row=>[row.student_name,row.admission_number,`${row.grade_level} / ${row.stream||"No stream"}`,row.academic_average==null ? "Not assessed" : `${number(row.academic_average)}%`,percent(row.attendance_rate_pct),row.assignment_counts.MISSING,row.competency_counts.NOT_ASSESSED,row.freshness,row.support_status||"Unavailable",row.calculated_at ? new Date(row.calculated_at+"Z").toLocaleString() : "Never"]));
        el("report-prev").disabled=page.offset===0;el("report-next").disabled=page.offset+page.limit>=page.total;
        el("report-methodology").innerHTML=data.methodology.map(note=>`<li>${esc(note)}</li>`).join("");
        const compare=data.comparison;
        el("report-comparison-note").textContent=compare ? `Compared with ${compare.term} ${compare.academic_year}, using current active enrollment. Coverage and records can differ; these changes do not prove an intervention effect. Percentage changes are percentage points.` : "Previous-period comparison is disabled or unavailable for the earliest supported period.";
        const metrics=[["Academic mean","academic_average"],["Academic assessment coverage","academic_coverage_pct"],["Recorded attendance rate","attendance_rate_pct"],["Assignment completion","assignment_completion_pct"],["Competency evidence coverage","competency_coverage_pct"],["Current analytics coverage","analytics_coverage_pct"]];
        el("report-comparison").innerHTML=compare ? table(["Measure","Previous period","Selected period","Change (points)"],metrics.map(([name,key])=>[name,percent(compare.summary[key]),percent(s[key]),compare.deltas[key]==null ? "Not comparable" : `${compare.deltas[key]>0 ? "+" : ""}${number(compare.deltas[key])}`]))+`<p>Assessed learners: ${compare.summary.assessed_learners} previously; ${s.assessed_learners} selected. Recorded learner-days: ${compare.summary.recorded_learner_days} previously; ${s.recorded_learner_days} selected.</p>` : "";
    }
    async function load(reset=true){
        if(reset)offset=0;
        const ticket=++generation;started=true;current=null;currentQuery=null;
        el("report-results").hidden=true;el("report-generated").textContent="";el("report-export").disabled=true;el("report-prev").disabled=el("report-next").disabled=true;
        if(!el("report-filters").checkValidity()){el("report-status").textContent="Choose a valid academic year (1–9999).";return;}
        const q=query();el("report-status").textContent="Loading school report…";
        try {
            const response=await apiFetch(`/admin/reports/overview?${q}`);const data=await response.json();
            if(ticket!==generation)return;
            if(!response.ok)throw new Error(Array.isArray(data.detail) ? data.detail.map(d=>d.msg).join("; ") : data.detail||"Report unavailable. Generate report to retry.");
            current=data;currentQuery=q;render(data);el("report-results").hidden=false;el("report-export").disabled=false;
            el("report-status").textContent=data.summary.learner_count ? "Report ready. Figures reflect saved records; generate again after changes." : "No active learners match the selected filters.";
        }catch(error){if(ticket===generation)el("report-status").textContent=error.message;}
    }
    el("report-filters").onsubmit=event=>{event.preventDefault();load();};
    ["report-year","report-term","report-grade","report-stream","report-compare","report-issue"].forEach(id=>el(id).onchange=()=>{if(id==="report-grade")streamOptions();load();});
    el("report-prev").onclick=()=>{offset=Math.max(0,offset-50);load(false);};
    el("report-next").onclick=()=>{offset+=50;load(false);};
    el("tab-reports").addEventListener("click",()=>{if(!started)load();});
    el("report-export").onclick=async()=>{
        if(!current || !currentQuery)return;
        const ticket=generation,q=new URLSearchParams(currentQuery),dataset=el("report-export-dataset").value;
        q.delete("limit");q.delete("offset");q.delete("compare_previous");q.set("dataset",dataset);el("report-export").disabled=true;
        try {
            const response=await apiFetch(`/admin/reports/export.csv?${q}`);
            if(!response.ok)throw new Error("CSV export unavailable. Generate report and retry.");
            const blob=await response.blob();if(ticket!==generation)return;
            const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`school-report-${dataset}-${current.academic_year}-term-${current.term.at(-1)}.csv`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
            el("report-status").textContent="CSV downloaded. Learner exports contain all follow-up matches, not only the visible page; exports reflect saved records at download time.";
        }catch(error){if(ticket===generation)el("report-status").textContent=error.message;}finally{if(ticket===generation)el("report-export").disabled=!current;}
    };
    options();
});
