
const VIEW_API = `http://${location.hostname}:5000/api`;

const params = new URLSearchParams(location.search);
const topicId = params.get("id");
const subjectId = params.get("subject");

let slides = [];
let slideIndex = 0;
let topicToc = [];
let currentUserRole = "";

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

function renderTopicToc() {
  const list = document.getElementById("topic-toc-list");
  list.replaceChildren();
  topicToc.forEach((entry, index) => {
    const item = document.createElement("li");
    item.className = "topic-toc-item";
    const title = document.createElement("input");
    title.type = "text";
    title.value = entry.title;
    title.maxLength = 200;
    title.disabled = currentUserRole !== "faculty";
    title.setAttribute("aria-label", `Topic ${index + 1} title`);
    title.addEventListener("input", () => {
      entry.title = title.value;
    });
    item.append(title);
    if (currentUserRole === "faculty") {
      const controls = document.createElement("span");
      controls.className = "topic-toc-controls";
      ["Move up", "Move down"].forEach((label, direction) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn secondary-button";
        button.textContent = direction ? "Down" : "Up";
        button.disabled = direction ? index === topicToc.length - 1 : index === 0;
        button.addEventListener("click", () => {
          const target = direction ? index + 1 : index - 1;
          [topicToc[index], topicToc[target]] = [topicToc[target], topicToc[index]];
          renderTopicToc();
        });
        controls.append(button);
      });
      item.append(controls);
    }
    list.append(item);
  });
}

async function loadTopicToc() {
  const result = await request(`/subjects/${encodeURIComponent(subjectId)}/toc`);
  topicToc = Array.isArray(result.toc) ? result.toc : [];
  renderTopicToc();
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
    currentUserRole = user.role || "";
    const data = await request(
      `/topics/${encodeURIComponent(topicId)}`
    );

    const topic = data.topic;

    if (!topic) {
      throw new Error("Topic not found.");
    }
    try {
      await loadTopicToc();
    } catch (error) {
      console.error("Failed to load table of contents:", error);
      document.getElementById("toc-message").textContent =
        "The table of contents could not be loaded.";
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
      document.getElementById("save-toc").hidden = false;
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

const tocModal = document.getElementById("toc-modal");
document.getElementById("open-toc").addEventListener("click", () => {
  renderTopicToc();
  tocModal.showModal();
});
document.getElementById("close-toc").addEventListener("click", () => tocModal.close());
document.getElementById("cancel-toc").addEventListener("click", () => tocModal.close());
document.getElementById("toc-form").addEventListener("submit", async event => {
  event.preventDefault();
  const message = document.getElementById("toc-message");
  const saveButton = document.getElementById("save-toc");
  saveButton.disabled = true;
  message.textContent = "";
  try {
    const result = await request(`/subjects/${encodeURIComponent(subjectId)}/toc`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        toc: topicToc.map(entry => ({
          topic_id: entry.topic_id,
          title: entry.title.trim(),
        })),
      }),
    });
    topicToc = result.toc;
    renderTopicToc();
    message.textContent = "Table of contents saved.";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});

init();
