const QUIZ_API = `http://${location.hostname}:5000/api`;
const quizParams = new URLSearchParams(location.search);
const quizTopicId = quizParams.get("id");
const quizSubjectId = quizParams.get("subject");
const questionsEl = document.getElementById("questions");
const messageEl = document.getElementById("quiz-message");
let quizExists = false;

async function quizRequest(path, options = {}) {
  const response = await fetch(QUIZ_API + path, { credentials: "include", ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function say(text, error = false) {
  messageEl.textContent = text;
  messageEl.style.color = error ? "#b91c1c" : "#166534";
}

function questionCard(question = {}) {
  const card = document.createElement("article");
  card.className = "slide-card quiz-question";
  card.innerHTML = `
    <h3></h3>
    <label class="field"><span>Question</span><textarea class="question-text" rows="3" maxlength="5000"></textarea></label>
    <label class="field"><span>Type</span><select class="question-type">
      <option value="multiple_choice">Multiple choice</option>
      <option value="simple">Simple answer</option>
      <option value="practical">Practical</option>
    </select></label>
    <label class="field"><span>Choices (one per line, optional)</span><textarea class="question-choices" rows="4"></textarea></label>
    <label class="field"><span>Correct answer</span><input class="question-answer" maxlength="1000"></label>
    <button type="button" class="remove-question">Remove question</button>`;
  card.querySelector(".question-text").value = question.text || "";
  card.querySelector(".question-type").value = question.type || "multiple_choice";
  card.querySelector(".question-choices").value = (question.choices || []).join("\n");
  card.querySelector(".question-answer").value = question.correct_answer || "";
  card.querySelector(".remove-question").addEventListener("click", () => {
    card.remove();
    renumberQuestions();
  });
  questionsEl.append(card);
  renumberQuestions();
}

function renumberQuestions() {
  const cards = [...questionsEl.querySelectorAll(".quiz-question")];
  cards.forEach((card, index) => {
    card.querySelector("h3").textContent = `Question ${index + 1}`;
  });
  document.getElementById("question-count").textContent = `(${cards.length}/10-20)`;
}

function collectQuestions() {
  return [...questionsEl.querySelectorAll(".quiz-question")].map(card => ({
    text: card.querySelector(".question-text").value.trim(),
    type: card.querySelector(".question-type").value,
    choices: card.querySelector(".question-choices").value.split("\n").map(v => v.trim()).filter(Boolean),
    correct_answer: card.querySelector(".question-answer").value.trim()
  }));
}

async function loadQuiz() {
  if (!quizTopicId || !quizSubjectId) {
    say("Missing topic or subject ID.", true);
    return;
  }
  document.getElementById("back-link").href = `toc.html?subject=${encodeURIComponent(quizSubjectId)}`;
  document.getElementById("report-link").href = `${QUIZ_API}/topics/${encodeURIComponent(quizTopicId)}/quiz/report.csv`;
  try {
    const data = await quizRequest(`/topics/${encodeURIComponent(quizTopicId)}/quiz`);
    quizExists = true;
    data.quiz.questions.forEach(questionCard);
    await loadAttempts();
  } catch (error) {
    if (error.message === "Quiz not found") {
      say("Create a quiz with 10 to 20 questions.");
    } else {
      say(error.message, true);
    }
  }
}

async function loadAttempts() {
  try {
    const [summary, attempts] = await Promise.all([
      quizRequest(`/topics/${encodeURIComponent(quizTopicId)}/quiz/summary`),
      quizRequest(`/topics/${encodeURIComponent(quizTopicId)}/quiz/attempts`)
    ]);
    document.getElementById("attempt-summary").textContent =
      `${summary.attempt_count} completed attempts · ${summary.passed_count} passed · average ${summary.average_score}%`;
    const list = document.getElementById("attempts");
    list.replaceChildren(...attempts.attempts.map(attempt => {
      const item = document.createElement("li");
      item.textContent = `${attempt.username}: ${attempt.score}% (${attempt.passed ? "Passed" : "Did not pass"})`;
      return item;
    }));
  } catch (error) {
    say(error.message, true);
  }
}

document.getElementById("add-question").addEventListener("click", () => questionCard());
document.getElementById("save-quiz").addEventListener("click", async () => {
  const questions = collectQuestions();
  if (questions.length < 10 || questions.length > 20) {
    say("Add between 10 and 20 questions before saving.", true);
    return;
  }
  try {
    await quizRequest(`/topics/${encodeURIComponent(quizTopicId)}/quiz`, {
      method: quizExists ? "PUT" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        questions
      })
    });
    quizExists = true;
    say("Quiz saved successfully.");
    await loadAttempts();
  } catch (error) {
    say(error.message, true);
  }
});
document.getElementById("delete-quiz").addEventListener("click", async () => {
  if (!quizExists || !await confirmDeletion("Delete this quiz?")) return;
  try {
    await quizRequest(`/topics/${encodeURIComponent(quizTopicId)}/quiz`, {method: "DELETE"});
    questionsEl.replaceChildren();
    quizExists = false;
    say("Quiz deleted.");
    renumberQuestions();
  } catch (error) {
    say(error.message, true);
  }
});
document.getElementById("print-report").addEventListener("click", () => window.print());
loadQuiz();
