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

document.getElementById("login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await api("/login", {
    username: `TUPT-${f.id1.value}-${f.id2.value}`,
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
    username: `TUPT-${f.rid1.value}-${f.rid2.value}`,
    password: f["new-password"].value,
  });
  if (r.ok) location.href = "subjects.html";
  else document.getElementById("reg-error").textContent = r.body.error;
});