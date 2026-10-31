const API = `http://${location.hostname}:5000/api`;

async function api(path, data, method) {
  const res = await fetch(API + path, {
    method: method || (data ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: data ? JSON.stringify(data) : undefined,
  });
  return { ok: res.ok, body: await res.json() };
}

function confirmDeletion(message) {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "delete-confirmation";
    dialog.setAttribute("aria-labelledby", "delete-confirmation-title");
    dialog.innerHTML = `
      <form method="dialog">
        <h2 id="delete-confirmation-title">Confirm deletion</h2>
        <p class="delete-confirmation-message"></p>
        <div class="modal-actions">
          <button class="btn secondary-button" value="cancel">Cancel</button>
          <button class="btn danger-button" value="confirm">Delete</button>
        </div>
      </form>`;
    dialog.querySelector(".delete-confirmation-message").textContent = message;
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "confirm");
      dialog.remove();
    }, { once: true });
    dialog.showModal();
  });
}

// Students sign in with their ID number (TUPT-YY-NNNN); faculty use their name.
function identifier(f, role, year, num, name) {
  if (role === "faculty") return f[name].value.trim();
  return `TUPT-${f[year].value}-${f[num].value}`;
}

document.getElementById("login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await api("/login", {
    username: identifier(f, f.role.value, "id1", "id2", "name"),
    password: f.password.value,
  });
  if (r.ok) location.replace("subjects.html");
  else document.getElementById("login-error").textContent = r.body.error;
});

document.getElementById("reg-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await api("/register", {
    role: f.role.value,
    username: identifier(f, f.role.value, "rid1", "rid2", "rname"),
    password: f["new-password"].value,
    email: f.email.value.trim(),
  });
  if (r.ok) {
    const message = document.getElementById("reg-error");
    message.classList.add("success");
    message.textContent =
      r.body.message || "Check your email to verify your account before logging in.";
    f.reset();
  } else {
    const message = document.getElementById("reg-error");
    message.classList.remove("success");
    message.textContent = r.body.error;
  }
});


async function checkSession() {
  const who = document.getElementById("who");
  const logout = document.getElementById("logout");

  if (!who) return;

  try {
    const res = await fetch(
      `http://${location.hostname}:5000/api/me`,
      { credentials: "include" }
    );

    if (!res.ok) {
      who.textContent = "Not logged in";
      location.replace("login.html");
      return;
    }

    const user = await res.json();
    who.textContent = user.username || user.name || user.role || "Logged in";

    if (logout) {
      logout.addEventListener("click", async () => {
        await fetch(`http://${location.hostname}:5000/api/logout`, {
          method: "POST",
          credentials: "include"
        });

        location.replace("login.html");
      });
    }
  } catch (error) {
    console.error("Session check failed:", error);
    who.textContent = "Connection error";
  }
}

checkSession();

window.addEventListener("pageshow", event => {
  if (event.persisted) {
    location.reload();
  }
});

document.querySelectorAll("[data-back-button]").forEach(button => {
  button.addEventListener("click", () => {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }

    location.href = button.dataset.fallback || "subjects.html";
  });
});
