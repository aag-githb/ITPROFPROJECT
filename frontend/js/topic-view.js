
const VIEW_API = `http://${location.hostname}:5000/api`;

const params = new URLSearchParams(location.search);
const topicId = params.get("id");
const subjectId = params.get("subject");

let slides = [];
let slideIndex = 0;

async function request(path) {
  const response = await fetch(VIEW_API + path, {
    credentials: "include",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.error || `Unable to load lesson (${response.status})`
    );
  }

  return data;
}

function textElement(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text || "";
  return element;
}

function renderSlide() {
  const container = document.getElementById("view-slide");
  const counter = document.getElementById("slide-count");

  container.replaceChildren();

  if (!slides.length) {
    container.textContent = "No slides available.";
    counter.textContent = "0 / 0";
    return;
  }

  const slide = slides[slideIndex];

  container.appendChild(
    textElement("h3", slide.title || `Slide ${slideIndex + 1}`)
  );

  container.appendChild(textElement("p", slide.text || ""));

  if (slide.image) {
    try {
      const url = new URL(slide.image, location.href);

      if (["http:", "https:"].includes(url.protocol)) {
        const image = document.createElement("img");
        image.src = url.href;
        image.alt = slide.title || "Slide image";
        image.loading = "lazy";
        image.style.maxWidth = "100%";
        container.appendChild(image);
      }
    } catch (error) {
      console.warn("Invalid slide image URL:", error);
    }
  }

  counter.textContent = `${slideIndex + 1} / ${slides.length}`;
}

async function init() {
  const titleElement = document.getElementById("view-title");

  if (!topicId || !subjectId) {
    titleElement.textContent = "Missing topic or subject ID.";
    return;
  }

  titleElement.textContent = "Loading lesson…";

  try {
    const user = await request("/me");
    const data = await request(
      `/topics/${encodeURIComponent(topicId)}`
    );

    const topic = data.topic;

    if (!topic) {
      throw new Error("Topic not found.");
    }

    titleElement.textContent = topic.title || "Untitled Topic";
    document.getElementById("view-description").textContent =
      topic.description || "No topic description provided.";
    document.title = `${topic.title || "Lesson"} | ITClassroom`;

    // Show the teacher's saved, formatted lesson content.
    const content = document.getElementById("view-content");
    content.innerHTML =
      topic.content || "<p>No lesson content has been added yet.</p>";

    // Show the summary and preserve its line breaks.
    const summary = document.getElementById("view-summary");
    summary.textContent = topic.summary || "No summary provided yet.";
    summary.style.whiteSpace = "pre-wrap";

    // Return to the correct topics page.
    document.getElementById("back-link").href =
  `toc.html?subject=${encodeURIComponent(subjectId)}`;
    if (user.role === "faculty") {
      const editLink = document.getElementById("edit-lesson");
      editLink.href =
        `topic-editor.html?id=${encodeURIComponent(topicId)}` +
        `&subject=${encodeURIComponent(subjectId)}`;
      editLink.hidden = false;
    } else if (topic.has_quiz) {
      const quizAction = document.getElementById("lesson-quiz-action");
      const quizLink = document.getElementById("start-quiz");
      quizLink.href =
        `quiz.html?id=${encodeURIComponent(topicId)}` +
        `&subject=${encodeURIComponent(subjectId)}`;
      quizAction.hidden = false;
    }

    // Render uploaded presentations.
    const files = document.getElementById("view-presentations");
    files.replaceChildren();

    const presentations = topic.presentations || [];

    if (presentations.length === 0) {
      files.appendChild(textElement("li", "No presentations uploaded."));
    } else {
      presentations.forEach(file => {
        const li = document.createElement("li");
        const link = document.createElement("a");

        // file.url already starts with /api, so don't add /api twice.
        link.href = `http://${location.hostname}:5000${file.url}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = file.name || "Open presentation";

        li.appendChild(link);
        files.appendChild(li);
      });
    }

    // Load and display saved slides.
    slides = Array.isArray(topic.slides) ? topic.slides : [];
    slideIndex = 0;
    renderSlide();

    console.log("Lesson loaded successfully:", topic);
  } catch (error) {
    titleElement.textContent = "Unable to load lesson";
    console.error("Failed to load lesson:", error);

    const content = document.getElementById("view-content");
    content.textContent = error.message;
  }
}

document.getElementById("previous-slide").addEventListener("click", () => {
  if (slides.length) {
    slideIndex = (slideIndex - 1 + slides.length) % slides.length;
    renderSlide();
  }
});

document.getElementById("next-slide").addEventListener("click", () => {
  if (slides.length) {
    slideIndex = (slideIndex + 1) % slides.length;
    renderSlide();
  }
});

init();
