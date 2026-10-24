// Faculty sign in and register with their name; students use their ID number (TUPT-YY-NNNN).
// Disabled inputs are skipped by form validation and by FormData, so only the visible identifier is sent.

document.querySelectorAll("input[data-digits]").forEach(input => {
  input.addEventListener("input", () => { input.value = input.value.replace(/\D/g, ""); });
});

document.querySelectorAll("form").forEach(form => {
  const role = form.querySelector('select[name="role"]');
  const idBox = form.querySelector('[data-for="id"]');
  const nameBox = form.querySelector('[data-for="name"]');
  if (!role || !idBox || !nameBox) return;

  function sync() {
    const faculty = role.value === "faculty";
    idBox.hidden = faculty;
    nameBox.hidden = !faculty;
    idBox.querySelectorAll("input").forEach(i => { i.disabled = faculty; });
    nameBox.querySelectorAll("input").forEach(i => { i.disabled = !faculty; });
  }

  role.addEventListener("change", sync);
  sync();
});