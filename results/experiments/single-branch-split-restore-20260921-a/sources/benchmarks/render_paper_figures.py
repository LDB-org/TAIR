"""Rebuild README figures from frozen experiments; never modifies experiment data."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/paper'
COLORS=['#506477','#18867f','#ce8638']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','svg.fonttype':'none','figure.facecolor':'white','savefig.facecolor':'white','pdf.fonttype':42})
SOURCES=[]
def read(relative):
 p=ROOT/relative;SOURCES.append({'path':relative,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 return [json.loads(s) for s in p.read_text().splitlines()] if p.suffix=='.jsonl' else json.loads(p.read_text())

def save(fig,name):
 fig.canvas.draw()
 texts=[(t,t.get_text(),t.get_fontproperties().copy()) for t in fig.findobj(Text)]
 formatters=[(axis,axis.get_major_formatter()) for ax in fig.axes for axis in [ax.xaxis,ax.yaxis]]
 for lang in ['en','zh-CN']:
  directory=OUT/lang;directory.mkdir(parents=True,exist_ok=True)
  if lang=='zh-CN':
   fonts=[Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')]
   font=next((p for p in fonts if p.exists()),None)
   if font is None:raise RuntimeError('Install fonts-noto-cjk or fonts-wqy-zenhei to render Chinese figures.')
   for axis,formatter in formatters:
    axis.set_major_formatter(FuncFormatter(lambda value,pos,original=formatter: ZH.get(original(value,pos),original(value,pos))))
   for text,value,prop in texts:
    text.set_text(ZH.get(value,value))
    translated=prop.copy();translated.set_file(str(font));text.set_fontproperties(translated)
  for ext in ['png','svg','pdf']:
   fig.savefig(directory/f'{name}.{ext}',dpi=180,bbox_inches='tight',metadata={'Creator':'TAIR figure renderer'} if ext=='pdf' else None)
  for axis,formatter in formatters:axis.set_major_formatter(formatter)
  for text,value,prop in texts:text.set_text(value);text.set_fontproperties(prop)
 plt.close(fig)

def box(ax,x,y,w,h,text,color=COLORS[0],dashed=False):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.02,rounding_size=0.12',linewidth=1.4,edgecolor=color,facecolor='#f5f8fa',linestyle='--' if dashed else '-'))
 ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=10,color='#172b3a')

def arrow(ax,start,end,label=None,dashed=False):
 ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=13,color='#536575',linewidth=1.3,linestyle='--' if dashed else '-'))
 if label:ax.text((start[0]+end[0])/2,(start[1]+end[1])/2+.11,label,ha='center',fontsize=8)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 combined=read('results/experiments/pi-combined-structural-20260918-a/rows.jsonl')
 finite=read('results/experiments/pi-all-classification-20260918-a/summary.json')
 jit=read('results/experiments/pi-jit-codebook-20260918-b/summary.json')
 jrows=read('results/experiments/pi-jit-codebook-20260918-b/rows.jsonl')
 fig,ax=plt.subplots(figsize=(12,6));ax.set_xlim(0,12);ax.set_ylim(0,6);ax.axis('off')
 ax.text(.2,5.65,'TAIR: four mechanisms, two measured paths',fontsize=16,weight='bold')
 ax.text(.2,5.23,'Implemented engine path',fontsize=11,weight='bold',color=COLORS[1])
 box(ax,.2,3.6,2,1.1,'Task + source\nRuntime candidates')
 box(ax,2.65,3.6,2.25,1.1,'C2  Direct logits\nSelect operation\nSelect Schema',COLORS[1])
 box(ax,5.4,3.6,2.3,1.1,'C3  Retain KV\nGenerate necessary\narguments',COLORS[1])
 box(ax,8.2,3.6,3.5,1.1,'C1  Compact protocol\nValidate + deterministic rewrite\nHarness executes',COLORS[1])
 for x1,x2 in [(2.2,2.65),(4.9,5.4),(7.7,8.2)]:arrow(ax,(x1,4.15),(x2,4.15))
 ax.text(.2,2.93,'C4  Dynamic codebook prototype (separate client-side path)',fontsize=11,weight='bold',color=COLORS[2])
 box(ax,.2,1.3,2.6,1.1,'Retrieve version-bound\ntemplates + bind values',COLORS[2],True)
 box(ax,3.3,1.3,2.25,1.1,'Classify + gate\nHit: select full edit\nNo argument generation',COLORS[2],True)
 box(ax,6.05,1.3,2.4,1.1,'Miss: generate\nOracle validation\nAdmit supported edit',COLORS[2],True)
 box(ax,8.95,1.3,2.75,1.1,'Codebook\nTask-bound templates\nSource-version checks',COLORS[2],True)
 arrow(ax,(2.8,1.85),(3.3,1.85));arrow(ax,(5.55,1.85),(6.05,1.85),label='miss');arrow(ax,(8.45,1.85),(8.95,1.85))
 ax.plot([10.3,10.3,1.5,1.5],[1.3,.85,.85,1.3],color=COLORS[2],linestyle='--');ax.text(5.9,.58,'Later requests reuse admitted templates; fallback does not yet reuse classifier KV.',ha='center',fontsize=9)
 save(fig,'01-architecture')
 fig,axes=plt.subplots(1,2,figsize=(11,4.3));names=['Native Pi','Compact typed','Combined'];arms=['native','typed','combined'];table={}
 for arm in arms:
  rs=[r for r in combined if r['arm']==arm]
  controls=sum(r['attempts'][0].get('control_records',0) for r in rs)
  first=sum(r['attempts'][0]['usage']['completion_tokens'] for r in rs)
  fallback=sum(a['usage']['completion_tokens'] for r in rs for a in r['attempts'][1:])
  table[arm]={'generated':first-controls,'controls':controls,'fallback':fallback,'passed':sum(r['first_passed'] for r in rs)}
 for panel,with_fallback in enumerate([False,True]):
  ax=axes[panel];x=np.arange(3);bottom=np.zeros(3)
  keys=['generated','controls']+(['fallback'] if with_fallback else [])
  for key,color,hatch,label in zip(keys,[COLORS[0],COLORS[1],COLORS[2]],['','///','...'],['First generated','Class controls','Native fallback']):
   vals=np.array([table[a][key] for a in arms]);ax.bar(x,vals,bottom=bottom,color=color,hatch=hatch,label=label,width=.58);bottom+=vals
  for i,total in enumerate(bottom):ax.text(i,total+35,f'{int(total):,}',ha='center',weight='bold')
  ax.set_xticks(x,names);ax.set_ylim(0,2400);ax.set_ylabel('Output units (sum over 10 tasks)');ax.set_title('B  All attempts, including fallback' if with_fallback else 'A  First attempts, including errors');ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 axes[1].legend(fontsize=8,loc='upper right')
 fig.text(.5,.01,'First-attempt behavior passes: 10/10, 8/10, 7/10. Final passes after fallback: 10/10 for all arms.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.05,1,1));save(fig,'02-output-accounting')
 fig,axes=plt.subplots(1,2,figsize=(11,4.4))
 data=[([finite['typed']['time_to_first_token_ms']/1000+finite['typed']['generation_time_ms']/1000,finite['all_classification']['time_to_first_token_ms']/1000],['Compact typed\n4/6 correct','All classification\n2/6 correct'],'A  Finite candidates: six requests per arm'),([jit['baseline']['scheduled_inference_seconds'],jit['jit']['scheduled_inference_seconds']],['Always generate\n9/10 correct','Dynamic codebook\n9/10 correct'],'B  Dynamic codebook: ten tasks per arm')]
 for ax,(vals,labels,title) in zip(axes,data):
  ax.bar(range(2),vals,color=[COLORS[0],COLORS[1]],width=.55)
  for i,v in enumerate(vals):ax.text(i,v+.15,f'{v:.2f} s',ha='center',weight='bold')
  ax.set_xticks(range(2),labels);ax.set_ylim(0,10);ax.set_ylabel('Scheduled-to-last-output interval (s)');ax.set_title(title,fontsize=11);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 fig.text(.5,.01,'Initial queue wait excluded; later scheduling effects remain. Panels are different workloads, not a joint benchmark.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.05,1,1));save(fig,'03-service-intervals')
 rs=[r for r in jrows if 'confidence' in r];fig,ax=plt.subplots(figsize=(10,4.1))
 labels=[]
 for i,r in enumerate(rs):
  correct=r['cache_hit'] or (r.get('generated_validation',{}).get('passed') and r.get('generated_edits')==r['decision']['edits'])
  color=COLORS[1] if correct else '#bb4545';p=r['confidence']['conditional_probability']
  ax.scatter(i,p,s=90,color=color,marker='o' if correct else 'X',zorder=3)
  ax.text(i,p+.028,f'{p:.4f}',ha='center',fontsize=10)
  labels.append(r['case'].replace('_','\n'))
 ax.axhline(.8,color='#555555',ls='--',label='Fixed score threshold = 0.8');ax.set_ylim(0,1.08);ax.set_xlim(-.55,len(rs)-.45)
 ax.scatter([],[],color=COLORS[1],s=70,label='Behaviorally correct candidate');ax.scatter([],[],color='#bb4545',marker='X',s=70,label='Wrong candidate (oracle rejected)')
 ax.set_xticks(range(len(rs)),labels);ax.set_ylabel('Conditional candidate probability');ax.set_title('A higher classification score did not imply a correct reusable edit')
 ax.legend(loc='lower left',fontsize=9);ax.grid(axis='y',alpha=.15);fig.tight_layout();save(fig,'04-gate-reliability')
 extra_figures(jrows)
 (OUT/'data.json').write_text(json.dumps({'sources':SOURCES,'output_accounting':table,'finite_service_seconds':data[0][0],'jit_service_seconds':data[1][0],'languages':['en','zh-CN'],'figures_per_language':10,'illustrative_cost_model':{'measured':False,'B_over_G':0.05,'O_over_G':[0.05,0.2,0.4]},'note':'Figures are descriptive; no confidence intervals or equal-quality speed claim. Break-even curves are illustrative, not measured.'},indent=2))
 print('Wrote ten figures in English and Chinese, each as PNG/SVG/PDF, plus source hashes.')



def canvas(title,height=6):
 fig,ax=plt.subplots(figsize=(12,height));ax.set_xlim(0,12);ax.set_ylim(0,height);ax.axis('off');ax.text(.2,height-.4,title,fontsize=15,weight='bold');return fig,ax


def extra_figures(rows):
 fig,ax=canvas('C1  Replace source serialization with executable edit intent',6.2)
 lanes=[(4.1,'A  Native edit',COLORS[0],['Generate old source\nRepeated context','Generate new source\nRepeated structure','Apply text replacement']),
        (2.45,'B  Compact protocol',COLORS[1],['Select operation: kw','Generate target + values\n--workers, default, 6','Runtime constructs\nthe source change']),
        (.8,'C  Codebook hit',COLORS[2],['Select validated template','Extract new value: 8\nBind existing target/slot','Runtime constructs\nthe source change'])]
 for y,title,color,labels in lanes:
  ax.text(.2,y+1.05,title,weight='bold',color=color)
  for x,label in zip([.3,4.2,8.1],labels):box(ax,x,y,3.5,.85,label,color)
  arrow(ax,(3.8,y+.425),(4.2,y+.425));arrow(ax,(7.7,y+.425),(8.1,y+.425))
 ax.text(6,.2,'Schematic: not token-proportional. A codebook hit generates no argument text.',ha='center',fontsize=9)
 save(fig,'05-protocol-compression')
 fig,ax=canvas('C3  Reuse the prefix across classification and generation',5.4)
 ax.text(.2,4.3,'Separate-request design (conceptual)',weight='bold',color=COLORS[0])
 box(ax,.3,3.2,2.7,.8,'Full context prefill',COLORS[0]);box(ax,3.35,3.2,1.6,.8,'Classify',COLORS[0]);box(ax,5.3,3.2,2.7,.8,'Full context prefill\nagain',COLORS[2]);box(ax,8.35,3.2,3.1,.8,'Generate arguments',COLORS[0])
 for x1,x2 in [(3,3.35),(4.95,5.3),(8,8.35)]:arrow(ax,(x1,3.6),(x2,3.6))
 ax.text(.2,2.55,'Retained-KV engine path (implemented)',weight='bold',color=COLORS[1])
 for x,w,label in [(.3,2.7,'Full context prefill'),(3.35,1.6,'Classify'),(5.3,2.7,'Inject selected suffix\nReuse prefix KV'),(8.35,3.1,'Constrained arguments')]:box(ax,x,1.4,w,.8,label,COLORS[1])
 for x1,x2 in [(3,3.35),(4.95,5.3),(8,8.35)]:arrow(ax,(x1,1.8),(x2,1.8))
 ax.text(6,.7,'10/10 combined calls: identical KV block IDs retained; 1,788–1,830 prefix tokens reused.',ha='center',fontsize=10)
 ax.text(6,.22,'Not to scale. Callback, scheduling and suffix prefill remain. C4 fallback still uses separate requests.',ha='center',fontsize=9)
 save(fig,'06-kv-continuation')
 fig,ax=canvas('C4  Discovery, admission, guarded reuse and invalidation',7.4)
 ax.text(2.8,6.5,'Discovery path',ha='center',weight='bold',color=COLORS[2]);ax.text(8.8,6.5,'Reuse path',ha='center',weight='bold',color=COLORS[1])
 left=['Generate a new edit','Behavior checks + regressions','Admit supported template\nRecord source hash + value binding','Version-bound codebook']
 right=['New task + source snapshot','Retrieve applicable templates\nBind task values','Classify candidates + NONE\nGate and validate','Execute selected edit\nNo argument generation']
 ys=[5.3,3.9,2.5,1.1]
 for y,l,r in zip(ys,left,right):box(ax,.6,y,4.4,.9,l,COLORS[2]);box(ax,6.6,y,4.4,.9,r,COLORS[1])
 for y in ys[:-1]:arrow(ax,(2.8,y),(2.8,y-.5));arrow(ax,(8.8,y),(8.8,y-.5))
 arrow(ax,(5,1.55),(5.8,1.55));ax.plot([5.8,5.8],[1.55,4.35],color='#536575');arrow(ax,(5.8,4.35),(6.6,4.35),label='lookup')
 ax.text(.6,.55,'Failed / unsupported generations are not admitted.',fontsize=9)
 ax.text(6.6,.55,'Changed source, NONE, low score or failed checks: generate.',fontsize=8.5)
 ax.plot([11,11.65,11.65,.25,.25],[2.95,2.95,6.85,6.85,5.75],ls='--',color=COLORS[2]);arrow(ax,(.25,5.75),(.6,5.75),dashed=True)
 ax.text(6,.06,'Prototype validation uses a task oracle; this is not a general correctness guarantee.',ha='center',fontsize=9)
 save(fig,'07-codebook-lifecycle')
 fig,ax=plt.subplots(figsize=(10,4.5));h=np.linspace(0,1,201);binding=.05
 for overhead,color in zip([.05,.2,.4],COLORS):
  ax.plot(h,overhead+h*binding+(1-h),color=color,lw=2,label=f'O/G = {overhead:.2f}')
  point=overhead/(1-binding);ax.scatter(point,1,color=color,s=35)
 ax.axhline(1,color='#777777',ls='--',label='Always-generate baseline');ax.set_xlim(0,1);ax.set_ylim(0,1.5);ax.set_xlabel('Verified hit rate h');ax.set_ylabel('Expected cost / generation cost G');ax.set_title('When does reuse pay off?  h (G − B) > O')
 ax.legend(fontsize=9);ax.grid(alpha=.15)
 fig.text(.5,.01,'Illustrative cost model, NOT measurements. Assumed B/G = 0.05; equal verification costs; no failed-execution term.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.06,1,1));save(fig,'08-break-even-model')
 rs=[r for r in rows if r['arm']=='jit'];fig,axes=plt.subplots(2,1,figsize=(12,5.8),gridspec_kw={'height_ratios':[1.1,1]},sharex=True)
 labels=['workers=6','workers=8','Unicode\ncold','Unicode\nwarm','NaN\nnovel','NaN\nrepeat','workers=12\nnew source','workers=14','guard\nnovel','guard\nrepeat']
 for i,r in enumerate(rs):
  color=COLORS[1] if r['cache_hit'] else COLORS[2] if r['admitted'] else COLORS[0]
  axes[0].bar(i,1,color=color,width=.85)
  axes[0].text(i,.5,'H' if r['cache_hit'] else 'A' if r['admitted'] else 'G',ha='center',va='center',color='white',weight='bold',fontsize=14)
  if r['false_acceptance']:axes[0].scatter(i,1.13,marker='x',s=65,c='#bb4545',linewidths=2)
 axes[0].set_ylim(0,1.35);axes[0].set_yticks([]);axes[0].set_title('Measured codebook lifecycle across ten sequential tasks')
 legend_handles=[Patch(facecolor=color,label=label) for color,label in [(COLORS[1],'H: validated reuse'),(COLORS[2],'A: generation admitted'),(COLORS[0],'G: generation without admission')]]
 axes[0].scatter([],[],marker='x',color='#bb4545',label='Wrong gate acceptance; oracle rejected');handles,labels_=axes[0].get_legend_handles_labels();axes[0].legend(handles=legend_handles+handles,loc='upper center',bbox_to_anchor=(.5,-.03),ncol=2,fontsize=8)
 axes[1].step(range(10),[r['book_size_after'] for r in rs],where='mid',color=COLORS[2],lw=2);axes[1].scatter(range(10),[r['book_size_after'] for r in rs],color=COLORS[2],s=25)
 axes[1].axvline(5.5,ls='--',color='#777777');axes[1].set_ylim(0,4.5);axes[1].set_yticks(range(5));axes[1].set_ylabel('Stored version-bound entries');axes[1].set_xticks(range(10),labels,fontsize=8);axes[1].grid(axis='y',alpha=.15)
 fig.subplots_adjust(hspace=.65,bottom=.18);fig.text(.5,.02,'Source change at task 7 blocks old entries. Four stored records; one validated reuse; two wrong accepts.',ha='center',fontsize=9)
 save(fig,'09-codebook-timeline')
 fig,ax=canvas('C2  Structural validity is a boundary, not semantic correctness',6.2)
 ax.text(3,5.25,'Enforced by the declared interface',ha='center',weight='bold',color=COLORS[1]);ax.text(9,5.25,'Requires separate checks',ha='center',weight='bold',color=COLORS[2])
 left=['Operation name from declared candidates','Target / field from the supported schema','Argument shape and value types','Complete output before call construction']
 right=['Did we choose the intended operation?','Do parameter values satisfy the task?','Is the action authorized in this environment?','Does execution produce the intended effect?']
 for y,l,r in zip([4.25,3.15,2.05,.95],left,right):box(ax,.4,y,5.2,.8,l,COLORS[1]);box(ax,6.4,y,5.2,.8,r,COLORS[2],True)
 ax.text(6,.3,'Observed example: ensure_ascii=False is structurally valid, but does not reject NaN.',ha='center',fontsize=9)
 save(fig,'10-schema-boundary')


ZH = {
'TAIR: four mechanisms, two measured paths':'TAIR：四项机制，两条实测路径',
'Implemented engine path':'已实现的引擎路径',
'Task + source\nRuntime candidates':'任务与源码\n运行时候选',
'C2  Direct logits\nSelect operation\nSelect Schema':'C2  直接读取 logits\n选择操作\n确定参数 Schema',
'C3  Retain KV\nGenerate necessary\narguments':'C3  保留 KV\n只生成必要参数',
'C1  Compact protocol\nValidate + deterministic rewrite\nHarness executes':'C1  紧凑协议\n校验并确定性修改源码\nHarness 执行',
'C4  Dynamic codebook prototype (separate client-side path)':'C4  动态码表原型（独立的客户端路径）',
'Retrieve version-bound\ntemplates + bind values':'检索带版本的模板\n绑定参数值',
'Classify + gate\nHit: select full edit\nNo argument generation':'分类与门控\n命中：选择完整修改\n不生成参数文本',
'Miss: generate\nOracle validation\nAdmit supported edit':'未命中：生成\n任务测试验证\n准入受支持修改',
'Codebook\nTask-bound templates\nSource-version checks':'码表\n任务模板\n源码版本检查',
'miss':'未命中','lookup':'检索',
'Later requests reuse admitted templates; fallback does not yet reuse classifier KV.':'后续请求复用已准入模板；回退尚未复用分类 KV。',
'Native Pi':'原生 Pi','Compact typed':'紧凑类型协议','Combined':'组合路径',
'First generated':'首次生成','Class controls':'分类控制记录','Native fallback':'原生回退',
'Output units (sum over 10 tasks)':'输出单位（10 个任务累计）',
'B  All attempts, including fallback':'B  全部尝试，包含回退','A  First attempts, including errors':'A  首次尝试，包含错误',
'First-attempt behavior passes: 10/10, 8/10, 7/10. Final passes after fallback: 10/10 for all arms.':'首次行为通过：10/10、8/10、7/10；计入回退后，三组均为 10/10。',
'Compact typed\n4/6 correct':'紧凑类型协议\n正确 4/6','All classification\n2/6 correct':'全分类\n正确 2/6',
'Always generate\n9/10 correct':'始终生成\n正确 9/10','Dynamic codebook\n9/10 correct':'动态码表\n正确 9/10',
'A  Finite candidates: six requests per arm':'A  有限候选：每组 6 次请求','B  Dynamic codebook: ten tasks per arm':'B  动态码表：每组 10 个任务',
'Scheduled-to-last-output interval (s)':'首次调度至最后输出区间（秒）',
'Initial queue wait excluded; later scheduling effects remain. Panels are different workloads, not a joint benchmark.':'排除初始排队，保留后续调度影响；两图工作量不同，不是同一组对照。',
'Fixed score threshold = 0.8':'固定分数阈值 = 0.8','Behaviorally correct candidate':'行为正确的候选','Wrong candidate (oracle rejected)':'错误候选（被任务测试拒绝）',
'Conditional candidate probability':'候选条件概率','A higher classification score did not imply a correct reusable edit':'分类分数更高，不代表复用修改正确',
'warm\nworkers':'workers\n复用请求','warm\nunicode':'Unicode\n复用请求','novel\nnan':'新增\nNaN 要求','repeat\nnan':'改写后的\nNaN 要求','warm\nnew\nversion':'新版本\n复用请求',
'C1  Replace source serialization with executable edit intent':'C1  用可执行修改意图替代源码序列化',
'A  Native edit':'A  原生文本编辑','B  Compact protocol':'B  紧凑协议','C  Codebook hit':'C  码表命中',
'Generate old source\nRepeated context':'生成旧源码\n重复上下文','Generate new source\nRepeated structure':'生成新源码\n重复结构','Apply text replacement':'执行文本替换',
'Select operation: kw':'选择操作：kw','Generate target + values\n--workers, default, 6':'生成目标与值\n--workers、default、6','Runtime constructs\nthe source change':'运行时确定性构造\n源码修改',
'Select validated template':'选择已验证模板','Extract new value: 8\nBind existing target/slot':'提取新值：8\n绑定已有目标与参数槽',
'Schematic: not token-proportional. A codebook hit generates no argument text.':'机制示意，长度不代表 Token 数；码表命中时不生成参数文本。',
'C3  Reuse the prefix across classification and generation':'C3  分类与生成之间复用前缀',
'Separate-request design (conceptual)':'独立请求设计（概念对照）','Full context prefill':'完整上下文 prefill','Classify':'分类','Full context prefill\nagain':'再次计算完整\n上下文 prefill','Generate arguments':'生成参数',
'Retained-KV engine path (implemented)':'保留 KV 的引擎路径（已实现）','Inject selected suffix\nReuse prefix KV':'注入选定续写输入\n复用前缀 KV','Constrained arguments':'约束生成参数',
'10/10 combined calls: identical KV block IDs retained; 1,788–1,830 prefix tokens reused.':'10/10 次组合调用保留相同 KV block IDs，复用 1,788–1,830 个前缀 tokens。',
'Not to scale. Callback, scheduling and suffix prefill remain. C4 fallback still uses separate requests.':'非时间比例图；仍有回调、调度和续写 prefill；C4 回退仍使用独立请求。',
'C4  Discovery, admission, guarded reuse and invalidation':'C4  发现、准入、受条件约束的复用与失效',
'Discovery path':'发现路径','Reuse path':'复用路径','Generate a new edit':'生成新修改','Behavior checks + regressions':'行为检查与回归测试',
'Admit supported template\nRecord source hash + value binding':'准入受支持的模板\n记录源码哈希与值绑定','Version-bound codebook':'带版本约束的码表',
'New task + source snapshot':'新任务与源码快照','Retrieve applicable templates\nBind task values':'检索适用模板\n绑定任务中的值',
'Classify candidates + NONE\nGate and validate':'候选与 NONE 分类\n门控与验证','Execute selected edit\nNo argument generation':'执行所选修改\n不生成参数',
'Failed / unsupported generations are not admitted.':'失败或不受支持的生成结果不入表。',
'Changed source, NONE, low score or failed checks: generate.':'源码变化、NONE、低分或验证失败：转生成。',
'Prototype validation uses a task oracle; this is not a general correctness guarantee.':'原型依赖任务测试 oracle 验证，不是通用正确性保证。',
'Always-generate baseline':'始终生成的基线','Verified hit rate h':'经验证的命中率 h','Expected cost / generation cost G':'预期成本 / 生成成本 G',
'When does reuse pay off?  h (G − B) > O':'复用何时有收益？ h (G − B) > O',
'Illustrative cost model, NOT measurements. Assumed B/G = 0.05; equal verification costs; no failed-execution term.':'解释性成本模型，不是实测曲线。假设 B/G = 0.05，验证成本相同，不含错误执行项。',
'Measured codebook lifecycle across ten sequential tasks':'10 个顺序任务中码表生命周期的实测记录',
'H: validated reuse':'H：验证通过的复用','A: generation admitted':'A：生成后准入','G: generation without admission':'G：生成但未准入',
'Wrong gate acceptance; oracle rejected':'门控误接受，被测试拒绝','Stored version-bound entries':'已存储的带版本条目数',
'Unicode\ncold':'Unicode\n冷启动','Unicode\nwarm':'Unicode\n复用请求','NaN\nnovel':'NaN\n新增要求','NaN\nrepeat':'NaN\n改写要求',
'workers=12\nnew source':'workers=12\n源码变化','guard\nnovel':'异常保护\n新增要求','guard\nrepeat':'异常保护\n改写要求',
'Source change at task 7 blocks old entries. Four stored records; one validated reuse; two wrong accepts.':'第 7 个任务源码变化，旧条目失效。共存储 4 条记录、成功复用 1 次、误接受 2 次。',
}

ZH.update({
'C2  Structural validity is a boundary, not semantic correctness':'C2  结构合法是一道边界，不等于语义正确',
'Enforced by the declared interface':'由声明接口约束','Requires separate checks':'需要额外检查',
'Operation name from declared candidates':'操作名称来自声明的候选集合',
'Target / field from the supported schema':'目标与字段来自支持的 Schema',
'Argument shape and value types':'参数结构与值类型符合约束',
'Complete output before call construction':'输出完整后才构造调用对象',
'Did we choose the intended operation?':'是否选择了用户要求的操作？',
'Do parameter values satisfy the task?':'参数值是否满足任务意图？',
'Is the action authorized in this environment?':'当前环境是否授权该操作？',
'Does execution produce the intended effect?':'执行是否产生预期效果？',
'Observed example: ensure_ascii=False is structurally valid, but does not reject NaN.':'实测例子：ensure_ascii=False 结构合法，但不能拒绝 NaN。',
})

if __name__=='__main__':main()
