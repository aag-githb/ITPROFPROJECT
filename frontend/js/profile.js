const profileForm = document.getElementById("profile-form");
const profileMessage = document.getElementById("profile-message");
const statusButton = document.getElementById("toggle-status");
let profile = null;

async function loadProfile() {
  const result = await api("/profile");
  if (!result.ok) {
    location.replace("login.html");
    return;
  }
  profile = result.body;
  profileForm.elements.username.value = profile.username;
  profileForm.elements.email.value = profile.email;
  document.getElementById("who").textContent =
    `${profile.username} (${profile.role})`;
  document.getElementById("faculty-profile-tabs").hidden = profile.role !== "faculty";
  document.getElementById("student-profile-tabs").hidden = profile.role === "faculty";
  statusButton.textContent = profile.disabled ? "Enable account" : "Disable account";
}

profileForm.addEventListener("submit", async event => {
  event.preventDefault();
  profileMessage.textContent = "";
  const data = Object.fromEntries(new FormData(profileForm));
  if (!data.password) delete data.password;
  const result = await api("/profile", data, "PUT");
  if (!result.ok) {
    profileMessage.textContent = result.body?.error || "Unable to update profile.";
    return;
  }
  profileMessage.textContent = result.body.requires_email_verification
    ? "Profile saved. Verify your new email before logging in again."
    : "Profile saved.";
  await loadProfile();
});

statusButton.addEventListener("click", async () => {
  const action = profile.disabled ? "enable" : "disable";
  if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} your account?`)) return;
  const result = await api("/profile/status", {disabled: !profile.disabled}, "POST");
  if (!result.ok) {
    profileMessage.textContent = result.body?.error || "Unable to update account status.";
    return;
  }
  await loadProfile();
});

document.getElementById("delete-account").addEventListener("click", async () => {
  if (!await confirmDeletion("Delete your account permanently? This cannot be undone.")) return;
  const result = await api(
    "/profile",
    {current_password: profileForm.elements.current_password.value},
    "DELETE"
  );
  if (!result.ok) {
    profileMessage.textContent = result.body?.error || "Unable to delete account.";
    return;
  }
  location.replace("login.html");
});

loadProfile();
