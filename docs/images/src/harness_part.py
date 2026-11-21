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
T(165,146,"quick","lbl",anchor="middle")
P("M360,128 C360,76 230,76 230,124","edge-human","hh")
T(295,66,"questions, request changes","lbl ink-human",anchor="middle"); T(295,82,"(same planner session)","lbl ink-human",anchor="middle")
# brainstorming branch
R(48,300,104,50,"node-ag",6); T(100,330,"brainstorm","t",anchor="middle")
T(100,370,"Opus, read-only","s",anchor="middle"); T(100,384,"rounds of questions","s",anchor="middle")
R(178,300,104,50,"human",25); T(230,323,"approve","t ink-human",anchor="middle"); T(230,340,"design","t ink-human",anchor="middle")
L(100,232,100,298,"edge",None,"hn"); T(92,268,"larger change","lbl",anchor="end")
L(152,318,176,318,"edge-human",None,"hh")
P("M200,352 C200,400 120,400 120,352","edge-human","hh"); T(160,416,"more questions","lbl ink-human",anchor="middle")
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
T(48,568,"Five agents, five sessions: what each one sees and may do","t")
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
