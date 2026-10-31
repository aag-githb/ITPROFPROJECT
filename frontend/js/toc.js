
const params = new URLSearchParams(location.search);
const subjectId = params.get("subject");

const list = document.getElementById("list");
const emptyEl = document.getElementById("empty");
const titleEl = document.getElementById("title");
const crumbEl = document.getElementById("crumb");
const metaEl = document.getElementById("meta");
const form = document.getElementById("add-form");
const input = form?.querySelector('input[name="title"]');
const descriptionInput = form?.querySelector('textarea[name="description"]');
const addBox = document.getElementById("add-box");
const topicModal = document.getElementById("topic-modal");
const lessonTab = document.getElementById("lesson-tab");
const peopleTab = document.getElementById("people-tab");
const lessonPanel = document.getElementById("lesson-panel");
const peoplePanel = document.getElementById("people-panel");
const subjectEditButton = document.getElementById("open-subject-edit");
const deleteSubjectButton = document.getElementById("delete-subject");
const subjectEditModal = document.getElementById("subject-edit-modal");
const subjectEditForm = document.getElementById("subject-edit-form");
const subjectEditMessage = document.getElementById("subject-edit-msg");

let currentRole = "";
let currentSubject = null;

function openSubjectEdit() {
  if (!currentSubject) return;

  Object.entries({
    name: currentSubject.name,
    code: currentSubject.code,
    category: currentSubject.category,
    section: currentSubject.section,
    term: currentSubject.term,
    year_level: currentSubject.year_level,
    academic_year: currentSubject.academic_year
  }).forEach(([name, value]) => {
    subjectEditForm.elements[name].value = value || "";
  });
  subjectEditMessage.textContent = "";
  subjectEditModal.showModal();
}

function setTab(tab) {
  const people = tab === "people";
  lessonPanel.hidden = people;
  peoplePanel.hidden = !people;
  lessonTab.classList.toggle("active", !people);
  peopleTab.classList.toggle("active", people);
  lessonTab.toggleAttribute("aria-current", !people);
  peopleTab.toggleAttribute("aria-current", people);
  if (people) loadPeople();
}

async function loadPeople() {
  const facultyList = document.getElementById("faculty-list");
  const studentList = document.getElementById("student-list");
  const peopleMsg = document.getElementById("people-msg");
  facultyList.replaceChildren();
  studentList.replaceChildren();
  peopleMsg.textContent = "";
  try {
    const result = await api(`/subjects/${encodeURIComponent(subjectId)}/people`);
    if (!result.ok) throw new Error(result.body?.error || "Unable to load people.");
    const render = (items, target, empty) => {
      if (!items.length) target.append(el("li", empty));
      items.forEach(person => {
        const row = el("li", "", "person-row");
        row.append(el("span", person.username));
        if (currentRole === "faculty" && target === studentList) {
          const removeButton = el("button", "Remove", "btn danger-button");
          removeButton.type = "button";
          removeButton.addEventListener("click", () => removeStudent(person.username));
          row.append(removeButton);
        }
        target.append(row);
      });
    };
    render(result.body.faculty || [], facultyList, "No faculty listed.");
    render(result.body.students || [], studentList, "No students enrolled yet.");
  } catch (error) {
    peopleMsg.textContent = error.message;
  }
}

async function removeStudent(username) {
  if (!await confirmDeletion(`Remove ${username} from this subject?`)) return;

  const peopleMsg = document.getElementById("people-msg");
  peopleMsg.textContent = "";
  try {
    const result = await api(
      `/subjects/${encodeURIComponent(subjectId)}/students/${encodeURIComponent(username)}`,
      undefined,
      "DELETE"
    );
    if (!result.ok) {
      throw new Error(result.body?.error || "Unable to remove student.");
    }
    await loadPeople();
  } catch (error) {
    peopleMsg.textContent = error.message;
  }
}

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
    const description = el(
      "p",
      topic.description || "No description provided yet.",
      "topic-description"
    );

    const statusText =
      topic.status === "passed" ? "Passed" :
      topic.status === "locked" ? "Locked until previous topic is passed" :
      topic.status === "unlocked" ? "Ready to study and take the quiz" :
      "Available";

    const status = el("p", statusText, "topic-status");
    details.append(topicTitle, description, status);

    const openLink = el("a", "Open lesson", "topic-link topic-action primary-action");
    openLink.href =
      `topic-view.html?id=${encodeURIComponent(topic.id)}` +
      `&subject=${encodeURIComponent(subjectId)}`;
    if (currentRole === "student" && topic.status === "locked") {
      openLink.setAttribute("aria-disabled", "true");
      openLink.addEventListener("click", event => event.preventDefault());
    }

    const actions = el("div", "", "topic-actions");
    actions.append(openLink);
    if (currentRole === "faculty") {
      const quizLink = el("a", "Manage quiz", "topic-link topic-action");
      quizLink.href =
        `quiz-editor.html?id=${encodeURIComponent(topic.id)}` +
        `&subject=${encodeURIComponent(subjectId)}`;
      actions.append(quizLink);
      const deleteButton = el(
        "button",
        "🗑",
        "btn topic-action danger-button topic-delete-button"
      );
      deleteButton.type = "button";
      deleteButton.setAttribute("aria-label", "Remove topic");
      deleteButton.title = "Remove topic";
      deleteButton.addEventListener("click", async () => {
        if (!await confirmDeletion(
          `Remove "${topic.title}"? This will also remove its quiz and progress.`
        )) return;

        deleteButton.disabled = true;
        const result = await api(
          `/topics/${encodeURIComponent(topic.id)}`,
          undefined,
          "DELETE"
        );
        if (!result.ok) {
          deleteButton.disabled = false;
          showMessage(result.body?.error || "Unable to remove topic.", true);
          return;
        }
        await loadTopics();
      });
      actions.append(deleteButton);
    } else if (topic.status !== "locked") {
      const quizLink = el("a", "Take quiz", "topic-link topic-action");
      quizLink.href =
        `quiz.html?id=${encodeURIComponent(topic.id)}` +
        `&subject=${encodeURIComponent(subjectId)}`;
      actions.append(quizLink);
    }
    item.append(number, details, actions);
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

    currentSubject = subject;
    titleEl.textContent = subject.name || "Topics";
    crumbEl.textContent = subject.name || "Subject";

    metaEl.textContent = [
      subject.code,
      subject.term,
      subject.year_level,
      subject.academic_year ? `AY ${subject.academic_year}` : ""
    ].filter(Boolean).join(" · ");

    if (subject.join_code && currentRole === "faculty") {
      metaEl.textContent += ` · Join code: ${subject.join_code}`;
    }
    subjectEditButton.hidden = currentRole !== "faculty";
    deleteSubjectButton.hidden = currentRole !== "faculty";

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
    location.replace("subjects.html");
    return;
  }

  try {
    const result = await api("/me");

    if (!result.ok) {
      location.replace("login.html");
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

async function deleteCurrentSubject() {
  if (!currentSubject) return;
  if (!await confirmDeletion(
    `Delete "${currentSubject.name}"? This will remove its topics, quizzes, and enrolled students.`
  )) return;

  deleteSubjectButton.disabled = true;
  try {
    const result = await api(
      `/subjects/${encodeURIComponent(subjectId)}`,
      undefined,
      "DELETE"
    );
    if (!result.ok) {
      throw new Error(result.body?.error || "Unable to delete subject.");
    }
    location.replace("subjects.html");
  } catch (error) {
    deleteSubjectButton.disabled = false;
    document.getElementById("list-msg").textContent = error.message;
  }
}

deleteSubjectButton?.addEventListener("click", deleteCurrentSubject);
subjectEditForm?.addEventListener("submit", async event => {
  event.preventDefault();
  subjectEditMessage.textContent = "";
  const submitButton = subjectEditForm.querySelector('[type="submit"]');
  submitButton.disabled = true;

  const data = Object.fromEntries(
    ["name", "code", "category", "section", "term", "year_level", "academic_year"]
      .map(name => [name, subjectEditForm.elements[name].value.trim()])
  );

  try {
    const result = await api(
      `/subjects/${encodeURIComponent(subjectId)}`,
      data,
      "PUT"
    );
    if (!result.ok) {
      throw new Error(result.body?.error || "Unable to update subject.");
    }
    subjectEditModal.close();
    await loadTopics();
  } catch (error) {
    subjectEditMessage.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
});

subjectEditButton?.addEventListener("click", openSubjectEdit);
document.getElementById("close-subject-edit")?.addEventListener(
  "click",
  () => subjectEditModal.close()
);
document.getElementById("cancel-subject-edit")?.addEventListener(
  "click",
  () => subjectEditModal.close()
);

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
        { title, description: descriptionInput?.value.trim() || "" }
      );

      if (!result.ok) {
        throw new Error(result.body?.error || "Unable to add topic.");
      }

      input.value = "";
      if (descriptionInput) descriptionInput.value = "";
      topicModal?.close();
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

lessonTab?.addEventListener("click", event => {
  event.preventDefault();
  setTab("lesson");
});
peopleTab?.addEventListener("click", event => {
  event.preventDefault();
  setTab("people");
});

document.getElementById("open-topic-modal")?.addEventListener("click", () => {
  topicModal?.showModal();
  input?.focus();
});
document.getElementById("close-topic-modal")?.addEventListener("click", () => topicModal?.close());
document.getElementById("cancel-topic-modal")?.addEventListener("click", () => topicModal?.close());
