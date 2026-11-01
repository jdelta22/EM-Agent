"""Browser test of the chat and attendant pages (customer and attendant in two contexts).

Run: uv run --with playwright python scripts/try_ui.py
Uses the installed Chrome, needs the stack up at http://localhost and ATTENDANT_TOKEN in .env.
Screenshots go to the folder given as the first argument (default: the system temp dir).
"""
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost"
TOKEN = next(l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8") if l.startswith("ATTENDANT_TOKEN="))
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "em-ui"
SHOTS.mkdir(parents=True, exist_ok=True)
SLOW = 90_000  # a model answer can take a while


def step(text):
    print(f"- {text}", flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    errors = []

    def new_page(context, name):
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(f"{name}: {e}"))
        page.on("console", lambda m: m.type == "error" and errors.append(f"{name} console: {m.text}"))
        return page

    # ---- landing ----
    landing = new_page(browser.new_context(viewport={"width": 1280, "height": 900}), "landing")
    landing.goto(BASE + "/")
    landing.screenshot(path=SHOTS / "1-landing.png", full_page=True)
    landing.get_by_role("link", name="Conversar com a gente").click()
    expect(landing).to_have_url(BASE + "/chat")
    step("landing -> chat via botão")

    # ---- customer ----
    customer = new_page(browser.new_context(viewport={"width": 480, "height": 800}), "customer")
    customer.goto(BASE + "/chat")
    expect(customer.locator(".msg.agent").first).to_contain_text("assistente virtual")
    expect(customer.locator(".chip")).to_have_count(4)
    customer.screenshot(path=SHOTS / "2-chat-welcome.png")
    step("chat abre com boas-vindas e 4 sugestões")

    customer.get_by_role("button", name="Qual o prazo para devolução?").click()
    expect(customer.locator(".msg.customer")).to_have_count(1)
    expect(customer.locator(".msg.agent")).to_have_count(2, timeout=SLOW)
    expect(customer.locator(".msg.agent").last).to_contain_text("7 dias")
    customer.screenshot(path=SHOTS / "3-chat-answer.png")
    step("sugestão enviada e resposta do agente (7 dias) renderizada")

    customer.reload()
    # the welcome text is UI-only: after a reload only the stored question and answer come back
    expect(customer.locator(".msg.customer")).to_have_count(1)
    expect(customer.locator(".msg.agent")).to_have_count(1)
    expect(customer.locator(".msg.agent")).to_contain_text("7 dias")
    step("recarregar a página restaura a conversa")

    customer.locator("#input").fill("Quero falar com um atendente. Meu pedido 5 chegou com defeito.")
    customer.locator("#input").press("Enter")
    expect(customer.locator("#status")).to_have_text("Atendente da loja", timeout=SLOW)
    customer.screenshot(path=SHOTS / "4-chat-transferred.png")
    step("pedido de atendente -> status vira 'Atendente da loja'")

    # ---- attendant ----
    desk = new_page(browser.new_context(viewport={"width": 1280, "height": 800}), "attendant")
    desk.goto(BASE + "/atendente")
    desk.locator("#token").fill("token-errado")
    desk.get_by_role("button", name="Entrar").click()
    expect(desk.locator("#login-error")).to_contain_text("Token inválido")
    step("token errado é recusado")

    desk.locator("#token").fill(TOKEN)
    desk.get_by_role("button", name="Entrar").click()
    expect(desk.locator("#live-text")).to_have_text("Ao vivo", timeout=15_000)
    item = desk.locator(".q-item").first
    expect(item).to_be_visible()
    expect(item.locator(".reason")).to_contain_text("pedido")  # the agent's summary for the attendant
    desk.screenshot(path=SHOTS / "5-desk-queue.png")
    step("atendente entra, fica 'Ao vivo' e vê a conversa na fila com o resumo do agente")

    item.click()
    expect(desk.locator(".msg.customer").last).to_contain_text("pedido 5")
    desk.screenshot(path=SHOTS / "6-desk-open.png")
    step("abrir a conversa mostra o histórico")

    desk.locator("#input").fill("Oi! Aqui é o Carlos da loja. Vamos resolver o seu pedido.")
    desk.locator("#input").press("Enter")
    expect(customer.locator(".msg.attendant")).to_contain_text("Carlos", timeout=15_000)
    customer.screenshot(path=SHOTS / "7-chat-attendant-reply.png")
    step("resposta do atendente chega ao cliente por polling")

    customer.locator("#input").fill("Obrigado, Carlos! Posso mandar foto?")
    customer.locator("#input").press("Enter")
    expect(desk.locator(".msg.customer").last).to_contain_text("mandar foto", timeout=15_000)
    desk.screenshot(path=SHOTS / "8-desk-customer-msg.png")
    step("mensagem do cliente chega ao atendente em tempo real (SSE)")

    in_queue = desk.locator(".q-item").count()
    desk.once("dialog", lambda d: d.accept())  # the confirm() must be accepted before the click
    desk.get_by_role("button", name="Devolver ao assistente").click()
    step("atendente devolve ao assistente")
    expect(customer.locator(".msg.system")).to_contain_text("voltou para o assistente", timeout=15_000)
    expect(customer.locator("#status")).to_have_text("Assistente virtual")
    customer.screenshot(path=SHOTS / "9-chat-released.png")
    step("cliente é avisado de que o assistente voltou")

    expect(desk.locator(".q-item")).to_have_count(in_queue - 1, timeout=15_000)
    step("a conversa sai da fila")

    # ---- a markup injection attempt must stay text ----
    customer.locator("#input").fill('<img src=x onerror="window.pwned=1"> **negrito**')
    customer.locator("#input").press("Enter")
    expect(customer.locator(".msg.customer").last).to_contain_text("<img src=x")
    assert customer.evaluate("window.pwned") is None
    step("HTML digitado pelo cliente aparece como texto, sem executar")

    browser.close()

print("\nerros de JS/console:", errors or "nenhum")
print("capturas em:", SHOTS)
