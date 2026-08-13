import "./lineage-marker.js";
const lineageMarker = (globalThis as any).lineageMarker;
let pass=0, fail=0;
const ck=(n:string, cond:boolean, got:unknown)=>{cond?pass++:fail++;console.log(`  ${cond?"OK  ":"FAIL"} ${n}${cond?"":"  got="+JSON.stringify(got)}`)};

const NP = "independence NOT PROVEN";

// 1. THE REGRESSION: absent state used to render nothing at all
const absent = lineageMarker(null);
ck("null -> NOT PROVEN, never a bare green", absent.tail.includes(NP), absent);
ck("null -> names why it could not evaluate", absent.tail.includes("fewer than two lanes"), absent.tail);

// 2. malformed, in several shapes
for (const bad of [undefined, {}, [], [42], "INDEPENDENT", [null,"x"]] as any[]) {
  const r = lineageMarker(bad);
  ck(`malformed ${JSON.stringify(bad)} -> NOT PROVEN`, r.tail.includes(NP), r);
}

// 3. an unrecognised future state must not inherit the strongest rendering
const future = lineageMarker(["INDEPENDENT_V2","new state"]);
ck("unknown state -> NOT PROVEN (fails closed)", future.tail.includes(NP), future);
ck("unknown state -> not marked independent", !future.addClass.includes("lin-independent"), future.addClass);

// 4. INVERSE CONTROL — the marker must DISAPPEAR when genuinely proven,
//    or the test is green about a string rather than a state
const ind = lineageMarker(["INDEPENDENT","no shared affiliation"]);
ck("INDEPENDENT -> marker gone", !ind.tail.includes(NP), ind.tail);
ck("INDEPENDENT -> class applied", ind.addClass.includes("lin-independent"), ind.addClass);

// 5. DERIVED still removes the plain match styling
const der = lineageMarker(["DERIVED","shared ancestor"]);
ck("DERIVED -> drops 'match'", der.removeClass.includes("match"), der.removeClass);
ck("DERIVED -> not NOT PROVEN", !der.tail.includes(NP), der.tail);

// 6. the invariant: no input produces an unqualified result
const inputs:any[] = [null, undefined, {}, [], [42], ["INDEPENDENT","x"], ["DERIVED","y"],
                      ["INDEPENDENCE_NOT_PROVEN","z"], ["WAT","q"]];
ck("no input yields an unqualified marker", inputs.every(i=>lineageMarker(i).qualified===true), "-");
ck("every input yields a non-empty tail", inputs.every(i=>lineageMarker(i).tail.length>0), "-");

console.log(`\n  ${fail===0?"PASS":"FAIL"} — ${pass}/${pass+fail}`);
process.exit(fail===0?0:1);
