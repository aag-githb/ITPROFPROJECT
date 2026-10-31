const STUDENT_QUIZ_API = `http://${location.hostname}:5000/api`;
const studentParams = new URLSearchParams(location.search);
const studentTopicId = studentParams.get("id");
const studentSubjectId = studentParams.get("subject");
const quizForm = document.getElementById("quiz-form");
const quizMessage = document.getElementById("quiz-message");
let attemptId = "";

async function studentQuizRequest(path, options = {}) {
  const response = await fetch(STUDENT_QUIZ_API + path, {credentials: "include", ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function showMessage(text, error = false) {
  quizMessage.textContent = text;
  quizMessage.style.color = error ? "#b91c1c" : "#166534";
}

function renderQuiz(quiz) {
  attemptId = quiz.attempt_id;
  quizForm.replaceChildren(...quiz.questions.map((question, index) => {
    const field = document.createElement("fieldset");
    field.className = "slide-card";
    const legend = document.createElement("legend");
    legend.textContent = `${index + 1}. ${question.text}`;
    field.append(legend);
    if (question.choices && question.choices.length) {
      question.choices.forEach(choice => {
        const label = document.createElement("label");
        label.innerHTML = `<input type="radio" name="${question.id}" value=""> `;
        label.querySelector("input").value = choice;
        label.append(document.createTextNode(choice));
        field.append(label);
      });
    } else {
      const input = document.createElement("input");
      input.type = "text";
      input.name = question.id;
      input.maxLength = 1000;
      field.append(input);
    }
    return field;
  }));
}

function collectAnswers() {
  const answers = {};
  [...quizForm.querySelectorAll("fieldset")].forEach(field => {
    const input = field.querySelector("input:checked") || field.querySelector("input[type=text]");
    if (input && input.value.trim()) answers[input.name] = input.value.trim();
  });
  return answers;
}

async function submitQuiz() {
  document.getElementById("submit-quiz").disabled = true;
  try {
    const result = await studentQuizRequest(`/topics/${encodeURIComponent(studentTopicId)}/quiz/submit`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({attempt_id: attemptId, answers: collectAnswers()})
    });
    document.getElementById("result").textContent =
      `${result.score}% — ${result.passed ? "Passed. The next topic is unlocked." : "Not passed. You may retake this quiz."}`;
    await loadHistory();
    const topicsLink = document.getElementById("topics-link");
    topicsLink.href = `toc.html?subject=${encodeURIComponent(studentSubjectId)}`;
    const nextLesson = document.getElementById("next-lesson");
    if (result.passed && result.next_topic_id) {
      nextLesson.href =
        `topic-view.html?id=${encodeURIComponent(result.next_topic_id)}` +
        `&subject=${encodeURIComponent(studentSubjectId)}`;
      nextLesson.hidden = false;
    } else {
      nextLesson.hidden = true;
    }
    document.getElementById("quiz-result-modal").showModal();
  } catch (error) {
    showMessage(error.message, true);
    document.getElementById("submit-quiz").disabled = false;
  }
}

async function loadHistory() {
  const data = await studentQuizRequest(`/topics/${encodeURIComponent(studentTopicId)}/quiz/history`);
  document.getElementById("history").replaceChildren(...data.attempts.map(attempt => {
    const item = document.createElement("li");
    item.textContent = `${attempt.score}% — ${attempt.passed ? "Passed" : "Not passed"} — ${attempt.status}`;
    return item;
  }));
}

async function initQuiz() {
  if (!studentTopicId || !studentSubjectId) {
    showMessage("Missing topic or subject ID.", true);
    return;
  }
  const topicsUrl = `toc.html?subject=${encodeURIComponent(studentSubjectId)}`;
  document.getElementById("back-link").href = topicsUrl;
  document.getElementById("topics-link").href = topicsUrl;
  try {
    const data = await studentQuizRequest(`/topics/${encodeURIComponent(studentTopicId)}/quiz/start`, {method: "POST"});
    renderQuiz(data.quiz);
    await loadHistory();
  } catch (error) {
    showMessage(error.message, true);
    document.getElementById("submit-quiz").disabled = true;
  }
}

document.getElementById("submit-quiz").addEventListener("click", () => submitQuiz());
initQuiz();
