// DOM-light regression for the shipped component; not a substitute for browser e2e.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('frontend/geometry_component/index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const messages = [];
const context2d = new Proxy({}, {get: (target, key) => target[key] ?? (() => {}), set: (target,key,value) => (target[key]=value,true)});
const canvas = {width:800,height:540,getContext:()=>context2d,setPointerCapture:()=>{},
    getBoundingClientRect:()=>({left:0,top:0,width:800,height:540})};
const elements = {c:canvas,reset:{},status:{}};
let listener;
const sandbox = {console,structuredClone,Date,Math,Map,
    document:{getElementById:id=>elements[id],body:{clientWidth:803}},
    parent:{postMessage:msg=>messages.push(msg)},
    window:{addEventListener:(name,fn)=>listener=fn}};
vm.createContext(sandbox);
vm.runInContext(script,sandbox);
assert.equal(messages[0].type,'streamlit:componentReady');
listener({data:{type:'streamlit:render',args:{solution:{points:{A:[0,0],B:[4,0],C:[0,3]},lines:[['A','B'],['B','C'],['C','A']],circles:[]}}}});
assert(messages.some(m=>m.type==='streamlit:setFrameHeight'));
const original = vm.runInContext('scale',sandbox);
canvas.onwheel({clientX:300,clientY:200,deltaY:-100,preventDefault:()=>{}});
assert(vm.runInContext('scale',sandbox)>original);
elements.reset.onclick();
const p = vm.runInContext('screen(points.A)',sandbox);
canvas.onpointerdown({pointerId:1,clientX:p[0],clientY:p[1]});
canvas.onpointermove({pointerId:1,clientX:p[0]+20,clientY:p[1]+20});
canvas.onpointerup({pointerId:1});
const edit = messages.find(m=>m.type==='streamlit:setComponentValue');
assert.equal(edit.value.point_name,'A');
assert.equal(edit.value.new_coords.length,2);
assert.deepEqual(Array.from(vm.runInContext('points.A',sandbox)),[0,0]);
console.log('PASS: component ready, render, zoom, reset, drag event, optimistic rollback');
