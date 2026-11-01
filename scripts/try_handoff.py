"""End-to-end handoff test against the running stack (http://localhost).

Run: python scripts/try_handoff.py   (needs ATTENDANT_TOKEN in .env; costs a few model calls)
"""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost"
TOKEN = next(l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8") if l.startswith("ATTENDANT_TOKEN="))


def call(method, path, body=None, token=TOKEN):
    headers = {"Content-Type": "application/json", "X-Attendant-Token": token}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def chat(message, cid=None):
    return call("POST", "/api/chat", {"message": message, **({"conversation_id": cid} if cid else {})})[1]


events = []
def listen():
    req = urllib.request.Request(BASE + "/api/attendant/events", headers={"X-Attendant-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            line = line.decode("utf-8").strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

def redis_cli(*args):
    return subprocess.run(["docker", "compose", "exec", "-T", "redis", "redis-cli", *args],
                          capture_output=True, text=True).stdout.strip()

def show(title, value):
    print(f"\n--- {title}\n{value}")


print("auth sem token:", call("GET", "/api/attendant/conversations/abc", token="")[0],
      "| token errado:", call("GET", "/api/attendant/conversations/abc", token="x")[0])
threading.Thread(target=listen, daemon=True).start()
time.sleep(1)

r = chat("Comprei uma guitarra e chegou com o braço empenado. Já mandei mensagem 3 vezes e ninguém responde, estou muito chateado. Pedido 5.")
cid = r["conversation_id"]
if r["handled_by"] != "human":  # the agent may ask a follow-up first
    show("agente respondeu", r["reply"])
    r = chat("É a guitarra do pedido 5, o braço está torto desde que abri a caixa. Quero falar com alguém da loja.", cid)
show("1. reclamação -> transferência", f"handled_by={r['handled_by']}\n{r['reply']}")
print("TTL da chave (s):", redis_cli("ttl", f"handoff:{cid}"))

r = chat("Alguém aí?", cid)
show("2. cliente em modo humano", r)

time.sleep(1)
show("3. eventos recebidos pelo atendente", json.dumps(events, ensure_ascii=False, indent=1))

show("4. atendente vê a conversa", json.dumps(call("GET", f"/api/attendant/conversations/{cid}")[1], ensure_ascii=False, indent=1)[-700:])
show("5. atendente responde", call("POST", f"/api/attendant/conversations/{cid}/message",
     {"text": "Oi, aqui é o Carlos da loja. Sinto muito pelo transtorno! Vamos trocar a guitarra do pedido 5, sem custo."}))
print("cliente enxerga (após índice 0, últimas 2):", json.dumps(call("GET", f"/api/chat/{cid}")[1]["messages"][-2:], ensure_ascii=False))

show("6. atendente devolve ao agente", call("POST", f"/api/attendant/conversations/{cid}/release"))
r = chat("Valeu! Aproveitando, vocês têm algum violão Yamaha até 1000 reais?", cid)
show("7. agente retoma", f"handled_by={r['handled_by']}\n{r['reply']}")

call("POST", f"/api/attendant/conversations/{cid}/message", {"text": "Voltei só pra confirmar o endereço de coleta."})
redis_cli("expire", f"handoff:{cid}", "1"); time.sleep(2)
r = chat("Pode ser rua das Flores, 10.", cid)
show("8. timeout expirou -> agente", f"handled_by={r['handled_by']}\n{r['reply']}")
