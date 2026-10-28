const API = `http://${location.hostname}:5000/api`;

async function api(path, data) {
  const res = await fetch(API + path, {
    method: data ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: data ? JSON.stringify(data) : undefined,
  });
  return { ok: res.ok, body: await res.json() };
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
  if (r.ok) location.href = "subjects.html";
  else document.getElementById("login-error").textContent = r.body.error;
});

document.getElementById("reg-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await api("/register", {
    role: f.role.value,
    username: identifier(f, f.role.value, "rid1", "rid2", "rname"),
    password: f["new-password"].value,
  });
  if (r.ok) location.href = "subjects.html";
  else document.getElementById("reg-error").textContent = r.body.error;
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

        location.href = "login.html";
      });
    }
  } catch (error) {
    console.error("Session check failed:", error);
    who.textContent = "Connection error";
  }
}

checkSession();
