# backend/main.py
import asyncio
import random
import uuid
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone

app = FastAPI(title="SIMGuard Central - Demo")

# Allow local frontend to connect (demo). Tighten origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory demo datastore (replace with DB for production)
state = {
    "sims": [
        {"id":"sim-0825550101","number":"082 555 0101","locked":True,"last":"No issues in 12h"},
        {"id":"sim-0825550102","number":"082 555 0102","locked":False,"last":"Unlocked by user 2h ago"},
        {"id":"sim-0812227788","number":"081 222 7788","locked":True,"last":"Auto-locked on risk spike"}
    ],
    "registered": [
        {"id":"reg-0601239999","number":"060 123 9999","relation":"Unknown","risk":"high"},
        {"id":"reg-0724001100","number":"072 400 1100","relation":"Old device","risk":"medium"},
        {"id":"reg-0825550102","number":"082 555 0102","relation":"Primary","risk":"low"}
    ],
    "alerts": [
        {"id":str(uuid.uuid4()), "ts":datetime.now(timezone.utc).isoformat(), "text":"System ready. Monitoring enabled.", "level":"info"}
    ],
    "activity": []
}

# WebSocket manager to broadcast alerts
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: Dict):
        living = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
                living.append(ws)
            except Exception:
                # ignore broken connections
                pass
        self.active = living

manager = ConnectionManager()

# Models
class Action(BaseModel):
    sim_id: str
    action: str  # "lock" | "unlock"

class RecoveryRequest(BaseModel):
    sim_id: str
    step: str

# Helpers
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def add_log(text: str):
    entry = {"id": str(uuid.uuid4()), "ts": now_iso(), "text": text}
    state["activity"].insert(0, entry)
    state["activity"] = state["activity"][:200]

def add_alert(text: str, level: str = "warn"):
    entry = {"id": str(uuid.uuid4()), "ts": now_iso(), "text": text, "level": level}
    state["alerts"].insert(0, entry)
    state["alerts"] = state["alerts"][:200]
    return entry

def find_sim(sim_id: str):
    for sim in state["sims"]:
        if sim["id"] == sim_id:
            return sim
    return None

# REST endpoints
@app.get("/sims")
async def get_sims():
    return {"sims": state["sims"], "registered": state["registered"], "alerts": state["alerts"], "activity": state["activity"]}

@app.post("/action")
async def take_action(action: Action):
    sim = find_sim(action.sim_id)
    if not sim:
        return {"error": "SIM not found"}
    if action.action == "lock":
        sim["locked"] = True
        sim["last"] = "Locked by user • " + now_iso()
        add_log(f"{sim['number']} locked via API")
        alert = add_alert(f"SIM {sim['number']} locked by user", "info")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"status":"locked","sim":sim}
    elif action.action == "unlock":
        sim["locked"] = False
        sim["last"] = "Unlocked by user • " + now_iso()
        add_log(f"{sim['number']} unlocked via API")
        alert = add_alert(f"SIM {sim['number']} unlocked by user", "warn")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"status":"unlocked","sim":sim}
    return {"error":"unknown action"}

@app.post("/recovery")
async def recovery(req: RecoveryRequest):
    sim = find_sim(req.sim_id)
    if not sim:
        return {"error":"SIM not found"}
    step = req.step
    if step == "freeze":
        sim["locked"] = True
        alert = add_alert(f"Recovery: SIM {sim['number']} frozen via wizard", "info")
        add_log(f"Recovery freeze for {sim['number']}")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"ok":True}
    elif step == "reset":
        alert = add_alert(f"Recovery: password reset initiated for {sim['number']}", "warn")
        add_log(f"Recovery reset triggered for {sim['number']}")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"ok":True}
    elif step == "notify-bank":
        alert = add_alert(f"Recovery: bank partners notified for {sim['number']}", "warn")
        add_log(f"Recovery notify-bank for {sim['number']}")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"ok":True}
    elif step == "open-case":
        ref = random.randint(10000,99999)
        alert = add_alert(f"Recovery: Telco case opened for {sim['number']} (Ref #{ref})", "danger")
        add_log(f"Recovery open-case for {sim['number']} ref {ref}")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"ok":True}
    elif step == "police":
        alert = add_alert(f"Recovery: SAPS note generated for {sim['number']}", "danger")
        add_log(f"Recovery police note for {sim['number']}")
        await manager.broadcast({"type":"alert","payload": alert})
        return {"ok":True}
    return {"error":"unknown step"}

@app.get("/risk/{sim_id}")
async def risk_score(sim_id: str):
    sim = find_sim(sim_id)
    if not sim:
        return {"error":"SIM not found"}
    score = random.choices(["Low","Medium","High"], weights=[60,30,10])[0]
    return {"sim_id": sim_id, "risk": score}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # send initial state
        await websocket.send_json({"type":"init","payload": {"sims": state["sims"], "registered": state["registered"], "alerts": state["alerts"], "activity": state["activity"]}})
        while True:
            # keep connection alive; accept optional pings from client
            data = await websocket.receive_text()
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background simulator (auto events)
async def simulator_loop():
    while True:
        await asyncio.sleep(random.randint(10, 25))
        choice = random.random()
        if choice < 0.6:
            sim = random.choice(state["sims"])
            add_log(f"Suspicious SIM-swap attempt detected for {sim['number']}")
            alert = add_alert(f"⚠️ Suspicious SIM-swap attempt detected for {sim['number']}", "warn")
            if not sim["locked"]:
                sim["locked"] = True
                sim["last"] = "Auto-locked on risk • " + now_iso()
                add_log(f"{sim['number']} auto-locked due to risk")
                auto_alert = add_alert(f"Auto-locked {sim['number']} due to high risk", "danger")
                await manager.broadcast({"type":"alert","payload": alert})
                await manager.broadcast({"type":"alert","payload": auto_alert})
            else:
                await manager.broadcast({"type":"alert","payload": alert})
        else:
            new_number = f"07{random.randint(100000000,999999999)}"
            entry = {"id": f"reg-{str(uuid.uuid4())[:8]}", "number": new_number, "relation":"Unknown", "risk": random.choice(["low","medium","high"])}
            state["registered"].insert(0, entry)
            add_log(f"New SIM {new_number} registered to your ID on remote ISP")
            alert = add_alert(f"New SIM {new_number} registered to your ID — auto-frozen pending review", "danger")
            new_sim = {"id": str(uuid.uuid4()), "number": new_number, "locked": True, "last": "Auto-locked on registration • " + now_iso()}
            state["sims"].insert(0, new_sim)
            add_log(f"Auto-added and locked {new_number} to local SIM list")
            await manager.broadcast({"type":"alert","payload": alert})
            await manager.broadcast({"type":"state","payload": {"sims": state["sims"], "registered": state["registered"]}})

# Start simulator on startup
@app.on_event("startup")
async def start_simulator():
    asyncio.create_task(simulator_loop())
