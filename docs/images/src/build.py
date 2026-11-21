import sys
from html import escape as e
out=[]
def R(x,y,w,h,cls,rx=6): out.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')
def T(x,y,txt,cls="",anchor=None,extra=""):
    a=f' text-anchor="{anchor}"' if anchor else ""
    c=f' class="{cls}"' if cls else ""
    out.append(f'<text{c} x="{x}" y="{y}"{a}{extra}>{e(txt)}</text>')
def L(x1,y1,x2,y2,cls,start=None,end=None):
    s=f' marker-start="url(#{start})"' if start else ""
    t=f' marker-end="url(#{end})"' if end else ""
    out.append(f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{s}{t}/>')
def P(d,cls,end=None,start=None):
    s=f' marker-start="url(#{start})"' if start else ""
    t=f' marker-end="url(#{end})"' if end else ""
    out.append(f'<path class="{cls}" d="{d}"{s}{t}/>')
def chip(x,y,w,txt,kind,h=28,dashed=False):
    R(x,y,w,h,f"chip-{kind}"+(" planned" if dashed else ""),4)
    T(x+10,y+h/2+4.5,txt,"ct")
def comp(x,y,w,h,kind,title,sub=None,dashed=False,mono=False):
    R(x,y,w,h,f"c-{kind}"+(" planned" if dashed else ""),8)
    T(x+14,y+26,title,f"t ink-{kind}"+(" mono" if mono else ""))
    if sub: T(x+w-14,y+26,sub,"s",anchor="end")
def markers(prefix):
    for name,cls in [("n","ah"),("h","ah-human"),("a","ah-api")]:
        out.append(f'<marker id="{prefix}{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path class="{cls}" d="M0,0 L10,5 L0,10 z"/></marker>')

# ---------- SYSTEM ----------
out.append('<svg viewBox="0 0 1200 990" role="img" aria-label="The hub on Vercel stores workflow releases, run events and analytics. Clients fetch pinned releases over an API with frozen contracts. A local runner executes the LangGraph workflow in a git worktree and drives claude -p agents, sends run events back to the hub, and opens a PR only after a human approves.">')
out.append('<defs>'); markers("s"); out.append('</defs>')
# hub zone
R(40,24,880,290,"z-hub",12); T(60,52,"JIGWORKS HUB · VERCEL","zt ink-hub")
cols=[("Hub API","FastAPI",["Sandbox validation","Immutable releases","Channels: stable, beta","Event ingest + SSE"]),
      ("Postgres","Neon",["Drafts + releases","Digest per release","Run events = audit","Price list by date"]),
      ("Analytics",None,["Cost per node","Fix rounds, duration","Compare releases","Human delta"]),
      ("Web hub","React Flow",["Python editor","Read-only graph","Publish a release","Runs & analytics"])]
x=56
for i,(t,sub,chips) in enumerate(cols):
    comp(x,68,206,230,"hub",t,sub)
    for j,c in enumerate(chips):
        chip(x+12,108+j*44,182,c,"hub",h=34,dashed=(c=="Human delta"))
    x+=216
comp(960,40,200,140,"gh","GitHub",None,dashed=True)
T(974,86,"one repo per workflow","s")
chip(972,100,176,"Push → updates draft","gh",h=30); chip(972,138,176,"Save → commits","gh",h=30)
L(958,125,902,125,"edge planned","sn","sn")
comp(960,200,200,100,"gh","GitHub")
T(974,244,"VaOndrej/jigworks","s mono")
T(974,262,"hub source code","s")
T(974,282,"Vercel deploys on push","s")
L(958,250,922,250,"edge",None,"sn")
# api band
R(40,348,1120,44,"z-api",10)
T(60,375,"API · REST + SSE","t ink-api")
T(1140,375,"frozen contracts: packages/contracts → TS + Python types","s mono",anchor="end")
# clients zone
R(200,428,960,140,"z-cli",12); T(1140,452,"CLIENTS","zt ink-cli",anchor="end")
comp(216,460,240,96,"cli","VS Code extension")
chip(228,494,104,"Prompt","cli",h=24); chip(340,494,104,"Live steps","cli",h=24)
chip(228,524,104,"Approvals","cli",h=24); chip(340,524,104,"Cost per run","cli",h=24)
comp(472,460,180,96,"cli","Jigworks CLI")
for k,(cx,cy,c) in enumerate([(484,494,"run"),(568,494,"approve"),(484,524,"resume"),(568,524,"audit")]):
    chip(cx,cy,76,c,"cli",h=24)
comp(684,460,220,96,"cli","Other IDE, CI or PR bot",dashed=True)
T(698,508,"any client that speaks","s"); T(698,526,"the same contracts","s")
comp(920,460,226,96,"cli","Portal for non-engineers",dashed=True)
T(934,508,"same runner, a workflow","s"); T(934,526,"with team-specific checks","s")
# engineer
R(40,470,140,76,"human",38)
T(110,503,"Engineer","t ink-human",anchor="middle"); T(110,523,"decides at interrupts","s",anchor="middle")
L(182,508,212,508,"edge-human",None,"sh")
# machine zone
R(200,616,960,250,"z-run",12); T(1140,640,"ENGINEER'S MACHINE · ONE GIT WORKTREE PER SESSION","zt ink-run",anchor="end")
L(240,558,240,664,"edge",None,"sn"); T(250,596,"starts the runner","lbl")
comp(216,668,500,182,"run","Local runner","Python · uv venv per digest")
rc=[["LangGraph graph (pinned)","Checkpoint + git commit"],["Gate: tests, invariants","Secret scan + bandit"],["Owns git: commit, push, PR","Audit log, offline queue"]]
for r,row in enumerate(rc):
    for c,txt in enumerate(row):
        chip(230+c*238,708+r*44,230,txt,"run",h=34)
comp(800,668,344,182,"ag","claude -p","fresh session per role",mono=True)
ac=[["Plan · Opus","Tests · Opus"],["Implement · Sonnet","Review · Opus"],["Fix · Sonnet","Summary · Sonnet"]]
for r,row in enumerate(ac):
    for c,txt in enumerate(row):
        chip(814+c*162,708+r*40,154,txt,"ag",h=32)
T(814,840,"allowlisted tools · no push, gh or network","s")
L(718,740,796,740,"edge",None,"sn"); T(757,732,"prompt","lbl",anchor="middle")
L(796,790,718,790,"edge",None,"sn"); T(757,810,"stream-json","lbl",anchor="middle")
# product repo
comp(216,912,500,60,"gh","Product repo on GitHub")
T(230,958,"a human reviews and merges; agents never merge","s")
L(460,852,460,908,"edge-human",None,"sh"); T(472,890,"branch + PR, only after the engineer approves","lbl ink-human")
# api arrows drawn last, over the zones
L(240,316,240,456,"edge-api",None,"sa"); T(250,338,"release .zip + digest","lbl ink-api")
L(668,668,668,316,"edge-api",None,"sa"); T(678,338,"run events, usage, approvals (queued offline)","lbl ink-api")
# legend
L(800,926,840,926,"edge"); T(850,930,"built","s")
L(910,926,950,926,"edge planned"); T(960,930,"designed, not built","s")
L(800,954,840,954,"edge-human"); T(850,958,"a human decides","s")
L(960,954,1000,954,"edge-api"); T(1010,958,"over the API","s")
out.append('</svg>')
system="\n".join(out); out.clear()

# ---------- HARNESS ----------
out.append('<svg viewBox="0 0 1240 960" role="img" aria-label="The feature-development graph: triage picks a quick path or brainstorming, the plan is approved by the engineer, a separate agent writes tests from the plan only, another implements, an independent agent reviews, the gate runs code checks, the engineer approves the PR. Each agent is its own claude -p session with its own context and tool rules.">')
out.append('<defs>'); markers("h"); out.append('</defs>')
nodes=[("triage","ag","Sonnet, read-only","quick fix or design first?"),("plan","ag","Opus, read-only",None),
       ("approve plan","human","engineer",None),
       ("write tests","ag","Opus","sees the plan, not code"),("implement","ag","Sonnet","may not edit tests"),
       ("review","ag","Opus, read-only","findings with IDs"),("gate","code","runner code, no LLM","tests, invariants,"),
       ("approve PR","human","engineer",None),("open PR","code","runner",None)]
for i,(n,k,l1,l2) in enumerate(nodes):
    x=48+i*130
    R(x,130,104,50,"human" if k=="human" else f"node-{k}",25 if k=="human" else 6)
    T(x+52,160,n,"t "+("ink-human" if k=="human" else ""),anchor="middle")
    T(x+52,200,l1,"s"+(" ink-human" if k=="human" else ""),anchor="middle")
    if l2: T(x+52,214,l2,"s",anchor="middle")
    if n=="gate": T(x+52,228,"secrets, bandit","s",anchor="middle")
    if i<8:
        hum = k=="human" or nodes[i+1][1]=="human"
        L(x+104,155,x+128,155,"edge-human" if hum else "edge",None,"hh" if hum else "hn")
T(165,118,"quick","lbl",anchor="middle")
P("M360,128 C360,76 230,76 230,124","edge-human","hh")
T(295,66,"questions, request changes","lbl ink-human",anchor="middle"); T(295,82,"(same planner session)","lbl ink-human",anchor="middle")
# brainstorming branch
R(48,300,104,50,"node-ag",6); T(100,330,"brainstorm","t",anchor="middle")
T(100,370,"Opus, read-only","s",anchor="middle"); T(100,384,"rounds of questions","s",anchor="middle")
R(178,300,104,50,"human",25); T(230,323,"approve","t ink-human",anchor="middle"); T(230,340,"design","t ink-human",anchor="middle")
L(100,232,100,298,"edge",None,"hn"); T(92,268,"larger change","lbl",anchor="end")
L(152,318,176,318,"edge-human",None,"hh")
P("M205,298 C205,262 135,262 135,296","edge-human","hh"); T(170,254,"more questions","lbl ink-human",anchor="middle")
L(260,298,260,232,"edge-human",None,"hh"); T(268,268,"design agreed","lbl ink-human")
# fix loop
R(698,300,104,50,"node-ag",6); T(750,330,"fix","t",anchor="middle"); T(690,345,"Sonnet","s",anchor="end")
L(735,222,735,298,"edge","hn","hn"); T(727,268,"FAIL, then re-check","lbl",anchor="end")
P("M880,236 C880,300 840,318 806,320","edge","hn"); T(890,276,"FAIL","lbl")
P("M1010,210 C1010,340 900,350 806,338","edge-human","hh"); T(962,352,"request changes","lbl ink-human")
R(698,410,104,50,"human",25); T(750,440,"approve fix","t ink-human",anchor="middle")
L(750,352,750,408,"edge-human","hh","hh")
T(764,386,"no progress in 2 rounds, cap of 8, or a question","lbl ink-human")
T(736,386,"continue +3, answer, or stop","lbl ink-human",anchor="end")
L(48,500,560,500,"rule"); T(48,492,"every node: LangGraph checkpoint + git commit, so a run resumes after a crash or a usage limit","s")
# legend
R(900,474,16,16,"node-ag",3); T(924,487,"agent (claude -p)","s")
R(1060,474,16,16,"node-code",3); T(1084,487,"runner code","s")
R(900,500,16,16,"human",8); T(924,513,"engineer decides","s")

# per-agent context and rules
T(48,568,"Separate sessions: what each building agent sees and may do","t")
cards=[("plan","Opus",
        [("SESSION",["new; resumed for","questions and changes"]),("SEES",["the task, the agreed design,","the repo (read-only)"]),
         ("TOOLS",["read, grep, git diff/log"]),("OUTPUT",["plan: files, checks,","milestones"])]),
       ("write tests","Opus",
        [("SESSION",["new"]),("SEES",["the task + the approved plan","never the implementation"]),
         ("TOOLS",["edit, run the repo's tests"]),("RULE",["tests from the spec,","before any code exists"])]),
       ("implement","Sonnet",
        [("SESSION",["new"]),("SEES",["the task, the plan,","the test writer's summary"]),
         ("TOOLS",["edit, run tests, scanners"]),("MAY NOT",["edit the tests, test config","or INVARIANTS.md (gate)"])]),
       ("review","Opus",
        [("SESSION",["new, did not write","the code"]),("SEES",["the plan + the diff","since the base commit"]),
         ("TOOLS",["read only"]),("OUTPUT",["PASS / FAIL, findings","F1, F2 … re-checked by ID"])]),
       ("fix","Sonnet",
        [("SESSION",["resumes the","implementer's session"]),("SEES",["its own change, the findings","or gate report, your answers"]),
         ("TOOLS",["edit, run tests, scanners"]),("MAY NOT",["the same protected files;","blocked → asks the human"])])]
for i,(name,model,rows) in enumerate(cards):
    x=48+i*230; y=588; w=218
    R(x,y,w,290,"card",8)
    R(x,y,w,34,"card-head",8); R(x,y+20,w,14,"card-head",0)
    T(x+12,y+23,name,"t"); T(x+w-12,y+23,model,"s",anchor="end")
    yy=y+56
    for label,lines in rows:
        T(x+12,yy,label,"cap"+(" ink-human" if label=="MAY NOT" else ""))
        for k,ln in enumerate(lines):
            T(x+12,yy+18+k*16,ln,"ct"+(" strong" if (name=="write tests" and label=="SEES" and k==1) else ""))
        yy+=18+len(lines)*16+14
T(48,912,"Every agent: allowlisted tools only. Denied to all: git push, commit, reset, checkout, gh, curl, web fetch and search.","s")
T(48,930,"The runner, not an agent, owns git and opens the PR.","s")
out.append('</svg>')
harness="\n".join(out)

tpl=open(sys.argv[1]).read()
open(sys.argv[2],'w').write(tpl.replace("%%SYSTEM%%",system).replace("%%HARNESS%%",harness))
