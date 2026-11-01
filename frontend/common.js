// Shared helpers for the chat and attendant pages.

// Renders the small subset of markdown the agent uses (paragraphs, "- " / "1." lists, **bold**)
// using DOM nodes only, never innerHTML, so message text can never inject markup.
function renderRich(container, text) {
  let list = null;
  const closeList = () => { list = null; };
  const inline = (parent, str) => {
    str.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
      if (/^\*\*[^*]+\*\*$/.test(part)) {
        const strong = document.createElement("strong");
        strong.textContent = part.slice(2, -2);
        parent.appendChild(strong);
      } else if (part) {
        parent.appendChild(document.createTextNode(part));
      }
    });
  };

  for (const line of text.split("\n")) {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const tag = bullet ? "UL" : "OL";
      if (!list || list.tagName !== tag) {
        list = document.createElement(tag.toLowerCase());
        container.appendChild(list);
      }
      const li = document.createElement("li");
      inline(li, (bullet || numbered)[1]);
      list.appendChild(li);
    } else if (line.trim()) {
      closeList();
      const p = document.createElement("p");
      inline(p, line);
      container.appendChild(p);
    } else {
      closeList();
    }
  }
}

// Builds a message bubble. `role` is customer | agent | attendant | system | error.
function messageEl(role, text, who) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  if (who) {
    const label = document.createElement("span");
    label.className = "who";
    label.textContent = who;
    el.appendChild(label);
  }
  if (role === "customer" || role === "system" || role === "error") {
    const p = document.createElement("p");
    p.textContent = text;
    el.appendChild(p);
  } else {
    renderRich(el, text);
  }
  return el;
}

function typingEl() {
  const el = document.createElement("div");
  el.className = "typing";
  el.innerHTML = "<i></i><i></i><i></i>"; // static markup, no user data
  return el;
}

function scrollToEnd(scroller) {
  scroller.scrollTop = scroller.scrollHeight;
}

// Enter sends, Shift+Enter makes a new line; the box grows with the text.
function setupComposer(textarea, form) {
  const grow = () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
  };
  textarea.addEventListener("input", grow);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  return { reset: () => { textarea.value = ""; grow(); } };
}
