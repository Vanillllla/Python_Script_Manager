function msg(key, fallback = "") {
  return (window.pysmMessages && window.pysmMessages[key]) || fallback || key;
}

async function apiRequest(method, endpoint, payload = null) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (payload !== null) {
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(endpoint, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed: ${response.status}`);
  }
  return data;
}

function formPayload(form) {
  const formData = new FormData(form);
  const payload = {};
  for (const [key, value] of formData.entries()) {
    if (value === "true") {
      payload[key] = true;
    } else if (value === "false") {
      payload[key] = false;
    } else if (/^\d+$/.test(value)) {
      payload[key] = Number(value);
    } else {
      payload[key] = value;
    }
  }
  return payload;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.hidden = false;
  toast.textContent = message;
  toast.style.background = isError ? "#ab3b27" : "#0d6b54";
  window.setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}

function bindApiForms() {
  document.querySelectorAll("[data-api-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await apiRequest(
          form.dataset.method || "POST",
          form.dataset.endpoint,
          formPayload(form),
        );
        showToast(form.dataset.success || msg("frontend.toast.saved", "Saved."));
        window.setTimeout(() => window.location.reload(), 300);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function bindScriptActions() {
  document.querySelectorAll("[data-script-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await apiRequest(button.dataset.method || "POST", button.dataset.endpoint, {});
        showToast(data.message || data.status || msg("frontend.toast.action_complete", "Action complete."));
        window.setTimeout(() => window.location.reload(), 350);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function bindScriptRemoval() {
  document.querySelectorAll("[data-remove-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const scriptId = Number(button.dataset.scriptId);
      const scriptName = button.dataset.scriptName || `#${scriptId}`;
      const confirmation = msg(
        "frontend.confirm.remove_script",
        "Remove this script?",
      )
        .replace("{id}", String(scriptId))
        .replace("{name}", scriptName);
      if (!window.confirm(confirmation)) {
        return;
      }
      try {
        const data = await apiRequest("DELETE", "/api/scripts", { script_ids: [scriptId] });
        showToast(data.message || msg("frontend.toast.action_complete", "Action complete."));
        window.setTimeout(() => window.location.reload(), 350);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function bindManagerAutostart() {
  document.querySelectorAll("[data-manager-autostart]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const data = await apiRequest("POST", "/api/autostart/manager", {
          enabled: button.dataset.enabled === "true",
        });
        showToast(data.message || msg("frontend.toast.autostart_updated", "Autostart updated."));
        window.setTimeout(() => window.location.reload(), 300);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function bindModuleLinks() {
  const output = document.getElementById("modules-output");
  if (output && !output.textContent.trim()) {
    output.textContent = msg("frontend.modules.empty", "Select an environment to list installed modules.");
  }
  document.querySelectorAll("[data-open-modules]").forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        const modules = await apiRequest(
          "GET",
          `/api/interpreters/${link.dataset.environmentId}/modules`,
        );
        output.textContent = modules.map((item) => `${item.name}==${item.version}`).join("\n");
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function initTerminal() {
  const root = document.getElementById("terminal-root");
  const fallback = document.getElementById("terminal-fallback");
  const form = document.getElementById("terminal-input-form");
  if (!root || !form) return;
  const scriptId = root.dataset.scriptId;
  let terminalWriter;

  if (window.Terminal) {
    const terminal = new window.Terminal({
      convertEol: true,
      cursorBlink: true,
      theme: {
        background: "#121816",
        foreground: "#d3f1e0",
      },
    });
    terminal.open(root);
    terminal.write(msg("frontend.terminal.connecting", "Connecting to script console...\r\n"));
    terminalWriter = (chunk) => terminal.write(chunk);
  } else {
    root.hidden = true;
    fallback.hidden = false;
    fallback.textContent = msg("frontend.terminal.connecting", "Connecting to script console...\r\n");
    terminalWriter = (chunk) => {
      fallback.textContent += chunk;
      fallback.scrollTop = fallback.scrollHeight;
    };
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/api/scripts/${scriptId}/terminal`);

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "snapshot") {
      terminalWriter(payload.content || "");
    } else if (payload.type === "chunk") {
      terminalWriter(payload.content || "");
    } else if (payload.type === "error") {
      showToast(payload.message || msg("frontend.terminal.error", "Terminal error"), true);
    }
  });

  socket.addEventListener("close", () => {
    terminalWriter(msg("frontend.terminal.disconnected", "\r\n[terminal disconnected]\r\n"));
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("terminal-input");
    const value = input.value;
    if (!value) return;
    try {
      await apiRequest("POST", `/api/scripts/${scriptId}/terminal/input`, {
        data: `${value}\r\n`,
      });
      input.value = "";
    } catch (error) {
      showToast(error.message, true);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindApiForms();
  bindScriptActions();
  bindScriptRemoval();
  bindManagerAutostart();
  bindModuleLinks();
  initTerminal();
});
