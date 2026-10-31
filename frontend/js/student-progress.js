const progressList = document.getElementById("progress-list");
const progressMessage = document.getElementById("progress-message");
const progressEmpty = document.getElementById("progress-empty");

function progressElement(tag, text = "", className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function formatAttempt(attempt) {
  const date = attempt.finished_at
    ? new Date(attempt.finished_at).toLocaleString()
    : "Date unavailable";
  const status = attempt.passed ? "Passed" : "Not passed";
  return `${attempt.score}% - ${status} - ${date}`;
}

function renderSubject(subject) {
  const section = progressElement("section", "", "progress-subject");
  const header = progressElement("div", "", "progress-subject-header");
  const heading = document.createElement("div");
  heading.append(
    progressElement("h2", subject.name || "Untitled subject"),
    progressElement(
      "p",
      [subject.code, subject.term, subject.year_level, subject.academic_year]
        .filter(Boolean).join(" - "),
      "progress-subject-meta"
    )
  );

  const summary = progressElement("div", "", "progress-summary");
  const summaryLabel = progressElement("div", "", "progress-summary-label");
  summaryLabel.append(
    progressElement("span", "Lesson progress"),
    progressElement("span", `${subject.progress}%`)
  );
  const bar = progressElement("div", "", "bar");
  const fill = document.createElement("i");
  fill.style.width = `${subject.progress}%`;
  bar.append(fill);
  summary.append(summaryLabel, bar);
  header.append(heading, summary);

  const topics = progressElement("ul", "", "progress-topics");
  if (!subject.topics.length) {
    topics.append(progressElement("li", "No lessons have been added yet."));
  }
  subject.topics.forEach(topic => {
    const row = progressElement("li", "", "progress-topic");
    row.append(progressElement("div", topic.title || "Untitled lesson", "progress-topic-title"));
    const attempts = progressElement("ul", "", "progress-attempts");
    if (!topic.has_quiz) {
      attempts.append(progressElement("li", "No quiz for this lesson."));
    } else if (!topic.attempts.length) {
      attempts.append(progressElement("li", "No quiz attempts yet."));
    } else {
      topic.attempts.forEach(attempt => {
        attempts.append(progressElement(
          "li",
          formatAttempt(attempt),
          `progress-attempt ${attempt.passed ? "progress-passed" : "progress-failed"}`
        ));
      });
    }
    row.append(attempts);
    topics.append(row);
  });
  section.append(header, topics);
  return section;
}

async function loadProgress() {
  try {
    const result = await api("/student/progress");
    if (!result.ok) {
      throw new Error(result.body?.error || "Unable to load progress.");
    }
    const subjects = Array.isArray(result.body.subjects)
      ? result.body.subjects : [];
    progressList.replaceChildren(...subjects.map(renderSubject));
    progressEmpty.hidden = subjects.length > 0;
  } catch (error) {
    progressMessage.textContent = error.message;
  }
}

async function initializeProgress() {
  const result = await api("/me");
  if (!result.ok || result.body.role !== "student") {
    location.replace(result.ok ? "subjects.html" : "login.html");
    return;
  }
  document.getElementById("who").textContent =
    `${result.body.username} (student)`;
  await loadProgress();
}

initializeProgress();
