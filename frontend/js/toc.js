
const params = new URLSearchParams(location.search);
const subjectId = params.get("subject");

const list = document.getElementById("list");
const emptyEl = document.getElementById("empty");
const titleEl = document.getElementById("title");
const crumbEl = document.getElementById("crumb");
const metaEl = document.getElementById("meta");
const form = document.getElementById("add-form");
const input = form?.querySelector('input[name="title"]');
const addBox = document.getElementById("add-box");

let currentRole = "";

function el(tag, text = "", cls = "") {
  const element = document.createElement(tag);
  element.textContent = text;

  if (cls) element.className = cls;

  return element;
}

function showMessage(message, isError = false) {
  const messageEl = document.getElementById("msg");

  if (!messageEl) return;

  messageEl.textContent = message;
  messageEl.style.color = isError ? "#c62828" : "#237547";
}

function renderTopics(topics) {
  list.replaceChildren();

  if (!topics.length) {
    emptyEl.hidden = false;
    emptyEl.textContent = "No topics yet.";
    return;
  }

  emptyEl.hidden = true;

  topics.forEach((topic, index) => {
    const item = el("li", "", "topic-item");
    const number = el("span", String(index + 1), "topic-number");
    const details = el("div", "", "topic-details");
    const topicTitle = el("h3", topic.title || "Untitled Topic");

    const statusText =
      topic.status === "passed"
        ? "Passed"
        : topic.status === "failed"
        ? "Retake required"
        : "Not started";

    const status = el("p", statusText, "topic-status");
    details.append(topicTitle, status);

    const destination =
  currentRole === "faculty" ? "topic-editor.html" : "topic-view.html";

const openLink = el("a", "Open Topic", "topic-link");
openLink.href =
  `${destination}?id=${encodeURIComponent(topic.id)}` +
  `&subject=${encodeURIComponent(subjectId)}`;

    item.append(number, details, openLink);
    list.append(item);
  });
}

async function loadTopics() {
  try {
    const result = await api(`/subjects/${encodeURIComponent(subjectId)}/topics`);

    if (!result.ok) {
      throw new Error(
        result.body?.error || "Unable to load topics."
      );
    }

    const response = result.body;
    const subject = response?.subject;
    const topics = response?.topics || [];

    if (!subject) {
      throw new Error("Subject information is missing from the API response.");
    }

    titleEl.textContent = subject.name || "Topics";
    crumbEl.textContent = subject.name || "Subject";

    metaEl.textContent = [
      subject.code,
      subject.term,
      subject.year_level,
      subject.academic_year ? `AY ${subject.academic_year}` : ""
    ].filter(Boolean).join(" · ");

    renderTopics(topics);
  } catch (error) {
    console.error("Failed to load topics:", error);
    list.replaceChildren();
    emptyEl.hidden = false;
    emptyEl.textContent = error.message || "Unable to load topics.";
  }
}

async function initializePage() {
  if (!subjectId) {
    location.href = "subjects.html";
    return;
  }

  try {
    const result = await api("/me");

    if (!result.ok) {
      location.href = "login.html";
      return;
    }

    const user = result.body;
    currentRole = String(user.role || "").trim().toLowerCase();

    // Show the entire Add a Topic section to faculty only.
    if (addBox) {
      const isFaculty = currentRole === "faculty";
      addBox.hidden = !isFaculty;
      addBox.style.display = isFaculty ? "block" : "none";
    }

    await loadTopics();
  } catch (error) {
    console.error("Failed to initialize topics page:", error);
    emptyEl.hidden = false;
    emptyEl.textContent = "Unable to verify your session. Please refresh the page.";
  }
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (currentRole !== "faculty") {
      showMessage("Only faculty members can add topics.", true);
      return;
    }

    const title = input?.value.trim();

    if (!title) {
      showMessage("Please enter a topic title.", true);
      return;
    }

    const submitButton = form.querySelector('[type="submit"]');
    if (submitButton) submitButton.disabled = true;

    try {
      const result = await api(
        `/subjects/${encodeURIComponent(subjectId)}/topics`,
        { title }
      );

      if (!result.ok) {
        throw new Error(result.body?.error || "Unable to add topic.");
      }

      input.value = "";
      showMessage("Topic added successfully.");
      await loadTopics();
    } catch (error) {
      console.error("Failed to add topic:", error);
      showMessage(error.message || "Unable to add topic.", true);
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
}

initializePage();
