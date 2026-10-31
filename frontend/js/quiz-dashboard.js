const DASHBOARD_API = `http://${location.hostname}:5000/api`;
const rowsEl = document.getElementById("score-rows");
const emptyEl = document.getElementById("empty");
const messageEl = document.getElementById("dashboard-message");
const subjectFilter = document.getElementById("subject-filter");
const topicFilter = document.getElementById("topic-filter");
const tocList = document.getElementById("toc-list");
const studentRecordsModal = document.getElementById("student-records-modal");
const studentRecordRows = document.getElementById("student-record-rows");
const studentRecordsMessage = document.getElementById("student-records-message");
const studentRecordsEmpty = document.getElementById("student-records-empty");
let tocSubjects = [];

async function loadDashboard() {
  try {
    const query = new URLSearchParams();
    if (subjectFilter.value) query.set("subject_id", subjectFilter.value);
    if (topicFilter.value) query.set("topic_id", topicFilter.value);
    const response = await fetch(`${DASHBOARD_API}/faculty/quiz-dashboard?${query}`, {
      credentials: "include"
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) location.replace("login.html");
      throw new Error(data.error || "Unable to load score dashboard.");
    }

    const rows = data.students || [];
    emptyEl.hidden = rows.length > 0;
    rowsEl.replaceChildren(...rows.map(row => {
      const tr = document.createElement("tr");
      const values = [
        row.student,
        row.quiz_count,
        row.attempt_count,
        row.passed_count,
        `${row.average_score}%`,
        `${row.best_score}%`
      ];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index >= 4) {
          cell.className = Number.parseFloat(value) >= data.passing_score
            ? "score-good" : "score-low";
        }
        tr.append(cell);
      });
      const recordsCell = document.createElement("td");
      const recordsButton = document.createElement("button");
      recordsButton.type = "button";
      recordsButton.className = "btn student-records-button";
      recordsButton.textContent = "View records";
      recordsButton.addEventListener("click", () => loadStudentRecords(row.student));
      recordsCell.append(recordsButton);
      tr.append(recordsCell);
      return tr;
    }));
  } catch (error) {
    messageEl.textContent = error.message;
  }
}

function formatRecordDate(value) {
  return value ? new Date(value).toLocaleString() : "Date unavailable";
}

async function loadStudentRecords(student) {
  studentRecordsMessage.textContent = "";
  studentRecordsEmpty.hidden = true;
  studentRecordRows.replaceChildren();
  document.getElementById("student-records-title").textContent =
    `${student}'s records`;
  studentRecordsModal.showModal();
  try {
    const query = new URLSearchParams();
    if (subjectFilter.value) query.set("subject_id", subjectFilter.value);
    if (topicFilter.value) query.set("topic_id", topicFilter.value);
    const response = await fetch(
      `${DASHBOARD_API}/faculty/quiz-dashboard/student/${encodeURIComponent(student)}?${query}`,
      {credentials: "include"}
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to load student records.");
    document.getElementById("student-records-summary").textContent =
      `${data.records.length} attempts · ${data.passed_count} passed · ` +
      `average ${data.average_score}% · best ${data.best_score}%`;
    studentRecordsEmpty.hidden = data.records.length > 0;
    studentRecordRows.replaceChildren(...data.records.map(record => {
      const row = document.createElement("tr");
      [
        `${record.subject_code} — ${record.subject}`,
        record.topic,
        `${record.score}%`,
        record.passed ? "Passed" : "Not passed",
        formatRecordDate(record.finished_at)
      ].forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 2 || index === 3) {
          cell.className = record.passed ? "score-good" : "score-low";
        }
        row.append(cell);
      });
      return row;
    }));
  } catch (error) {
    studentRecordsMessage.textContent = error.message;
  }
}

function updateCsvLink() {
  const query = new URLSearchParams();
  if (subjectFilter.value) query.set("subject_id", subjectFilter.value);
  if (topicFilter.value) query.set("topic_id", topicFilter.value);
  document.getElementById("csv-link").href =
    `${DASHBOARD_API}/faculty/quiz-dashboard.csv?${query}`;
}

function renderTopicFilter() {
  const subject = tocSubjects.find(item => item.id === subjectFilter.value);
  topicFilter.replaceChildren(new Option("All topics", ""));
  (subject?.topics || []).forEach(topic => {
    topicFilter.append(new Option(topic.title, topic.id));
  });
}

async function loadTableOfContents() {
  const response = await fetch(`${DASHBOARD_API}/faculty/table-of-contents`, {
    credentials: "include"
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Unable to load table of contents.");
  tocSubjects = data.subjects || [];
  subjectFilter.replaceChildren(new Option("All subjects", ""));
  tocSubjects.forEach(subject => {
    subjectFilter.append(new Option(`${subject.code} — ${subject.name}`, subject.id));
  });
  renderTopicFilter();
  tocList.replaceChildren(...tocSubjects.map(subject => {
    const section = document.createElement("section");
    section.className = "toc-subject";
    const heading = document.createElement("h2");
    heading.textContent = `${subject.code} — ${subject.name}`;
    const list = document.createElement("ol");
    subject.topics.forEach(topic => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = `topic-editor.html?id=${encodeURIComponent(topic.id)}&subject=${encodeURIComponent(subject.id)}`;
      link.textContent = topic.title || "Untitled lesson";
      item.append(link, document.createTextNode(
        topic.quiz_id ? ` — Quiz: ${topic.question_count} questions` : " — No quiz yet"
      ));
      list.append(item);
    });
    section.append(heading, list);
    return section;
  }));
}

document.getElementById("csv-link").href = `${DASHBOARD_API}/faculty/quiz-dashboard.csv`;
document.getElementById("print-dashboard").addEventListener(
  "click", () => window.print()
);
subjectFilter.addEventListener("change", () => {
  topicFilter.value = "";
  renderTopicFilter();
  updateCsvLink();
  loadDashboard();
});
topicFilter.addEventListener("change", () => {
  updateCsvLink();
  loadDashboard();
});
document.getElementById("clear-filters").addEventListener("click", () => {
  subjectFilter.value = "";
  renderTopicFilter();
  updateCsvLink();
  loadDashboard();
});
document.getElementById("close-student-records").addEventListener(
  "click", () => studentRecordsModal.close()
);
document.getElementById("scores-tab").addEventListener("click", () => {
  document.getElementById("scores-panel").hidden = false;
  document.getElementById("toc-panel").hidden = true;
});
document.getElementById("toc-tab").addEventListener("click", () => {
  document.getElementById("scores-panel").hidden = true;
  document.getElementById("toc-panel").hidden = false;
});
loadTableOfContents().catch(error => {
  messageEl.textContent = error.message;
});
loadDashboard();
