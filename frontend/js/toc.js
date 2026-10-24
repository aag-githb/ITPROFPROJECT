const params = new URLSearchParams(location.search);
const subjectId = params.get("subject");
const list = document.getElementById("list");
const emptyEl = document.getElementById("empty");
let role = "";

if (!subjectId) location.href = "subjects.html";

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

// A topic is open if it's the first one, the viewer is faculty, or the previous topic's quiz was passed (75%+).
function row(t, idx, all) {
  const isFaculty = role === "faculty";
  const prevPassed = idx === 0 || all[idx - 1].status === "passed";
  const locked = !isFaculty && !prevPassed;

  const li = el("li", undefined, locked ? "locked" : "");
  const n = el("div", String(idx + 1), "n");

  const info = el("div", undefined, "t");
  const strong = el("strong");
  if (locked) {
    strong.textContent = t.title;
  } else {
    const a = el("a", t.title);
    a.href = "topic.html?id=" + encodeURIComponent(t.id) + "&subject=" + encodeURIComponent(subjectId);
    strong.append(a);
  }
  info.append(strong);
  if (locked) info.append(el("span", "Pass the quiz for topic " + idx + " to unlock this."));
  else if (t.status === "failed") info.append(el("span", "Quiz not passed yet. Repeat the topic and try again."));

  li.append(n, info);
  if (!isFaculty) {
    const score = t.score != null ? " \u00b7 " + t.score + "%" : "";
    if (locked) li.append(el("span", "Locked", "pill lock"));
    else if (t.status === "passed") li.append(el("span", "Passed" + score, "pill pass"));
    else if (t.status === "failed") li.append(el("span", "Retake" + score, "pill open"));
    else li.append(el("span", "Start", "pill open"));
  }
  return li;
}

async function loadTopics() {
  const r = await api("/subjects/" + encodeURIComponent(subjectId) + "/topics");
  const msg = document.getElementById("list-msg");
  if (!r.ok) {
    msg.textContent = (r.body && r.body.error) || "Couldn't load the topics. Refresh the page to try again.";
    return;
  }
  msg.textContent = "";
  const s = r.body.subject;
  if (s) {
    document.title = s.name + " | ITClassroom";
    document.getElementById("title").textContent = s.name;
    document.getElementById("crumb").textContent = s.code;
    document.getElementById("meta").textContent = s.code + " · " + s.term + " · " + s.year;
  }
  const topics = r.body.topics || [];
  list.replaceChildren(...topics.map(row));
  emptyEl.textContent = role === "faculty"
    ? "No topics yet. Add the first topic above."
    : "No topics yet. Your faculty will add them here.";
  emptyEl.hidden = topics.length > 0;
}

api("/me").then(r => {
  if (!r.ok) { location.href = "login.html"; return; }
  role = r.body.role;
  document.getElementById("who").textContent = r.body.username + " (" + role + ")";
  if (role === "faculty") document.getElementById("add-box").style.display = "block";
  loadTopics();
});

document.getElementById("add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const r = await api("/subjects/" + encodeURIComponent(subjectId) + "/topics", { title: f.title.value.trim() });
  document.getElementById("msg").textContent = r.ok ? "" : ((r.body && r.body.error) || "Couldn't add the topic.");
  if (r.ok) { f.reset(); loadTopics(); }
});

document.getElementById("logout").onclick = async () => {
  await api("/logout", {});
  location.href = "login.html";
};